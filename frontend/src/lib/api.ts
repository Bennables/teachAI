export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

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

export interface DistillVideoResponse {
  workflow_id: string;
  workflow: WorkflowTemplate;
  saved_video_path?: string;
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

export async function postDistillVideo(
  file: File,
  workflowHint?: string
): Promise<DistillVideoResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (workflowHint) {
    formData.append("workflow_hint", workflowHint);
  }
  return apiFetch<DistillVideoResponse>("/api/workflows/distill-video", {
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
