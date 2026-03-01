import asyncio
import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.vlm_extractor import extract_workflow
from app.core.storage import (
    get_workflow,
    list_runs,
    list_workflows as storage_list_workflows,
    save_workflow,
)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"}

# In-memory distill jobs: job_id -> { status, percent, message, workflow_id?, workflow?, error? }
_distill_jobs: dict[str, dict[str, Any]] = {}


@router.get("")
def list_workflows() -> dict[str, list[dict[str, object]]]:
    workflows = storage_list_workflows()
    runs = list_runs()
    response: list[dict[str, object]] = []

    for workflow_id, workflow in workflows.items():
        wf_runs = [run for run in runs.values() if run.workflow_id == workflow_id]
        run_count = len(wf_runs)
        succeeded = sum(1 for run in wf_runs if run.status.value == "succeeded")
        success_rate = (succeeded / run_count) if run_count else 0.0
        site_domain = urlparse(workflow.start_url).netloc

        response.append(
            {
                "id": workflow_id,
                "name": workflow.name,
                "category": workflow.category,
                "site_domain": site_domain,
                "created_at": None,
                "run_count": run_count,
                "last_run_at": None,
                "success_rate": success_rate,
            }
        )

    return {"workflows": response}


def _run_distill(job_id: str, saved_path: Path, workflow_hint: Optional[str]) -> None:
    """Run sync extraction and update job state (called from thread)."""
    job = _distill_jobs.get(job_id)
    if not job or job.get("status") != "running":
        return

    def on_progress(message: str, percent: float) -> None:
        job["message"] = message
        job["percent"] = percent

    try:
        workflow = extract_workflow(saved_path, on_progress=on_progress)
        if workflow_hint:
            hint = workflow_hint.strip().lower()
            if hint:
                tags = list(workflow.tags)
                if hint not in tags:
                    tags.append(hint)
                workflow = workflow.model_copy(update={"tags": tags})

        workflow_id = f"wf_{uuid4().hex[:8]}"
        save_workflow(workflow_id, workflow)
        job["status"] = "done"
        job["percent"] = 100
        job["message"] = "Done"
        job["workflow_id"] = workflow_id
        job["workflow"] = workflow.model_dump(mode="json")
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


@router.post("/distill-video")
async def distill_video(
    file: UploadFile = File(...),
    workflow_hint: Optional[str] = Form(default=None),
) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing uploaded filename.")
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a video.")

    suffix = (Path(file.filename).suffix or ".mp4").lower()
    if suffix not in ALLOWED_VIDEO_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format. Use mp4/webm/mov/mkv/avi/m4v.",
        )
    file_token = uuid4().hex
    saved_path = UPLOADS_DIR / f"{file_token}{suffix}"

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    saved_path.write_bytes(content)

    job_id = f"distill_{uuid4().hex[:12]}"
    _distill_jobs[job_id] = {
        "status": "running",
        "percent": 0,
        "message": "Starting…",
    }
    asyncio.create_task(
        asyncio.to_thread(_run_distill, job_id, saved_path, workflow_hint)
    )
    return {"job_id": job_id}


@router.get("/distill-video/status/{job_id}")
async def distill_video_status(job_id: str) -> StreamingResponse:
    """SSE stream of distill progress. Events: progress (percent, message) then done or error."""
    if job_id not in _distill_jobs:
        raise HTTPException(status_code=404, detail="Unknown distill job.")

    async def event_stream():
        while True:
            job = _distill_jobs.get(job_id, {})
            status = job.get("status", "running")
            payload = {
                "status": status,
                "percent": job.get("percent", 0),
                "message": job.get("message", ""),
            }
            if status == "done":
                payload["workflow_id"] = job.get("workflow_id")
                payload["workflow"] = job.get("workflow")
            elif status == "error":
                payload["error"] = job.get("error", "Unknown error")
            yield f"data: {json.dumps(payload)}\n\n"
            if status in ("done", "error"):
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{workflow_id}")
def get_workflow_by_id(workflow_id: str) -> dict[str, object]:
    workflow = get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    wf_runs = [run for run in list_runs().values() if run.workflow_id == workflow_id]
    run_count = len(wf_runs)
    succeeded = sum(1 for run in wf_runs if run.status.value == "succeeded")
    success_rate = (succeeded / run_count) if run_count else 0.0

    return {
        "workflow_id": workflow_id,
        "workflow": workflow.model_dump(mode="json"),
        "metadata": {
            "created_at": None,
            "run_count": run_count,
            "success_rate": success_rate,
        },
    }
