"""
Legacy v1 endpoints ported from server.py:
  POST /api/v1/extract-workflow   — VLM extraction from uploaded video
  POST /api/v1/execute-booking    — UCI library room booking via Selenium
  GET  /api/v1/booking-params-example
"""

import json
import logging
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.pipeline import WorkflowExtractionPipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["v1"])

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
UCI_WORKFLOW_PATH = _BACKEND_ROOT / "tests/uci_booking/workflow_uci_library_booking.json"
PARAMS_EXAMPLE_PATH = _BACKEND_ROOT / "tests/uci_booking/params.example.json"
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
ALLOWED_DURATIONS = [30, 60, 90, 120]
FORCED_BOOKING_PARAMS = {
    "library": "Langson",
    "booking_date": "03/02/2026",
    "room_keyword": "394",
    "booking_time": "12:00pm",
    "duration_minutes": 30,
    "full_name": "Sujith Krishnamoorthy",
    "email": "sujithk@uci.edu",
    "affiliation": "Graduate",
    "purpose_for_reservation_covid_19": "Need a place to study",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class VLMExtractionResponse(BaseModel):
    status: str
    workflow_type: str
    workflow: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    extraction_time_ms: Optional[int] = None
    source_video: Optional[str] = None


class BookingParams(BaseModel):
    library: str = Field(..., example="Langson")
    booking_date: str = Field(..., example="03/02/2026", description="Date in MM/DD/YYYY format")
    room_keyword: str = Field(..., example="394", description="Room identifier")
    booking_time: str = Field(..., example="3:00pm", description="Time slot")
    duration_minutes: int = Field(..., example=30, description="Duration in minutes (30, 60, 90, 120)")
    full_name: str = Field(default="", example="Alex Anteater")
    email: str = Field(default="", example="alex@uci.edu")
    affiliation: str = Field(..., example="Graduate", description="Undergraduate, Graduate, Faculty, or Staff")
    purpose_for_reservation_covid_19: str = Field(default="", example="Need a place to study")


class SeleniumExecutionRequest(BaseModel):
    params: BookingParams
    max_auth_resumes: int = Field(default=2)
    headless: bool = Field(default=False)


class SeleniumExecutionResponse(BaseModel):
    status: str
    run_id: str
    workflow_name: str
    execution_log: List[str]
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_booking_params(params: BookingParams) -> None:
    if not params.library.strip():
        raise ValueError("Library cannot be empty")
    try:
        datetime.strptime(params.booking_date, "%m/%d/%Y")
    except ValueError:
        raise ValueError("booking_date must be in MM/DD/YYYY format")
    if params.duration_minutes not in ALLOWED_DURATIONS:
        raise ValueError(f"duration_minutes must be one of: {ALLOWED_DURATIONS}")
    for field_name, value in [
        ("room_keyword", params.room_keyword),
        ("booking_time", params.booking_time),
        ("affiliation", params.affiliation),
    ]:
        if not str(value).strip():
            raise ValueError(f"{field_name} cannot be empty")
    valid_affiliations = ["Undergraduate", "Graduate", "Faculty", "Staff"]
    if params.affiliation not in valid_affiliations:
        raise ValueError(f"affiliation must be one of: {valid_affiliations}")


def _mask_email(value: str) -> str:
    cleaned = str(value).strip()
    if "@" not in cleaned:
        return "***"
    local, domain = cleaned.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _booking_params_log_view(params: BookingParams) -> dict[str, Any]:
    """Return non-sensitive booking params for tracing across queue/API/runner stages."""
    return {
        "library": params.library,
        "booking_date": params.booking_date,
        "room_keyword": params.room_keyword,
        "booking_time": params.booking_time,
        "duration_minutes": params.duration_minutes,
        "full_name": params.full_name,
        "email": _mask_email(params.email),
        "affiliation": params.affiliation,
        "purpose_for_reservation_covid_19": params.purpose_for_reservation_covid_19,
    }


def _cleanup_temp_file(file_path: Path) -> None:
    try:
        if file_path.exists():
            file_path.unlink()
    except Exception as exc:
        logger.warning(f"[CLEANUP] Failed to remove {file_path}: {exc}")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/extract-workflow", response_model=VLMExtractionResponse)
async def extract_workflow_from_video(
    background_tasks: BackgroundTasks,
    workflow_type: str = Query(..., description="'greenhouse' or 'langson_library'"),
    video: UploadFile = File(..., description="Video file for workflow extraction"),
) -> VLMExtractionResponse:
    """Extract a workflow from an uploaded video using the VLM pipeline."""
    start_time = time.time()

    if workflow_type not in ("greenhouse", "langson_library"):
        raise HTTPException(status_code=400, detail="workflow_type must be 'greenhouse' or 'langson_library'")

    if not video.filename:
        raise HTTPException(status_code=400, detail="No video file provided")

    file_ext = Path(video.filename).suffix.lower()
    if file_ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}",
        )

    temp_video: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            content = await video.read()
            tmp.write(content)
            temp_video = Path(tmp.name)

        logger.info(f"[VLM] Processing {workflow_type} from {video.filename} ({len(content)} bytes)")

        pipeline = WorkflowExtractionPipeline()
        workflow = await pipeline.extract(temp_video)

        workflow_dict = workflow.model_dump()
        workflow_dict["workflow_type"] = workflow_type
        workflow_dict["source_video"] = video.filename

        execution_time_ms = int((time.time() - start_time) * 1000)
        logger.info(f"[VLM] Extracted '{workflow.name}' in {execution_time_ms}ms")
        background_tasks.add_task(_cleanup_temp_file, temp_video)

        return VLMExtractionResponse(
            status="success",
            workflow_type=workflow_type,
            workflow=workflow_dict,
            extraction_time_ms=execution_time_ms,
            source_video=video.filename,
        )

    except Exception as exc:
        logger.error(f"[VLM] Extraction failed: {exc}")
        if temp_video:
            background_tasks.add_task(_cleanup_temp_file, temp_video)
        return VLMExtractionResponse(status="error", workflow_type=workflow_type, error=str(exc))


