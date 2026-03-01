import asyncio
import json as _json
from pathlib import Path
from typing import AsyncGenerator, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
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

# In-memory job queues: job_id → asyncio.Queue of SSE event dicts.
# Cleaned up when the SSE stream consumer reads the terminal event.
_distill_jobs: dict[str, asyncio.Queue] = {}


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


async def _distill_background(
    job_id: str,
    video_path: Path,
    workflow_hint: Optional[str],
) -> None:
    """Runs extraction in a thread pool and pushes SSE events into the job queue."""
    queue = _distill_jobs.get(job_id)
    if queue is None:
        return

    loop = asyncio.get_running_loop()

    def on_progress(step: str, pct: float) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "progress", "step": step, "pct": int(pct)},
        )

    def on_output(text: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "text", "content": text},
        )

    # Emit immediately so the frontend can confirm the SSE connection is alive.
    loop.call_soon_threadsafe(
        queue.put_nowait,
        {"type": "text", "content": f"Job {job_id} started — extracting workflow from {video_path.name}\n"},
    )

    try:
        workflow = await loop.run_in_executor(
            None,
            lambda: extract_workflow(video_path, on_progress, on_output),
        )

        if workflow_hint:
            hint = workflow_hint.strip().lower()
            if hint:
                tags = list(workflow.tags)
                if hint not in tags:
                    tags.append(hint)
                workflow = workflow.model_copy(update={"tags": tags})

        workflow_id = f"wf_{uuid4().hex[:8]}"
        save_workflow(workflow_id, workflow)

        # Emit the final workflow JSON into the log so it's always visible.
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "text", "content": f"\n--- Final Workflow ---\n{_json.dumps(workflow.model_dump(mode='json'), indent=2)}\n"},
        )

        loop.call_soon_threadsafe(
            queue.put_nowait,
            {
                "type": "done",
                "workflow_id": workflow_id,
                "workflow": workflow.model_dump(mode="json"),
            },
        )
    except Exception as exc:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "error", "message": str(exc)},
        )


@router.post("/distill-video")
async def distill_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    workflow_hint: Optional[str] = Form(default=None),
) -> dict[str, str]:
    """
    Accepts a video upload, saves it, starts background extraction, and immediately
    returns a job_id. The client streams progress via GET /distill-video/{job_id}/stream.
    """
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

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    file_token = uuid4().hex
    saved_path = UPLOADS_DIR / f"{file_token}{suffix}"
    saved_path.write_bytes(content)

    job_id = f"job_{uuid4().hex[:8]}"
    _distill_jobs[job_id] = asyncio.Queue()

    background_tasks.add_task(_distill_background, job_id, saved_path, workflow_hint)
    return {"job_id": job_id}


@router.get("/distill-video/{job_id}/stream")
async def stream_distill_progress(job_id: str) -> StreamingResponse:
    """SSE endpoint that streams extraction progress events for a given job_id."""
    queue = _distill_jobs.get(job_id)
    if queue is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=180.0)
                except asyncio.TimeoutError:
                    yield f"data: {_json.dumps({'type': 'error', 'message': 'Processing timed out.'})}\n\n"
                    break

                yield f"data: {_json.dumps(event)}\n\n"

                if event.get("type") in ("done", "error"):
                    _distill_jobs.pop(job_id, None)
                    break
        except asyncio.CancelledError:
            _distill_jobs.pop(job_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
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
