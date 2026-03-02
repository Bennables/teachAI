#!/usr/bin/env python3
"""
TeachAI Backend Server

Provides two main endpoints:
1. VLM workflow extraction from videos (greenhouse and langson library)
2. Selenium script execution with UCI booking workflow
"""

import asyncio
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv(Path(__file__).resolve().parent / ".env")

# Import from existing modules
from app.core.pipeline import WorkflowExtractionPipeline
from app.models.schemas import WorkflowTemplate

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app setup
app = FastAPI(
    title="TeachAI Backend API",
    description="API for VLM workflow extraction and Selenium automation",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",  # Vite default
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
UCI_WORKFLOW_PATH = "tests/uci_booking/workflow_uci_library_booking.json"
PARAMS_EXAMPLE_PATH = "tests/uci_booking/params.example.json"
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
ALLOWED_DURATIONS = [30, 60, 90, 120]

# Request/Response Models
class VLMExtractionRequest(BaseModel):
    """Request for VLM workflow extraction."""
    workflow_type: str = Field(..., description="Type: 'greenhouse' or 'langson_library'")

class VLMExtractionResponse(BaseModel):
    """Response for VLM workflow extraction."""
    status: str
    workflow_type: str
    workflow: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    extraction_time_ms: Optional[int] = None
    source_video: Optional[str] = None

class BookingParams(BaseModel):
    """Parameters for UCI library booking."""
    library: str = Field(..., example="Langson")
    booking_date: str = Field(..., example="03/02/2026", description="Date in MM/DD/YYYY format")
    room_keyword: str = Field(..., example="394", description="Room identifier")
    booking_time: str = Field(..., example="3:00pm", description="Time slot")
    duration_minutes: int = Field(..., example=30, description="Duration in minutes (30, 60, 90, 120)")
    full_name: str = Field(default="", example="Alex Anteater", description="Full name for reservation")
    email: str = Field(default="", example="alex@uci.edu", description="Email address")
    affiliation: str = Field(..., example="Graduate", description="Affiliation (Undergraduate, Graduate, Faculty, Staff)")
    purpose_for_reservation_covid_19: str = Field(default="", example="Need a place to study", description="Purpose for reservation")

class SeleniumExecutionRequest(BaseModel):
    """Request for Selenium execution."""
    params: BookingParams
    max_auth_resumes: int = Field(default=2, description="Max authentication resume cycles")
    headless: bool = Field(default=False, description="Run in headless mode")

class SeleniumExecutionResponse(BaseModel):
    """Response for Selenium execution."""
    status: str
    run_id: str
    workflow_name: str
    execution_log: List[str]
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None

# Global state for tracking operations
extraction_tasks: Dict[str, Dict] = {}
execution_tasks: Dict[str, Dict] = {}

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "TeachAI Backend API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "vlm_extract": "/api/v1/extract-workflow",
            "selenium_execute": "/api/v1/execute-booking",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "teachai-backend",
        "timestamp": time.time()
    }

@app.post("/api/v1/extract-workflow", response_model=VLMExtractionResponse)
async def extract_workflow_from_video(
    background_tasks: BackgroundTasks,
    workflow_type: str = Query(..., description="Type: 'greenhouse' or 'langson_library'"),
    video: UploadFile = File(..., description="Video file for workflow extraction")
) -> VLMExtractionResponse:
    """
    Extract workflow from uploaded video using VLM.

    Supports two workflow types:
    - greenhouse: For greenhouse booking workflows
    - langson_library: For UCI Langson Library booking workflows
    """
    start_time = time.time()

    # Validate workflow type
    if workflow_type not in ["greenhouse", "langson_library"]:
        raise HTTPException(
            status_code=400,
            detail="workflow_type must be 'greenhouse' or 'langson_library'"
        )

    # Validate file
    if not video.filename:
        raise HTTPException(status_code=400, detail="No video file provided")

    file_ext = Path(video.filename).suffix.lower()
    if file_ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}"
        )

    temp_video = None
    try:
        # Save uploaded video to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            content = await video.read()
            tmp.write(content)
            temp_video = Path(tmp.name)

        logger.info(f"[VLM] Processing {workflow_type} workflow from {video.filename} ({len(content)} bytes)")

        # Create extraction pipeline
        pipeline = WorkflowExtractionPipeline()

        # Extract workflow using VLM
        workflow = await pipeline.extract(temp_video)

        # Convert to dictionary
        workflow_dict = workflow.model_dump()

        # Add workflow type metadata
        workflow_dict["workflow_type"] = workflow_type
        workflow_dict["source_video"] = video.filename

        execution_time_ms = int((time.time() - start_time) * 1000)

        logger.info(f"[VLM] Successfully extracted {workflow_type} workflow: {workflow.name} ({execution_time_ms}ms)")

        # Schedule cleanup
        background_tasks.add_task(cleanup_temp_file, temp_video)

        return VLMExtractionResponse(
            status="success",
            workflow_type=workflow_type,
            workflow=workflow_dict,
            extraction_time_ms=execution_time_ms,
            source_video=video.filename
        )

    except Exception as e:
        logger.error(f"[VLM] Extraction failed: {e}")

        # Cleanup on error
        if temp_video and temp_video.exists():
            background_tasks.add_task(cleanup_temp_file, temp_video)

        return VLMExtractionResponse(
            status="error",
            workflow_type=workflow_type,
            error=str(e)
        )

