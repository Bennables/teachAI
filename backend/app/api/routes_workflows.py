import asyncio
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.models.schemas import WorkflowTemplate
from app.services.workflow_extraction_service import WorkflowExtractionService
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

_distill_jobs: dict[str, dict[str, Any]] = {}


def get_distill_job(job_id: str) -> Optional[dict[str, Any]]:
    return _distill_jobs.get(job_id)


def _semantic_to_template(semantic_workflow: Any, workflow_hint: Optional[str]) -> WorkflowTemplate:
    """Convert SemanticWorkflow output into legacy WorkflowTemplate shape."""
    step_dicts: list[dict[str, Any]] = []
    for step in semantic_workflow.steps:
        step_type = str(step.type)
        base: dict[str, Any] = {"type": step_type, "description": step.description}
        target = step.target

        if step_type == "GOTO":
            base["url"] = step.url or semantic_workflow.start_url
        elif step_type == "CLICK":
            if target and target.text_hint:
                base["target_text_hint"] = target.text_hint
            if target:
                base["target_semantic"] = (
                    target.label_hint
                    or target.role_hint
                    or target.placeholder_hint
                    or target.visual_description
                )
        elif step_type == "TYPE":
            if target and target.text_hint:
                base["target_text_hint"] = target.text_hint
            if target:
                base["target_semantic"] = (
                    target.label_hint
                    or target.placeholder_hint
                    or target.role_hint
                    or target.visual_description
                )
            base["value"] = step.value or ""
        elif step_type == "SELECT":
            if target:
                base["target_semantic"] = (
                    target.label_hint
                    or target.text_hint
                    or target.role_hint
                    or target.visual_description
                )
            base["value"] = step.value or ""
        elif step_type == "WAIT":
            if step.wait_text:
                base["until_text_visible"] = step.wait_text
            else:
                base["seconds"] = max(0.5, float(step.timeout_seconds or 1.0))
        elif step_type == "SCROLL":
            base["direction"] = "down"
            base["pixels"] = 300
        else:
            # Skip unsupported step types in the legacy template schema.
            continue

        step_dicts.append(base)

    tags: list[str] = ["distilled"]
    if workflow_hint and workflow_hint.strip():
        tags.append(workflow_hint.strip().lower())

    payload = {
        "name": semantic_workflow.name,
        "description": semantic_workflow.description,
        "start_url": semantic_workflow.start_url,
        "category": "custom",
        "tags": tags,
        "parameters": [],
        "steps": step_dicts,
    }
    return WorkflowTemplate.model_validate(payload)


async def _run_distill_job(job_id: str, saved_path: Path, workflow_hint: Optional[str]) -> None:
    _distill_jobs[job_id] = {
        "status": "running",
        "percent": 10,
        "message": "Uploading video saved. Starting extraction...",
    }
    try:
        def _on_progress(message: str, percent: float) -> None:
            job = _distill_jobs.get(job_id)
            if job is None:
                return
            job["status"] = "running"
            job["percent"] = max(0.0, min(100.0, float(percent)))
            job["message"] = message

        service = WorkflowExtractionService()
        semantic_workflow = await service.extract_workflow(saved_path, progress_callback=_on_progress)
        workflow = _semantic_to_template(semantic_workflow, workflow_hint)

        _distill_jobs[job_id] = {
            "status": "running",
            "percent": 85,
            "message": "Saving workflow...",
        }
        workflow_id = f"wf_{uuid4().hex[:8]}"
        save_workflow(workflow_id, workflow)
        _distill_jobs[job_id] = {
            "status": "done",
            "percent": 100,
            "message": "Workflow distillation complete.",
            "workflow_id": workflow_id,
            "workflow": workflow.model_dump(mode="json"),
            "saved_video_path": str(saved_path),
        }
    except Exception as exc:
        _distill_jobs[job_id] = {
            "status": "error",
            "percent": 100,
            "message": "Workflow distillation failed.",
            "error": str(exc),
        }


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


@router.post("/distill-video")
async def distill_video(
    background_tasks: BackgroundTasks,
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

    job_id = f"job_{uuid4().hex[:8]}"
    _distill_jobs[job_id] = {
        "status": "queued",
        "percent": 0,
        "message": "Queued distillation job.",
    }
    background_tasks.add_task(_run_distill_job, job_id, saved_path, workflow_hint)
    return {"job_id": job_id}


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
