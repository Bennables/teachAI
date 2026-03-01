#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "[1/6] Health check: ${BASE_URL}/health"
HEALTH_JSON="$(curl -fsS "${BASE_URL}/health")"
python3 - <<'PY' "$HEALTH_JSON"
import json, sys
payload = json.loads(sys.argv[1])
assert payload.get("status") == "ok", payload
print("health ok")
PY

tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

video_file="${tmp_dir}/sample.mp4"
# Distill route currently validates only non-empty bytes + filename.
printf 'FAKE-MP4-BYTES' > "${video_file}"

echo "[2/6] Distill video (start job)"
DISTILL_JSON="$(curl -fsS -X POST "${BASE_URL}/api/workflows/distill-video" \
  -F "file=@${video_file};type=video/mp4" \
  -F "workflow_hint=booking")"

JOB_ID="$(python3 - <<'PY' "$DISTILL_JSON"
import json, sys
payload = json.loads(sys.argv[1])
jid = payload.get("job_id")
assert jid, payload
print(jid)
PY
)"
echo "job_id=${JOB_ID}"

echo "[2b/6] Poll distill status until done"
WORKFLOW_ID=""
while IFS= read -r line; do
  if [[ "$line" == data:* ]]; then
    WORKFLOW_ID="$(python3 -c "
import json, sys
s = sys.stdin.read()
data = json.loads(s)
if data.get('status') == 'done':
    print(data.get('workflow_id', ''))
elif data.get('status') == 'error':
    sys.exit(1)
" <<< "${line#data: }")"
    if [[ -n "$WORKFLOW_ID" ]]; then
      break
    fi
  fi
done < <(curl -fsS -N "${BASE_URL}/api/workflows/distill-video/status/${JOB_ID}")
if [[ -z "$WORKFLOW_ID" ]]; then
  echo "Distill job did not complete with workflow_id"
  exit 1
fi
echo "workflow_id=${WORKFLOW_ID}"

echo "[3/6] Get workflow ${WORKFLOW_ID}"
WORKFLOW_JSON="$(curl -fsS "${BASE_URL}/api/workflows/${WORKFLOW_ID}")"
python3 - <<'PY' "$WORKFLOW_JSON" "$WORKFLOW_ID"
import json, sys
payload = json.loads(sys.argv[1])
expected_id = sys.argv[2]
assert payload.get("workflow_id") == expected_id, payload
workflow = payload.get("workflow") or {}
assert workflow.get("steps"), payload
assert workflow.get("parameters") is not None, payload
print("workflow fetch ok")
PY

echo "[4/6] Create run"
RUN_JSON="$(curl -fsS -X POST "${BASE_URL}/api/runs" \
  -H "Content-Type: application/json" \
  -d "{\"workflow_id\": \"${WORKFLOW_ID}\", \"params\": {\"room\": \"Study Room 3A\", \"date\": \"2026-03-01\", \"time\": \"2:00 PM\"}}")"

RUN_ID="$(python3 - <<'PY' "$RUN_JSON"
import json, sys
payload = json.loads(sys.argv[1])
rid = payload.get("run_id")
assert rid, payload
print(rid)
PY
)"
echo "run_id=${RUN_ID}"

echo "[5/6] Poll run status"
LAST_STATUS=""
for i in 1 2 3 4 5; do
  RUN_STATE_JSON="$(curl -fsS "${BASE_URL}/api/runs/${RUN_ID}")"
  LAST_STATUS="$(python3 - <<'PY' "$RUN_STATE_JSON"
import json, sys
payload = json.loads(sys.argv[1])
required = ["run_id", "workflow_id", "status", "current_step", "total_steps", "logs"]
for key in required:
    assert key in payload, payload
print(payload["status"])
PY
)"
  echo "poll ${i}: status=${LAST_STATUS}"
  sleep 1
  if [[ "${LAST_STATUS}" == "succeeded" || "${LAST_STATUS}" == "failed" || "${LAST_STATUS}" == "waiting_for_auth" ]]; then
    break
  fi
done

echo "[6/6] Continue-after-auth endpoint"
if [[ "${LAST_STATUS}" == "waiting_for_auth" ]]; then
  CONTINUE_JSON="$(curl -fsS -X POST "${BASE_URL}/api/runs/${RUN_ID}/continue")"
  python3 - <<'PY' "$CONTINUE_JSON"
import json, sys
payload = json.loads(sys.argv[1])
assert payload.get("ok") is True, payload
print("continue ok")
PY
else
  echo "skipped (run status is ${LAST_STATUS})"
fi

echo "All API smoke checks passed."
