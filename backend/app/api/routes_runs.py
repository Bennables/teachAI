from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.core.storage import (
    get_run,
    get_workflow,
    list_runs as storage_list_runs,
    save_run,
    update_run,
)
from app.executor.selenium_runner import WorkflowRunner
from app.models.schemas import RunStatus

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Keeps parameters for resumed runs in this in-memory MVP.
run_params: dict[str, dict[str, Any]] = {}
active_runners: dict[str, WorkflowRunner] = {}
TERMINAL_STATUSES = {RunStatus.SUCCEEDED, RunStatus.FAILED}


class CreateRunRequest(BaseModel):
    workflow_id: str
    params: dict[str, Any] = Field(default_factory=dict)


def _run_workflow_task(run_id: str, workflow_id: str) -> None:
    workflow = get_workflow(workflow_id)
    if workflow is None:
        return

    runner = active_runners.get(run_id)
    if runner is None:
        runner = WorkflowRunner(run_id=run_id, workflow_id=workflow_id)
        active_runners[run_id] = runner

    params = run_params.get(run_id, {})
    try:
        runner.run(workflow, params)
    except Exception:
        # Runner already records FAILED status/logs in storage.
        pass

    run = get_run(run_id)
    if run is None or run.status != RunStatus.WAITING_FOR_AUTH:
        active_runners.pop(run_id, None)
    if run is None or run.status in TERMINAL_STATUSES:
        run_params.pop(run_id, None)


@router.get("")
def list_runs() -> dict[str, list[dict[str, Any]]]:
    runs = [run.model_dump(mode="json") for run in storage_list_runs().values()]
    return {"runs": runs}


@router.post("")
def create_run(
    payload: CreateRunRequest, background_tasks: BackgroundTasks
) -> dict[str, str]:
    workflow = get_workflow(payload.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    run_id = f"run_{uuid4().hex[:8]}"
    save_run(
        run_id=run_id,
        workflow_id=payload.workflow_id,
        status=RunStatus.QUEUED,
        current_step=0,
        total_steps=len(workflow.steps),
    )
    run_params[run_id] = payload.params

    background_tasks.add_task(_run_workflow_task, run_id, payload.workflow_id)
    return {"run_id": run_id}


@router.get("/{run_id}")
def get_run_by_id(run_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return run.model_dump(mode="json")


@router.post("/{run_id}/continue")
def continue_run(run_id: str, background_tasks: BackgroundTasks) -> dict[str, bool]:
    run = get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")

    if run.status != RunStatus.WAITING_FOR_AUTH:
        raise HTTPException(
            status_code=400,
            detail="Run is not waiting for authentication.",
        )

    if run_id not in run_params:
        raise HTTPException(
            status_code=400,
            detail="Run parameters not found; cannot resume run.",
        )

    resume_step = run.current_step
    # If in-memory runner was lost (for example process restart), create a fresh
    # session and retry from one step earlier as a best-effort recovery path.
    if run_id not in active_runners:
        resume_step = max(0, run.current_step - 1)

    update_run(run_id, status=RunStatus.QUEUED, current_step=resume_step)
    background_tasks.add_task(_run_workflow_task, run_id, run.workflow_id)
    return {"ok": True}
