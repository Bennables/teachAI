"use client";

import { FormEvent, useMemo, useEffect, useRef } from "react";
import { postDistillVideo, WS_BASE_URL, type DistillStatusEvent } from "@/lib/api";
import { useCallback, useState } from "react";
import Link from "next/link";
import { VoiceInput } from "@/components/VoiceInput";
import { postParsePrompt } from "@/lib/api";

type WorkflowStatus = "ready" | "processing" | "failed";

type WorkflowCard = {
  id: string;
  name: string;
  updatedAt: string;
  status: WorkflowStatus;
};

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleString();
}

export default function HomePage() {
  const [workflows, setWorkflows] = useState<WorkflowCard[]>([]);
  const [isModalOpen, setModalOpen] = useState(false);
  const [workflowName, setWorkflowName] = useState("");
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [distilling, setDistilling] = useState(false);
  const [distillProgress, setDistillProgress] = useState<{ percent: number; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [useCaseNotes, setUseCaseNotes] = useState("");

  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  const onTranscript = useCallback((newText: string) => {
    setText((prev) => (prev + newText).trimStart());
  }, []);

  const onUseCaseTranscript = useCallback((newText: string) => {
    setUseCaseNotes((prev) => (prev + newText).trimStart());
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSent(false);
    try {
      await postParsePrompt(text);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send prompt");
    } finally {
      setLoading(false);
    }
  }

  const isDistillDisabled = useMemo(
    () => !workflowName.trim() || !videoFile || distilling,
    [workflowName, videoFile, distilling]
  );

  async function onDistillVideo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workflowName.trim() || !videoFile) return;

    setDistilling(true);
    setDistillProgress({ percent: 0, message: "Starting…" });
    setError(null);
    setNotice(null);

    try {
      const hint = useCaseNotes.trim()
        ? `${workflowName.trim()}. ${useCaseNotes.trim()}`
        : workflowName.trim();
      const { job_id } = await postDistillVideo(videoFile, hint);
      await new Promise<void>((resolve, reject) => {
        const ws = new WebSocket(`${WS_BASE_URL}/ws`);

        ws.onopen = () => {
          ws.send(JSON.stringify({ job_id }));
        };

        ws.onmessage = (msgEvent) => {
          try {
            const event = JSON.parse(msgEvent.data) as DistillStatusEvent;
            const frameMessage =
              event.current_frame != null && event.total_frames != null
                ? `Analyzing frame ${event.current_frame}/${event.total_frames}`
                : event.message;
            setDistillProgress({ percent: event.percent, message: frameMessage });

            if (event.status === "done" && event.workflow_id && event.workflow) {
              const newWorkflow: WorkflowCard = {
                id: event.workflow_id,
                name: event.workflow.name || workflowName.trim(),
                updatedAt: formatTime(Date.now()),
                status: "ready"
              };
              setWorkflows((current) => [newWorkflow, ...current]);
              setWorkflowName("");
              setVideoFile(null);
              setUseCaseNotes("");
              setModalOpen(false);
              ws.close();
              resolve();
            } else if (event.status === "error") {
              ws.close();
              reject(new Error(event.error ?? event.message ?? "Distillation failed."));
            }
          } catch {
            // ignore malformed websocket frames
          }
        };

        ws.onerror = () => {
          reject(new Error("Failed to connect to workflow status websocket."));
        };
      });
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Unable to distill video.";
      const backendUnavailable =
        message.includes("Failed to fetch") || message.includes("NetworkError");

      if (backendUnavailable) {
        const localWorkflow: WorkflowCard = {
          id: crypto.randomUUID(),
          name: workflowName.trim(),
          updatedAt: formatTime(Date.now()),
          status: "ready"
        };
        setWorkflows((current) => [localWorkflow, ...current]);
        setWorkflowName("");
        setVideoFile(null);
        setUseCaseNotes("");
        setModalOpen(false);
        setNotice("Backend unreachable. Workflow saved in local demo mode.");
      } else {
        setError(message);
      }
    } finally {
      setDistilling(false);
      setDistillProgress(null);
    }
  }

  return (
    <main className="cyber-shell min-h-screen">
      <div className="parallax-layer parallax-far" aria-hidden="true" />
      <div className="parallax-layer parallax-mid" aria-hidden="true" />
      <div className="parallax-layer parallax-near" aria-hidden="true" />

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-10">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-cyan-300/80">TeachOnce</p>
            <h1 className="mt-2 text-3xl font-semibold text-slate-100">Workflow Hub</h1>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/greenhouse"
              className="inline-flex h-11 items-center rounded-lg border border-cyan-400/30 bg-slate-900/70 px-4 text-sm font-medium text-cyan-200 transition hover:border-cyan-400/60 hover:bg-slate-900"
            >
              Greenhouse Apply
            </Link>
            <button
              onClick={() => setModalOpen(true)}
              className="cyber-button inline-flex h-11 min-w-11 items-center justify-center rounded-lg px-4"
            >
              <span className="text-2xl leading-none">+</span>
              <span className="ml-2 text-sm font-medium">Add Workflow</span>
            </button>
          </div>
        </header>
        {notice ? (
          <p className="mb-4 rounded-md border border-amber-300/40 bg-amber-300/10 px-3 py-2 text-sm text-amber-100">
            {notice}
          </p>
        ) : null}

        {workflows.length === 0 ? (
          <section className="empty-state-panel mt-10 flex flex-1 flex-col items-center justify-center rounded-2xl p-10 text-center">
            <p className="text-sm uppercase tracking-[0.24em] text-fuchsia-200/70">No workflows yet</p>
            <h2 className="mt-4 max-w-xl text-3xl font-semibold text-slate-100">
              Drop a process video to teach your first automation
            </h2>
            <p className="mt-3 max-w-lg text-sm text-slate-300/80">
              Name the workflow, distill it in the background, then run it from this hub.
            </p>
            <button
              onClick={() => setModalOpen(true)}
              className="cyber-button mt-8 inline-flex h-11 items-center rounded-lg px-6 text-sm font-medium"
            >
              Add Workflow
            </button>
          </section>
        ) : (
          <section className="grid gap-6 pb-8 sm:grid-cols-2 xl:grid-cols-3">
            {workflows.map((workflow) => (
              <Link
                key={workflow.id}
                href={`/workflow/${workflow.id}`}
                className="workflow-card block rounded-xl p-5"
              >
                <div className="flex items-center justify-between">
                  <p className="text-sm uppercase tracking-[0.2em] text-cyan-200/90">Workflow</p>
                  <span className="rounded-md border border-cyan-400/40 bg-cyan-400/10 px-2 py-0.5 text-xs text-cyan-200">
                    {workflow.status}
                  </span>
                </div>
                <h3 className="mt-4 text-xl font-semibold text-slate-100">{workflow.name}</h3>
                <p className="mt-3 text-sm text-slate-300/80">Updated {workflow.updatedAt}</p>
              </Link>
            ))}
          </section>
        )}
      </div>

      {isModalOpen ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm">
          <form
            onSubmit={onDistillVideo}
            className="w-full max-w-xl rounded-2xl border border-cyan-300/30 bg-slate-950/95 p-6 shadow-[0_0_60px_rgba(45,212,191,0.15)]"
          >
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-slate-100">Add New Workflow</h2>
              <button
                type="button"
                onClick={() => {
                  if (distilling) return;
                  setModalOpen(false);
                }}
                className="rounded-md px-2 py-1 text-slate-300 hover:bg-slate-800"
              >
                x
              </button>
            </div>

            <label className="mb-2 block text-sm font-medium text-slate-300">Workflow Name</label>
            <input
              type="text"
              value={workflowName}
              onChange={(event) => setWorkflowName(event.target.value)}
              className="mb-5 w-full rounded-lg border border-fuchsia-400/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-cyan-400"
              placeholder="Booking a library meeting room"
              required
            />

            <label className="mb-2 block text-sm font-medium text-slate-300">Upload Video</label>
            <label className="mb-2 flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-cyan-300/40 bg-slate-900/70 px-4 text-center text-sm text-slate-300 transition hover:border-fuchsia-400/70 hover:bg-slate-900">
              <input
                type="file"
                accept="video/*"
                className="hidden"
                onChange={(event) => setVideoFile(event.target.files?.[0] ?? null)}
              />
              {videoFile ? (
                <>
                  <p className="text-base text-slate-100">{videoFile.name}</p>
                  <p className="mt-2 text-xs text-cyan-200">Click to replace video</p>
                </>
              ) : (
                <>
                  <p>Drag and drop your workflow video</p>
                  <p className="mt-2 text-xs text-cyan-200">or click to browse files</p>
                </>
              )}
            </label>

            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between">
                <label className="block text-sm font-medium text-slate-300">
                  Describe Your Use Case
                </label>
                <VoiceInput
                  onTranscript={onUseCaseTranscript}
                  disabled={distilling}
                  className="listen-button rounded-md px-3 py-1.5 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-60"
                />
              </div>
              <textarea
                value={useCaseNotes}
                onChange={(event) => setUseCaseNotes(event.target.value)}
                rows={4}
                className="w-full rounded-lg border border-cyan-400/30 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition focus:border-fuchsia-400"
                placeholder="Example: Log into UCI library portal, choose Science Library, select 2:00 PM to 3:00 PM, then confirm reservation."
              />
            </div>

            {error ? <p className="mb-4 text-sm text-rose-300">{error}</p> : null}

            {distillProgress ? (
              <div className="mb-4">
                <div className="mb-1 flex justify-between text-xs text-slate-400">
                  <span>{distillProgress.message}</span>
                  <span>{Math.round(distillProgress.percent)}%</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-cyan-400 transition-[width] duration-300"
                    style={{ width: `${Math.min(100, Math.max(0, distillProgress.percent))}%` }}
                  />
                </div>
              </div>
            ) : null}

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  if (distilling) return;
                  setModalOpen(false);
                }}
                className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 hover:border-slate-500"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isDistillDisabled}
                className="cyber-button rounded-lg px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
              >
                {distilling ? "Distilling..." : "Distill Video"}
              </button>
            </div>


          </form>
        </div>
      ) : null}
      
    </main>
  );
}
