# UCI Booking Selenium Test

This folder contains a realistic workflow JSON + runner harness for testing the
UCI Library Gateway booking flow with the real URL:

- https://spaces.lib.uci.edu/booking/Gateway

## Files

- `workflow_uci_library_booking.json` - WorkflowTemplate JSON
- `params.example.json` - Example parameter values
- `run_uci_booking_test.py` - Script that executes the workflow using `WorkflowRunner`

## Run

```bash
cd backend
source venv/bin/activate
python tests/uci_booking/run_uci_booking_test.py
```

Override parameters from CLI:

```bash
cd backend
source venv/bin/activate
python tests/uci_booking/run_uci_booking_test.py \
  --date 03/05/2026 \
  --room 1216 \
  --time 2:00pm \
  --duration 60 \
  --first-name Alex \
  --last-name Anteater \
  --email alex@uci.edu \
  --affiliation Undergraduate \
  --purpose Studying
```

If the script pauses for auth (`waiting_for_auth`):
1. Complete UCI login/Duo in the browser window.
2. Press Enter in terminal to resume.

Duration rules enforced by the test runner:
- Must be one of `30`, `60`, `90`, `120` minutes
- Runner computes `booking_end_time = booking_time + duration_minutes`
- Workflow clicks start slot, end slot, then `Submit Times`

Room keyword behavior:
- `room_keyword` is a partial match (not exact match required)
- Recommended values are short stable tokens like room number (e.g. `2107`)
