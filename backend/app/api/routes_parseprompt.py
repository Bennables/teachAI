import json
import os

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["parseprompt"])

# Temporary in-memory storage for the latest prompt text.
stored_prompt_text: str | None = None

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


def _call_llm_for_booking(raw_text: str) -> BookingParsedResponse:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; cannot parse prompt")
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": _BOOKING_EXTRACT_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        temperature=0.0,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned empty response")
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


@router.post("/parseprompt", status_code=status.HTTP_204_NO_CONTENT)
def parse_prompt(payload: ParsePromptRequest) -> Response:
    global stored_prompt_text
    stored_prompt_text = payload.text
    print(stored_prompt_text)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
