#!/usr/bin/env python3
"""Run the UCI booking workflow JSON through WorkflowRunner.

Usage examples:
  python tests/uci_booking/run_uci_booking_test.py
  python tests/uci_booking/run_uci_booking_test.py --params tests/uci_booking/params.example.json
  python tests/uci_booking/run_uci_booking_test.py \
    --date 03/05/2026 --room 1216 --full-name "Alex Anteater" --email alex@uci.edu
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

# Ensure `app` package imports work when running this file directly.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.storage import get_run
from app.executor.selenium_runner import WorkflowRunner
from app.models.schemas import RunStatus, WorkflowTemplate


TEST_DIR = Path(__file__).resolve().parent
DEFAULT_WORKFLOW = TEST_DIR / "workflow_uci_library_booking.json"
DEFAULT_PARAMS = TEST_DIR / "params.example.json"
ALLOWED_DURATIONS = {30, 60, 90, 120}


def load_workflow(path: Path) -> WorkflowTemplate:
    raw = path.read_text(encoding="utf-8")
    return WorkflowTemplate.model_validate_json(raw)


def load_params(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_cli_overrides(params: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    merged = dict(params)
    if args.date:
        merged["booking_date"] = args.date
    if args.room:
        merged["room_keyword"] = args.room
    if args.time:
        merged["booking_time"] = args.time
    if args.duration:
        merged["duration_minutes"] = str(args.duration)
    if args.full_name:
        merged["full_name"] = args.full_name
    if args.email:
        merged["email"] = args.email
    if args.affiliation:
        merged["affiliation"] = args.affiliation
    if args.purpose:
        merged["purpose_for_reservation_covid_19"] = args.purpose
    return merged


def split_full_name(full_name: str) -> tuple[str, str]:
    cleaned = " ".join(str(full_name).strip().split())
    if not cleaned:
        raise ValueError("full_name cannot be empty.")
    parts = cleaned.split(" ", 1)
    first = parts[0]
    last = parts[1] if len(parts) > 1 else "."
    return first, last


def extract_room_id(room_keyword: str) -> str:
    text = str(room_keyword).strip()
    if not text:
        raise ValueError("room_keyword cannot be empty.")
    import re

    match = re.search(r"\b(\d{3,5})\b", text)
    if match:
        return match.group(1)
    token = re.sub(r"[^A-Za-z0-9_-]", "", text)
    if not token:
        raise ValueError(
            "Could not derive room_id from room_keyword. Use a value like 2106 or Gateway 2106."
        )
    return token


def compute_end_time_label(start_time_label: str, duration_minutes: int) -> str:
    normalized = start_time_label.strip().lower().replace(" ", "")
    start_dt = datetime.strptime(normalized, "%I:%M%p")
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return end_dt.strftime("%-I:%M%p").lower()


def validate_and_augment_params(params: dict[str, Any]) -> dict[str, Any]:
    raw_booking_date = params.get("booking_date")
    if not raw_booking_date:
        raise ValueError("Missing required parameter: booking_date")
    try:
        booking_date = datetime.strptime(str(raw_booking_date).strip(), "%m/%d/%Y")
    except ValueError as exc:
        raise ValueError("booking_date must use MM/DD/YYYY format.") from exc

    if "booking_time" not in params:
        raise ValueError("Missing required parameter: booking_time")

    raw_full_name = params.get("full_name")
    if not raw_full_name:
        legacy_first = str(params.get("first_name", "")).strip()
        legacy_last = str(params.get("last_name", "")).strip()
        if legacy_first or legacy_last:
            raw_full_name = " ".join(part for part in [legacy_first, legacy_last] if part)
        else:
            raise ValueError("Missing required parameter: full_name")
    full_name_first, full_name_last = split_full_name(str(raw_full_name))

    raw_room_keyword = params.get("room_keyword")
    if not raw_room_keyword:
        raise ValueError("Missing required parameter: room_keyword")
    room_id = extract_room_id(str(raw_room_keyword))

    raw_duration = params.get("duration_minutes")
    if raw_duration is None:
        raise ValueError("Missing required parameter: duration_minutes")
    try:
        duration = int(raw_duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration_minutes must be an integer value.") from exc
    if duration not in ALLOWED_DURATIONS:
        raise ValueError("duration_minutes must be one of: 30, 60, 90, 120.")

    params["duration_minutes"] = str(duration)
    params["booking_end_time"] = compute_end_time_label(params["booking_time"], duration)
    params["booking_date_iso"] = booking_date.strftime("%Y-%m-%d")
    params["booking_date_human"] = booking_date.strftime("%B %-d, %Y")
    params["full_name"] = str(raw_full_name).strip()
    params["full_name_first"] = full_name_first
    params["full_name_last"] = full_name_last
    params["room_id"] = room_id
    return params


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run UCI booking workflow test")
    parser.add_argument(
        "--workflow",
        type=Path,
        default=DEFAULT_WORKFLOW,
        help="Path to workflow JSON",
    )
    parser.add_argument(
        "--params",
        type=Path,
        default=DEFAULT_PARAMS,
        help="Path to params JSON",
    )
    parser.add_argument("--date", type=str, help="booking_date override (MM/DD/YYYY)")
    parser.add_argument("--room", type=str, help="room_keyword override")
    parser.add_argument("--time", type=str, help="booking_time override (e.g. 2:00pm)")
    parser.add_argument(
        "--duration",
        type=int,
        help="duration in minutes (30, 60, 90, 120)",
    )
    parser.add_argument("--full-name", dest="full_name", type=str, help="full_name override")
    parser.add_argument("--email", type=str, help="email override")
    parser.add_argument(
        "--affiliation",
        type=str,
        help="affiliation override (Undergraduate|Graduate|Faculty|Staff)",
    )
    parser.add_argument(
        "--purpose",
        type=str,
        help="purpose_for_reservation_covid_19 override",
    )
    parser.add_argument(
        "--max-auth-resumes",
        type=int,
        default=2,
        help="How many auth resume cycles to allow",
    )
    return parser


def status_printer(event: dict[str, Any]) -> None:
    status = event.get("status")
    step = event.get("current_step")
    message = event.get("message")
    print(f"[status={status} step={step}] {message}")


def main() -> int:
    args = build_parser().parse_args()

    if not args.workflow.exists():
        print(f"Workflow file not found: {args.workflow}", file=sys.stderr)
        return 2
    if not args.params.exists():
        print(f"Params file not found: {args.params}", file=sys.stderr)
        return 2

    workflow = load_workflow(args.workflow)
    params = merge_cli_overrides(load_params(args.params), args)
    try:
        params = validate_and_augment_params(params)
    except ValueError as exc:
        print(f"Parameter validation error: {exc}", file=sys.stderr)
        return 2

    run_id = f"run_uci_test_{uuid4().hex[:8]}"
    workflow_id = f"wf_uci_test_{uuid4().hex[:8]}"
    runner = WorkflowRunner(run_id=run_id, workflow_id=workflow_id, status_callback=status_printer)

    print(f"Run ID: {run_id}")
    print(f"Workflow: {workflow.name}")
    print(
        f"Booking window: {params['booking_time']} -> {params['booking_end_time']} "
        f"({params['duration_minutes']} minutes)"
    )
    print("Starting browser automation...")

    auth_resumes = 0
    while True:
        try:
            runner.run(workflow, params)
        except Exception as exc:  # noqa: BLE001
            print(f"Runner raised exception: {exc}", file=sys.stderr)

        run_state = get_run(run_id)
        if run_state is None:
            print("Run state missing from storage.", file=sys.stderr)
            return 1

        print(f"Current status: {run_state.status.value}")

        if run_state.status == RunStatus.WAITING_FOR_AUTH:
            if auth_resumes >= args.max_auth_resumes:
                print("Reached max auth resumes; stopping.", file=sys.stderr)
                return 1

            auth_resumes += 1
            print("Authentication pause detected.")
            print("1) Complete login/Duo in the opened browser.")
            print("2) Press Enter here to continue the workflow.")
            input()
            continue

        if run_state.status == RunStatus.SUCCEEDED:
            print("Workflow succeeded.")
            return 0

        if run_state.status == RunStatus.FAILED:
            print("Workflow failed. Recent logs:")
            for entry in run_state.logs[-10:]:
                print(f"- [{entry.level}] {entry.message}")
            return 1

        # Any other state should be transient; loop once more.
        print("Run in non-terminal state; attempting another pass.")


if __name__ == "__main__":
    raise SystemExit(main())