@app.post("/api/v1/execute-booking", response_model=SeleniumExecutionResponse)
async def execute_uci_booking(request: SeleniumExecutionRequest) -> SeleniumExecutionResponse:
    """
    Execute UCI library booking using Selenium with provided parameters.

    Uses the existing UCI booking workflow and runs it with the provided parameters.
    """
    start_time = time.time()
    run_id = f"run_uci_{uuid4().hex[:8]}"

    # Validate parameters
    try:
        validate_booking_params(request.params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Parameter validation error: {e}")

    # Construct paths
    backend_root = Path(__file__).resolve().parent
    workflow_path = backend_root / UCI_WORKFLOW_PATH
    params_temp_file = None

    try:
        # Create temporary params file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            params_dict = request.params.model_dump()
            json.dump(params_dict, tmp, indent=2)
            params_temp_file = Path(tmp.name)

        logger.info(f"[SELENIUM] Starting UCI booking execution with run_id: {run_id}")
        logger.info(f"[SELENIUM] Library: {request.params.library}, Date: {request.params.booking_date}")

        # Build command using workflow runner test script
        cmd = [
            "python", str(backend_root / "tests/uci_booking/run_uci_booking_test.py"),
            "--workflow", str(workflow_path),
            "--params", str(params_temp_file),
            "--max-auth-resumes", str(request.max_auth_resumes),
        ]

        # Execute the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=backend_root
        )

        execution_time_ms = int((time.time() - start_time) * 1000)

        # Parse output
        stdout_lines = result.stdout.strip().split('\n') if result.stdout else []
        stderr_lines = result.stderr.strip().split('\n') if result.stderr else []

        # Combine logs
        execution_log = []
        if stdout_lines:
            execution_log.extend([f"[STDOUT] {line}" for line in stdout_lines if line])
        if stderr_lines:
            execution_log.extend([f"[STDERR] {line}" for line in stderr_lines if line])

        # Determine status
        if result.returncode == 0:
            status = "success"
            error = None
            logger.info(f"[SELENIUM] Execution completed successfully in {execution_time_ms}ms")
        else:
            status = "error"
            error = f"Process exited with code {result.returncode}"
            if stderr_lines:
                error += f": {stderr_lines[-1]}"
            logger.error(f"[SELENIUM] Execution failed: {error}")

        # Cleanup temp file
        if params_temp_file:
            params_temp_file.unlink()

        return SeleniumExecutionResponse(
            status=status,
            run_id=run_id,
            workflow_name="UCI Library Room Booking",
            execution_log=execution_log,
            error=error,
            execution_time_ms=execution_time_ms
        )

    except subprocess.TimeoutExpired:
        logger.error(f"[SELENIUM] Execution timeout for run_id: {run_id}")
        if params_temp_file:
            params_temp_file.unlink()

        return SeleniumExecutionResponse(
            status="timeout",
            run_id=run_id,
            workflow_name="UCI Library Room Booking",
            execution_log=["Execution timed out after 5 minutes"],
            error="Execution timeout",
            execution_time_ms=int((time.time() - start_time) * 1000)
        )

    except Exception as e:
        logger.error(f"[SELENIUM] Unexpected error: {e}")
        if params_temp_file:
            params_temp_file.unlink()

        return SeleniumExecutionResponse(
            status="error",
            run_id=run_id,
            workflow_name="UCI Library Room Booking",
            execution_log=[],
            error=str(e),
            execution_time_ms=int((time.time() - start_time) * 1000)
        )

@app.get("/api/v1/booking-params-example")
async def get_booking_params_example() -> BookingParams:
    """Get example booking parameters."""
    try:
        backend_root = Path(__file__).resolve().parent
        params_file = backend_root / PARAMS_EXAMPLE_PATH

        if params_file.exists():
            with open(params_file, 'r') as f:
                params_data = json.load(f)
            return BookingParams(**params_data)
        else:
            # Return default example if file doesn't exist
            return BookingParams(
                library="Langson",
                booking_date="03/02/2026",
                room_keyword="394",
                booking_time="12:00pm",
                duration_minutes=30,
                full_name="Sujith Krishnamoorthy",
                email="sujithk@uci.edu",
                affiliation="Graduate",
                purpose_for_reservation_covid_19="Need a place to study"
            )
    except Exception as e:
        logger.error(f"Failed to load example params: {e}")
        raise HTTPException(status_code=500, detail="Failed to load example parameters")

# Helper functions
def validate_booking_params(params: BookingParams) -> None:
    """Validate booking parameters."""
    from datetime import datetime

    # Validate library
    if not params.library.strip():
        raise ValueError("Library cannot be empty")

    # Validate date format
    try:
        datetime.strptime(params.booking_date, "%m/%d/%Y")
    except ValueError:
        raise ValueError("booking_date must be in MM/DD/YYYY format")

    # Validate duration
    if params.duration_minutes not in ALLOWED_DURATIONS:
        raise ValueError(f"duration_minutes must be one of: {ALLOWED_DURATIONS}")

    # Validate required fields
    required_fields = [
        ('room_keyword', params.room_keyword),
        ('booking_time', params.booking_time),
        ('affiliation', params.affiliation),
    ]

    for field_name, value in required_fields:
        if not str(value).strip():
            raise ValueError(f"{field_name} cannot be empty")

    # Validate affiliation
    valid_affiliations = ["Undergraduate", "Graduate", "Faculty", "Staff"]
    if params.affiliation not in valid_affiliations:
        raise ValueError(f"affiliation must be one of: {valid_affiliations}")

def cleanup_temp_file(file_path: Path) -> None:
    """Background task to cleanup temporary files."""
    try:
        if file_path.exists():
            file_path.unlink()
            logger.debug(f"[CLEANUP] Removed temp file: {file_path}")
    except Exception as e:
        logger.warning(f"[CLEANUP] Failed to remove {file_path}: {e}")

# Run server
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )