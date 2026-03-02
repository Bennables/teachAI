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
  workflowHint?: string,
  onProgress?: (step: string, pct: number) => void,
  onOutput?: (text: string) => void
): Promise<DistillVideoResponse> {
  // Step 1: upload the file and get a job ID back immediately.
  const formData = new FormData();
  formData.append("file", file);
  if (workflowHint) {
    formData.append("workflow_hint", workflowHint);
  }
  const { job_id } = await apiFetch<{ job_id: string }>(
    "/api/workflows/distill-video",
    { method: "POST", body: formData }
  );

  // Step 2: open the SSE stream and forward events to the caller.
  return new Promise<DistillVideoResponse>((resolve, reject) => {
    const es = new EventSource(
      `${API_BASE_URL}/api/workflows/distill-video/${job_id}/stream`
    );

    es.onmessage = (event) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse(event.data as string) as Record<string, unknown>;
      } catch {
        return;
      }

      if (data.type === "progress") {
        onProgress?.(data.step as string, data.pct as number);
      } else if (data.type === "text") {
        onOutput?.(data.content as string);
      } else if (data.type === "done") {
        es.close();
        resolve({
          workflow_id: data.workflow_id as string,
          workflow: data.workflow as DistillVideoResponse["workflow"],
        });
      } else if (data.type === "error") {
        es.close();
        reject(new Error((data.message as string) ?? "Extraction failed."));
      }
    };

    es.onerror = () => {
      es.close();
      reject(new Error("Lost connection to the progress stream."));
    };
  });
}

export async function postDistillVideoWithProgress(
  file: File,
  workflowHint: string | undefined,
  onUploadProgress: (percent: number) => void
): Promise<DistillVideoResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (workflowHint) {
    formData.append("workflow_hint", workflowHint);
  }

  return new Promise<DistillVideoResponse>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE_URL}/api/workflows/distill-video`);

    xhr.upload.onprogress = (event: ProgressEvent<EventTarget>) => {
      if (!event.lengthComputable) return;
      const percent = (event.loaded / event.total) * 100;
      onUploadProgress(Math.min(100, Math.max(0, percent)));
    };

    xhr.onerror = () => {
      reject(new Error("Upload failed due to a network error."));
    };

    xhr.onload = () => {
      let data: Record<string, unknown> = {};
      try {
        data = (JSON.parse(xhr.responseText) as Record<string, unknown>) ?? {};
      } catch {
        data = {};
      }

      if (xhr.status >= 200 && xhr.status < 300) {
        const workflowId = data.workflow_id;
        const workflow = data.workflow;
        if (typeof workflowId !== "string" || typeof workflow !== "object" || workflow == null) {
          reject(new Error("Malformed distill response from server."));
          return;
        }
        resolve({
          workflow_id: workflowId,
          workflow: workflow as WorkflowTemplate,
          saved_video_path:
            typeof data.saved_video_path === "string" ? data.saved_video_path : undefined
        });
        return;
      }

      const detail =
        (typeof data.detail === "string" && data.detail) ||
        `${xhr.status} ${xhr.statusText}`;
      reject(new Error(detail));
    };

    xhr.send(formData);
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

export interface ParsePromptBookingParams {
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

export interface ParsePromptGreenhouseDraft {
  application_url: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  address: string;
  submit: boolean;
}

export interface ParsePromptResponse {
  route: "booking" | "greenhouse" | "unknown";
  message: string;
  booking_job_id?: string | null;
  booking_params?: ParsePromptBookingParams | null;
  greenhouse_draft?: ParsePromptGreenhouseDraft | null;
  missing_fields: string[];
}

export async function postParsePrompt(text: string): Promise<ParsePromptResponse> {
  const response = await fetch(`${API_BASE_URL}/api/parseprompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text })
  });
  const data = (await response.json().catch(() => ({}))) as
    | ParsePromptResponse
    | { detail?: string };
  if (!response.ok) {
    throw new Error((data as { detail?: string }).detail ?? `${response.status} ${response.statusText}`);
  }
  return data as ParsePromptResponse;
}

export interface GreenhouseApplyParams {
  application_url: string;
  submit?: boolean;
}

export interface GreenhouseApplyResponse {
  success: boolean;
  message: string;
  submit_clicked?: boolean;
}

export async function postGreenhouseApply(
  params: GreenhouseApplyParams,
  resumeFile: File
): Promise<GreenhouseApplyResponse> {
  const form = new FormData();
  form.append("application_url", params.application_url);
  form.append("submit", String(params.submit ?? false));
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