@router.post("/execute-booking", response_model=SeleniumExecutionResponse)
async def execute_uci_booking(request: SeleniumExecutionRequest) -> SeleniumExecutionResponse:
    """Execute UCI library room booking via Selenium with the provided parameters."""
    start_time = time.time()
    run_id = f"run_uci_{uuid4().hex[:8]}"
    effective_params = request.params
    params_for_logs = _booking_params_log_view(effective_params)

    logger.info(f"[BOOKING][RECEIVED] run_id={run_id} params={params_for_logs}")

    try:
        _validate_booking_params(effective_params)
        logger.info(f"[BOOKING][VALIDATED] run_id={run_id} params={params_for_logs}")
    except ValueError as exc:
        logger.warning(f"[BOOKING][REJECTED] run_id={run_id} reason={exc} params={params_for_logs}")
        raise HTTPException(status_code=400, detail=f"Parameter validation error: {exc}")

    params_temp_file: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(effective_params.model_dump(), tmp, indent=2)
            params_temp_file = Path(tmp.name)

        logger.info(f"[SELENIUM] run_id={run_id}  library={effective_params.library}  date={effective_params.booking_date}")

        cmd = [
            "python",
            str(_BACKEND_ROOT / "tests/uci_booking/run_uci_booking_test.py"),
            "--workflow", str(UCI_WORKFLOW_PATH),
            "--params", str(params_temp_file),
            "--max-auth-resumes", str(request.max_auth_resumes),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(_BACKEND_ROOT),
        )

        execution_time_ms = int((time.time() - start_time) * 1000)

        stdout_lines = [l for l in result.stdout.splitlines() if l] if result.stdout else []
        stderr_lines = [l for l in result.stderr.splitlines() if l] if result.stderr else []
        execution_log = (
            [f"[BOOKING][RECEIVED] run_id={run_id} params={params_for_logs}"]
            + [f"[BOOKING][VALIDATED] run_id={run_id} params={params_for_logs}"]
            + [f"[STDOUT] {l}" for l in stdout_lines]
            + [f"[STDERR] {l}" for l in stderr_lines]
        )

        if result.returncode == 0:
            status, error = "success", None
            logger.info(f"[BOOKING][COMPLETE] run_id={run_id} status=success")
        else:
            status = "error"
            error = f"Process exited with code {result.returncode}"
            if stderr_lines:
                error += f": {stderr_lines[-1]}"
            logger.error(f"[BOOKING][COMPLETE] run_id={run_id} status=error detail={error}")

        return SeleniumExecutionResponse(
            status=status,
            run_id=run_id,
            workflow_name="UCI Library Room Booking",
            execution_log=execution_log,
            error=error,
            execution_time_ms=execution_time_ms,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"[BOOKING][COMPLETE] run_id={run_id} status=timeout")
        return SeleniumExecutionResponse(
            status="timeout",
            run_id=run_id,
            workflow_name="UCI Library Room Booking",
            execution_log=["Execution timed out after 5 minutes"],
            error="Execution timeout",
            execution_time_ms=int((time.time() - start_time) * 1000),
        )

    except Exception as exc:
        logger.error(f"[SELENIUM] Unexpected error: {exc}")
        return SeleniumExecutionResponse(
            status="error",
            run_id=run_id,
            workflow_name="UCI Library Room Booking",
            execution_log=[],
            error=str(exc),
            execution_time_ms=int((time.time() - start_time) * 1000),
        )

    finally:
        if params_temp_file:
            params_temp_file.unlink(missing_ok=True)


@router.get("/booking-params-example", response_model=BookingParams)
async def get_booking_params_example() -> BookingParams:
    """Return example booking parameters."""
    if PARAMS_EXAMPLE_PATH.exists():
        try:
            return BookingParams(**json.loads(PARAMS_EXAMPLE_PATH.read_text()))
        except Exception:
            pass
    return BookingParams(
        library="Langson",
        booking_date="03/02/2026",
        room_keyword="394",
        booking_time="12:00pm",
        duration_minutes=30,
        full_name="Alex Anteater",
        email="alex@uci.edu",
        affiliation="Graduate",
        purpose_for_reservation_covid_19="Need a place to study",
    )
