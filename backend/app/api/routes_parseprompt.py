import json
import logging
import os
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, ValidationError

from app.api.routes_booking import BookingParams, SeleniumExecutionRequest, execute_uci_booking
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["parseprompt"])
logger = logging.getLogger(__name__)

# Temporary in-memory storage for the latest prompt text.
stored_prompt_text: Optional[str] = None

_BOOKING_EXTRACT_PROMPT = """Extract booking/reservation details from the following text.
Return ONLY a single JSON object with exactly these keys (use empty string if not found):
- booking_date (format MM/DD/YYYY)
- room_keyword
- booking_time (e.g. 2:00pm)
- first_name
- last_name
- email
- affiliation (e.g. Undergraduate, Graduate, Staff, Faculty)
- purpose_for_reservation_covid_19 (e.g. Other, Study, Meeting)

If any required information is missing, set that field to empty string.
Do not include markdown or any text outside the JSON object."""

_ROUTE_AND_EXTRACT_PROMPT = """You are a router for automation requests.
Read the user text and return ONLY one JSON object with this exact shape:
{
  "intent": "booking" | "greenhouse" | "unknown",
  "booking": {
    "library": "",
    "booking_date": "",
    "room_keyword": "",
    "booking_time": "",
    "duration_minutes": 30,
    "full_name": "",
    "email": "",
    "affiliation": "",
    "purpose_for_reservation_covid_19": ""
  },
  "greenhouse": {
    "application_url": "",
    "first_name": "",
    "last_name": "",
    "email": "",
    "phone": "",
    "address": "",
    "submit": false
  }
}

Rules:
- intent=booking when user asks to reserve/book rooms/timeslots.
- intent=greenhouse when user asks to apply/fill a Greenhouse application.
- intent=unknown for anything else.
- Always include all keys.
- Use empty strings when unknown.
- duration_minutes must be one of 30, 60, 90, 120 (default 30).
- affiliation must be one of Undergraduate, Graduate, Faculty, Staff when present.
- Return JSON only (no markdown, no prose)."""


class GreenhouseDraft(BaseModel):
    application_url: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    submit: bool = False


class ParsePromptRouteResponse(BaseModel):
    route: Literal["booking", "greenhouse", "unknown"]
    message: str
    booking_job_id: Optional[str] = None
    booking_params: Optional[BookingParams] = None
    greenhouse_draft: Optional[GreenhouseDraft] = None
    missing_fields: list[str] = Field(default_factory=list)


class BookingJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


_booking_jobs: dict[str, BookingJobStatus] = {}


class ParsePromptRequest(BaseModel):
    text: str


class BookingParsedResponse(BaseModel):
    booking_date: str
    room_keyword: str
    booking_time: str
    first_name: str
    last_name: str
    email: str
    affiliation: str
    purpose_for_reservation_covid_19: str


