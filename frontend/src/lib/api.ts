export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const WS_BASE_URL = API_BASE_URL.replace(/^http/, "ws");

export interface ParameterSpec {
  key: string;
  description: string;
  example: string;
  required: boolean;
  input_type: "text" | "date" | "time" | "number" | "select";
  options?: string[] | null;
}

export interface WorkflowTemplate {
  name: string;
  description?: string | null;
  start_url: string;
  category: string;
  tags: string[];
  parameters: ParameterSpec[];
  steps: Record<string, unknown>[];
}

/** Response from POST /distill-video when starting a background distill job */
export interface DistillVideoStartResponse {
  job_id: string;
}

/** Final payload when distill status stream sends status "done" */
export interface DistillVideoResponse {
  workflow_id: string;
  workflow: WorkflowTemplate;
  saved_video_path?: string;
}

export interface DistillStatusEvent {
  status: "queued" | "running" | "done" | "error";
  percent: number;
  message: string;
  current_frame?: number;
  total_frames?: number;
  workflow_id?: string;
  workflow?: WorkflowTemplate;
  saved_video_path?: string;
  error?: string;
}

export interface WorkflowByIdResponse {
  workflow_id: string;
  workflow: WorkflowTemplate;
  metadata: {
    created_at: string | null;
    run_count: number;
    success_rate: number;
  };
}

export interface CreateRunResponse {
  run_id: string;
}

export interface RunLogEntry {
  ts: string;
  level: "info" | "warn" | "error";
  message: string;
  step_index?: number | null;
  screenshot_path?: string | null;
}

export interface RunResponse {
  run_id: string;
  workflow_id: string;
  status:
    | "queued"
    | "running"
    | "waiting_for_auth"
    | "needs_user_disambiguation"
    | "succeeded"
    | "failed";
  current_step: number;
  total_steps: number;
  logs: RunLogEntry[];
  disambiguation?: Record<string, unknown> | null;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  const data = (await response.json().catch(() => ({}))) as
    | Record<string, unknown>
    | undefined;
  if (!response.ok) {
    const detail =
      (data && typeof data.detail === "string" && data.detail) ||
      `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return data as T;
}

/** Start video distillation; returns job_id. Use getDistillStatusStream for progress. */
export async function postDistillVideo(
  file: File,
  workflowHint?: string
): Promise<DistillVideoStartResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (workflowHint) {
    formData.append("workflow_hint", workflowHint);
  }
  return apiFetch<DistillVideoStartResponse>("/api/workflows/distill-video", {
    method: "POST",
    body: formData
  });
}

export async function getWorkflow(workflowId: string): Promise<WorkflowByIdResponse> {
  return apiFetch<WorkflowByIdResponse>(`/api/workflows/${workflowId}`);
}

export async function postRun(
  workflowId: string,
  params: Record<string, string>
): Promise<CreateRunResponse> {
  return apiFetch<CreateRunResponse>("/api/runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workflow_id: workflowId, params })
  });
}

export async function getRun(runId: string): Promise<RunResponse> {
  return apiFetch<RunResponse>(`/api/runs/${runId}`);
}

export async function postContinueRun(runId: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/api/runs/${runId}/continue`, {
    method: "POST"
  });
}

export async function postParsePrompt(text: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/parseprompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(data.detail ?? `${response.status} ${response.statusText}`);
  }
}

export interface GreenhouseApplyResponse {
  success: boolean;
  message: string;
  submit_clicked?: boolean;
}

// ── Booking (WebSocket) ──────────────────────────────────────────────────────

export interface BookingParams {
  library: string;
  booking_date: string;
  room_keyword: string;
  booking_time: string;
  duration_minutes: number;
  full_name: string;
  email: string;
  affiliation: string;
  purpose_for_reservation_covid_19: string;
}

export interface BookingWsRequest {
  params: BookingParams;
  max_auth_resumes?: number;
  headless?: boolean;
}

export type BookingWsMessageType = "started" | "log" | "done" | "error";

export interface BookingWsMessage {
  type: BookingWsMessageType;
  run_id?: string;
  message?: string;
  status?: "success" | "error" | "timeout";
  execution_time_ms?: number;
  error?: string | null;
}

export async function postGreenhouseApply(
  applicationUrl: string,
  resumeFile: File
): Promise<GreenhouseApplyResponse> {
  const form = new FormData();
  form.append("application_url", applicationUrl);
  form.append("resume", resumeFile);

  const response = await fetch(`${API_BASE_URL}/api/greenhouse/apply`, {
    method: "POST",
    body: form
  });
  const data = (await response.json().catch(() => ({}))) as
    | GreenhouseApplyResponse
    | { detail?: string };
  if (!response.ok) {
    const detail =
      typeof (data as { detail?: string }).detail === "string"
        ? (data as { detail: string }).detail
        : `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return data as GreenhouseApplyResponse;
}
