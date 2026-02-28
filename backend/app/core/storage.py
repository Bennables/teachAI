from datetime import datetime, timezone
from typing import Any, Literal, Optional, Union

from app.models.schemas import (
    DisambiguationPayload,
    LogEntry,
    RunState,
    RunStatus,
    WorkflowTemplate,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


UCI_FALLBACK_WORKFLOW_ID = "wf_abc123"
UCI_FALLBACK_WORKFLOW = WorkflowTemplate.model_validate(
    {
        "name": "UCI Library Room Booking",
        "description": "Fallback workflow for booking a UCI library room.",
        "start_url": "https://spaces.lib.uci.edu/",
        "category": "booking",
        "tags": ["uci", "library", "booking"],
        "parameters": [
            {
                "key": "room",
                "description": "Room to book",
                "example": "Study Room 3A",
                "required": True,
                "input_type": "text",
            },
            {
                "key": "date",
                "description": "Booking date",
                "example": "2024-01-15",
                "required": True,
                "input_type": "date",
            },
            {
                "key": "time",
                "description": "Preferred booking time",
                "example": "2:00 PM",
                "required": True,
                "input_type": "time",
            },
        ],
        "steps": [
            {
                "type": "GOTO",
                "description": "Navigate to UCI Library booking page",
                "url": "https://spaces.lib.uci.edu/",
            },
            {
                "type": "CLICK",
                "description": "Open room booking interface",
                "target_text_hint": "Book a Room",
            },
            {
                "type": "WAIT",
                "description": "Wait for booking form to render",
                "seconds": 1.0,
            },
            {
                "type": "TYPE",
                "description": "Enter desired date",
                "target_semantic": "Date",
                "value": "{{date}}",
            },
            {
                "type": "TYPE",
                "description": "Enter desired time",
                "target_semantic": "Time",
                "value": "{{time}}",
            },
            {
                "type": "TYPE",
                "description": "Enter desired room",
                "target_semantic": "Room",
                "value": "{{room}}",
            },
            {
                "type": "CLICK",
                "description": "Submit room search",
                "target_text_hint": "Search",
            },
            {
                "type": "WAIT",
                "description": "Wait for search results",
                "seconds": 2.0,
            },
        ],
    }
)


workflows: dict[str, WorkflowTemplate] = {
    UCI_FALLBACK_WORKFLOW_ID: UCI_FALLBACK_WORKFLOW
}
runs: dict[str, RunState] = {}


def list_workflows() -> dict[str, WorkflowTemplate]:
    return workflows


def get_workflow(workflow_id: str) -> Optional[WorkflowTemplate]:
    return workflows.get(workflow_id)


def save_workflow(workflow_id: str, workflow: WorkflowTemplate) -> WorkflowTemplate:
    workflows[workflow_id] = workflow
    return workflow


def delete_workflow(workflow_id: str) -> Optional[WorkflowTemplate]:
    return workflows.pop(workflow_id, None)


def list_runs() -> dict[str, RunState]:
    return runs


def get_run(run_id: str) -> Optional[RunState]:
    return runs.get(run_id)


def save_run(
    run_id: str,
    workflow_id: str,
    status: RunStatus = RunStatus.QUEUED,
    current_step: int = 0,
    total_steps: int = 0,
) -> RunState:
    run = RunState(
        run_id=run_id,
        workflow_id=workflow_id,
        status=status,
        current_step=current_step,
        total_steps=total_steps,
        logs=[],
        disambiguation=None,
    )
    runs[run_id] = run
    return run


def update_run(
    run_id: str,
    *,
    status: Optional[Union[RunStatus, str]] = None,
    current_step: Optional[int] = None,
    error: Optional[str] = None,
    disambiguation: Optional[Union[DisambiguationPayload, dict[str, Any]]] = None,
) -> Optional[RunState]:
    run = runs.get(run_id)
    if run is None:
        return None

    updates: dict[str, Any] = {}
    if status is not None:
        updates["status"] = RunStatus(status)
    if current_step is not None:
        updates["current_step"] = current_step
    if disambiguation is not None:
        if isinstance(disambiguation, dict):
            updates["disambiguation"] = DisambiguationPayload.model_validate(
                disambiguation
            )
        else:
            updates["disambiguation"] = disambiguation
    if error:
        add_log(run_id, "error", error)

    updated = run.model_copy(update=updates)
    runs[run_id] = updated
    return updated


def add_log(
    run_id: str,
    level: Literal["info", "warn", "error"],
    message: str,
    step_index: Optional[int] = None,
    screenshot_path: Optional[str] = None,
) -> Optional[LogEntry]:
    run = runs.get(run_id)
    if run is None:
        return None

    log = LogEntry(
        ts=_utc_now_iso(),
        level=level,
        message=message,
        step_index=step_index,
        screenshot_path=screenshot_path,
    )
    updated_logs = [*run.logs, log]
    runs[run_id] = run.model_copy(update={"logs": updated_logs})
    return log


def save_resolved_selector(
    workflow_id: str, step_index: int, css_selector: str, confidence: Optional[float] = None
) -> bool:
    del confidence  # Not persisted in this simple in-memory scaffold.

    workflow = workflows.get(workflow_id)
    if workflow is None:
        return False
    if step_index < 0 or step_index >= len(workflow.steps):
        return False

    steps = list(workflow.steps)
    steps[step_index] = steps[step_index].model_copy(
        update={"resolved_css_selector": css_selector}
    )
    workflows[workflow_id] = workflow.model_copy(update={"steps": steps})
    return True