def _extract_json_from_text(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    return json.loads(cleaned[start : end + 1])


def _call_grok(system_prompt: str, user_text: str) -> str:
    api_key = settings.grok_api_key or os.getenv("GROK_API_KEY")
    if not api_key:
        raise RuntimeError("GROK_API_KEY is not set; cannot parse prompt")

    payload = {
        "model": os.getenv("GROK_MODEL", "grok-3-fast"),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.0,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except Exception as exc:
        raise RuntimeError(f"Grok request failed: {exc}") from exc

    if response.status_code >= 400:
        raise RuntimeError(
            f"Grok request failed ({response.status_code}): {response.text[:500]}"
        )

    body = response.json()
    content = (
        body.get("choices", [{}])[0]
        .get("message", {})
        .get("content")
    )
    if not content:
        raise ValueError("Grok returned empty response")
    return str(content)


def _call_llm_for_booking(raw_text: str) -> BookingParsedResponse:
    content = _call_grok(_BOOKING_EXTRACT_PROMPT, raw_text)
    data = _extract_json_from_text(content)
    return BookingParsedResponse(
        booking_date=data.get("booking_date", "") or "",
        room_keyword=data.get("room_keyword", "") or "",
        booking_time=data.get("booking_time", "") or "",
        first_name=data.get("first_name", "") or "",
        last_name=data.get("last_name", "") or "",
        email=data.get("email", "") or "",
        affiliation=data.get("affiliation", "") or "",
        purpose_for_reservation_covid_19=data.get("purpose_for_reservation_covid_19", "") or "",
    )


def _call_llm_for_route(raw_text: str) -> ParsePromptRouteResponse:
    content = _call_grok(_ROUTE_AND_EXTRACT_PROMPT, raw_text)
    data = _extract_json_from_text(content)
    route = str(data.get("intent", "unknown")).strip().lower()
    if route not in {"booking", "greenhouse", "unknown"}:
        route = "unknown"

    if route == "booking":
        booking_raw = data.get("booking", {}) if isinstance(data.get("booking"), dict) else {}
        full_name = str(booking_raw.get("full_name", "") or "").strip()
        if not full_name:
            first_name = str(booking_raw.get("first_name", "") or "").strip()
            last_name = str(booking_raw.get("last_name", "") or "").strip()
            full_name = f"{first_name} {last_name}".strip()
        booking_dict = {
            "library": str(booking_raw.get("library", "") or "").strip() or "Langson",
            "booking_date": str(booking_raw.get("booking_date", "") or "").strip(),
            "room_keyword": str(booking_raw.get("room_keyword", "") or "").strip(),
            "booking_time": str(booking_raw.get("booking_time", "") or "").strip(),
            "duration_minutes": booking_raw.get("duration_minutes", 30) or 30,
            "full_name": full_name,
            "email": str(booking_raw.get("email", "") or "").strip(),
            "affiliation": str(booking_raw.get("affiliation", "") or "").strip(),
            "purpose_for_reservation_covid_19": str(
                "other"
            ).strip(),
        }

        optional_booking_fields = {"duration_minutes", "full_name", "email", "purpose_for_reservation_covid_19"}
        missing_fields = [
            key for key, value in booking_dict.items()
            if key not in optional_booking_fields and not str(value).strip()
        ]
        try:
            booking_params = BookingParams.model_validate(booking_dict)
            return ParsePromptRouteResponse(
                route="booking",
                message="Detected booking intent. Parameters parsed and ready to queue.",
                booking_params=booking_params,
                missing_fields=missing_fields,
            )
        except ValidationError:
            return ParsePromptRouteResponse(
                route="booking",
                message="Detected booking intent, but some fields need correction before queueing.",
                missing_fields=missing_fields,
            )

    if route == "greenhouse":
        greenhouse_raw = data.get("greenhouse", {}) if isinstance(data.get("greenhouse"), dict) else {}
        greenhouse_draft = GreenhouseDraft.model_validate(
            {
                "application_url": str(greenhouse_raw.get("application_url", "") or "").strip(),
                "first_name": str(greenhouse_raw.get("first_name", "") or "").strip(),
                "last_name": str(greenhouse_raw.get("last_name", "") or "").strip(),
                "email": str(greenhouse_raw.get("email", "") or "").strip(),
                "phone": str(greenhouse_raw.get("phone", "") or "").strip(),
                "address": str(greenhouse_raw.get("address", "") or "").strip(),
                "submit": bool(greenhouse_raw.get("submit", False)),
            }
        )
        missing = []
        if not greenhouse_draft.application_url:
            missing.append("application_url")
        return ParsePromptRouteResponse(
            route="greenhouse",
            message="Detected Greenhouse intent. Draft created; upload resume to run.",
            greenhouse_draft=greenhouse_draft,
            missing_fields=missing,
        )

    return ParsePromptRouteResponse(
        route="unknown",
        message="Could not confidently determine booking vs greenhouse from the text.",
    )


async def _run_booking_job(job_id: str, params: BookingParams) -> None:
    job = _booking_jobs.get(job_id)
    if not job:
        return
    safe_params = {
        "library": params.library,
        "booking_date": params.booking_date,
        "room_keyword": params.room_keyword,
        "booking_time": params.booking_time,
        "duration_minutes": params.duration_minutes,
        "full_name": params.full_name,
        "email": "***",
        "affiliation": params.affiliation,
    }
    logger.info(f"[BOOKING_JOB][RUNNING] job_id={job_id} params={safe_params}")
    _booking_jobs[job_id] = BookingJobStatus(job_id=job_id, status="running")
    try:
        response = await execute_uci_booking(SeleniumExecutionRequest(params=params))
        _booking_jobs[job_id] = BookingJobStatus(
            job_id=job_id,
            status="done" if response.status == "success" else "error",
            result=response.model_dump(),
            error=response.error,
        )
        logger.info(
            f"[BOOKING_JOB][DONE] job_id={job_id} status={_booking_jobs[job_id].status} run_id={response.run_id}"
        )
    except Exception as exc:
        _booking_jobs[job_id] = BookingJobStatus(job_id=job_id, status="error", error=str(exc))
        logger.error(f"[BOOKING_JOB][ERROR] job_id={job_id} error={exc}")


@router.post("/parseprompt", response_model=ParsePromptRouteResponse)
async def parse_prompt(payload: ParsePromptRequest, background_tasks: BackgroundTasks) -> ParsePromptRouteResponse:
    global stored_prompt_text
    stored_prompt_text = payload.text
    try:
        route_result = _call_llm_for_route(payload.text)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse prompt: {e!s}",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    if route_result.route == "booking" and route_result.booking_params and not route_result.missing_fields:
        job_id = f"booking_job_{uuid4().hex[:10]}"
        _booking_jobs[job_id] = BookingJobStatus(job_id=job_id, status="queued")
        logger.info(f"[BOOKING_JOB][QUEUED] job_id={job_id} route=booking")
        background_tasks.add_task(_run_booking_job, job_id, route_result.booking_params)
        route_result.booking_job_id = job_id
        route_result.message = "Detected booking intent. Booking workflow queued."

    return route_result


@router.get("/parseprompt/booking-jobs/{job_id}", response_model=BookingJobStatus)
def get_booking_job_status(job_id: str) -> BookingJobStatus:
    job = _booking_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Booking job not found.")
    return job


def _validate_booking_found(parsed: BookingParsedResponse) -> None:
    """Raise ValueError if required booking data is missing."""
    required = [
        ("booking_date", parsed.booking_date),
        ("room_keyword", parsed.room_keyword),
        ("booking_time", parsed.booking_time),
        ("first_name", parsed.first_name),
        ("last_name", parsed.last_name),
        ("email", parsed.email),
    ]
    missing = [k for k, v in required if not (v and str(v).strip())]
    if missing:
        raise ValueError(f"Required data could not be found: {', '.join(missing)}")


@router.get("/parseprompt/parsed", response_model=BookingParsedResponse)
def get_parsed_prompt():
    """Parse the stored prompt text into booking fields via LLM. Returns error if no text or parsing fails."""
    if not stored_prompt_text or not stored_prompt_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No prompt text stored. POST text to /api/parseprompt first.",
        )
    try:
        parsed = _call_llm_for_booking(stored_prompt_text)
        _validate_booking_found(parsed)
        return parsed
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not parse data from prompt: {e!s}",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
