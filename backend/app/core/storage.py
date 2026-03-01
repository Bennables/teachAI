from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Literal, Optional, Union

from app.models.schemas import (
    DisambiguationPayload,
    LogEntry,
    RunState,
    RunStatus,
    WorkflowTemplate,
)

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_WORKFLOWS_FILE = _DATA_DIR / "workflows.json"
_RUNS_FILE = _DATA_DIR / "runs.json"


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_workflows_from_disk() -> dict[str, WorkflowTemplate]:
    _ensure_data_dir()
    if not _WORKFLOWS_FILE.exists():
        return {}
    try:
        raw: dict[str, Any] = json.loads(_WORKFLOWS_FILE.read_text())
        return {wid: WorkflowTemplate.model_validate(wf) for wid, wf in raw.items()}
    except Exception:
        return {}


def _persist_workflows(data: dict[str, WorkflowTemplate]) -> None:
    _ensure_data_dir()
    _WORKFLOWS_FILE.write_text(
        json.dumps({wid: wf.model_dump(mode="json") for wid, wf in data.items()}, indent=2)
    )


def _load_runs_from_disk() -> dict[str, RunState]:
    _ensure_data_dir()
    if not _RUNS_FILE.exists():
        return {}
    try:
        raw: dict[str, Any] = json.loads(_RUNS_FILE.read_text())
        return {rid: RunState.model_validate(rs) for rid, rs in raw.items()}
    except Exception:
        return {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_uci_fallback_workflow() -> WorkflowTemplate:
    default_payload = {
        "name": "UCI Library Room Booking",
        "description": "Fallback workflow for booking a UCI library room.",
        "start_url": "https://spaces.lib.uci.edu/spaces",
        "category": "booking",
        "tags": ["uci", "library", "booking"],
        "parameters": [
            {
                "key": "library",
                "description": "Library location dropdown value.",
                "example": "Gateway Study Center",
                "required": True,
                "input_type": "text",
            },
            {
                "key": "booking_date",
                "description": "Booking date in MM/DD/YYYY format",
                "example": "03/02/2026",
                "required": True,
                "input_type": "text",
            },
            {
                "key": "room_keyword",
                "description": "Room identifier keyword (partial match).",
                "example": "2106",
                "required": True,
                "input_type": "text",
            },
            {
                "key": "booking_time",
                "description": "Booking start time label",
                "example": "2:00pm",
                "required": True,
                "input_type": "text",
            },
            {
                "key": "duration_minutes",
                "description": "Duration in minutes (30,60,90,120).",
                "example": "60",
                "required": True,
                "input_type": "select",
                "options": ["30", "60", "90", "120"],
            },
            {
                "key": "full_name",
                "description": "Full name",
                "example": "Alex Anteater",
                "required": True,
                "input_type": "text",
            },
            {
                "key": "email",
                "description": "Email",
                "example": "alex@uci.edu",
                "required": True,
                "input_type": "text",
            },
            {
                "key": "affiliation",
                "description": "Affiliation value",
                "example": "Undergraduate",
                "required": True,
                "input_type": "select",
                "options": ["Undergraduate", "Graduate", "Faculty", "Staff"],
            },
            {
                "key": "purpose_for_reservation_covid_19",
                "description": "Reservation purpose value",
                "example": "Other",
                "required": True,
                "input_type": "text",
            },
        ],
        "steps": [
            {
                "type": "GOTO",
                "description": "Open UCI Library Gateway booking page",
                "url": "https://spaces.lib.uci.edu/booking/Gateway",
            },
            {
                "type": "WAIT",
                "description": "Wait for page content to appear",
                "until_text_visible": "Space Availability",
            },
            {
                "type": "WAIT",
                "description": "Allow room grid and scripts to fully initialize",
                "seconds": 2.5,
            },
        ],
    }

    workflow_path = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "uci_booking"
        / "workflow_uci_library_booking.json"
    )
    if workflow_path.exists():
        try:
            return WorkflowTemplate.model_validate(json.loads(workflow_path.read_text()))
        except Exception:
            pass

    return WorkflowTemplate.model_validate(default_payload)


UCI_FALLBACK_WORKFLOW_ID = "wf_abc123"
UCI_FALLBACK_WORKFLOW = _load_uci_fallback_workflow()

_disk_workflows = _load_workflows_from_disk()
if UCI_FALLBACK_WORKFLOW_ID not in _disk_workflows:
    _disk_workflows[UCI_FALLBACK_WORKFLOW_ID] = UCI_FALLBACK_WORKFLOW

workflows: dict[str, WorkflowTemplate] = _disk_workflows
runs: dict[str, RunState] = _load_runs_from_disk()


def list_workflows() -> dict[str, WorkflowTemplate]:
    return workflows


def get_workflow(workflow_id: str) -> Optional[WorkflowTemplate]:
    return workflows.get(workflow_id)


def save_workflow(workflow_id: str, workflow: WorkflowTemplate) -> WorkflowTemplate:
    workflows[workflow_id] = workflow
    _persist_workflows(workflows)
    return workflow


def delete_workflow(workflow_id: str) -> Optional[WorkflowTemplate]:
    removed = workflows.pop(workflow_id, None)
    if removed is not None:
        _persist_workflows(workflows)
    return removed


def _persist_runs(data: dict[str, RunState]) -> None:
    _ensure_data_dir()
    _RUNS_FILE.write_text(
        json.dumps({rid: rs.model_dump(mode="json") for rid, rs in data.items()}, indent=2)
    )


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
    _persist_runs(runs)
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
    _persist_runs(runs)
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
    _persist_runs(runs)
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
