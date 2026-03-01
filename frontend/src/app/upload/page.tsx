"use client";

import { DragEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { postDistillVideo } from "@/lib/api";

function isVideoFile(file: File): boolean {
  return file.type.startsWith("video/");
}

export default function UploadPage() {
  const router = useRouter();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [progressStep, setProgressStep] = useState("");
  const [progressPct, setProgressPct] = useState(0);
  const [parseOutputs, setParseOutputs] = useState<string[]>([]);
  const [createdWorkflowId, setCreatedWorkflowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const helperText = useMemo(() => {
    if (!selectedFile) return "Drag and drop a video file here, or choose a file.";
    return selectedFile.name;
  }, [selectedFile]);

  function onFilePicked(file: File | null) {
    if (!file) return;
    if (!isVideoFile(file)) {
      setError("Please upload a video file.");
      return;
    }
    setError(null);
    setSelectedFile(file);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files?.[0] ?? null;
    onFilePicked(file);
  }

  async function onSubmit() {
    if (!selectedFile) {
      setError("Please select a video first.");
      return;
    }

    setLoading(true);
    setProgressStep("Uploading video…");
    setProgressPct(0);
    setParseOutputs([]);
    setCreatedWorkflowId(null);
    setError(null);

    try {
      const data = await postDistillVideo(
        selectedFile,
        "booking",
        (step, pct) => {
          setProgressStep(step);
          setProgressPct(pct);
        }
      );

      const paramLines = data.workflow.parameters.map(
        (p, i) =>
          `Param ${i + 1}: ${p.key}${p.example ? ` (e.g. ${p.example})` : ""}`
      );
      const stepLines = data.workflow.steps.map(
        (s, i) => `Step ${i + 1}: ${JSON.stringify(s)}`
      );
      setParseOutputs([...paramLines, ...stepLines]);
      setCreatedWorkflowId(data.workflow_id);
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : "Failed to distill video.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="cyber-shell min-h-screen">
      <div className="parallax-layer parallax-far" aria-hidden="true" />
      <div className="parallax-layer parallax-mid" aria-hidden="true" />
      <div className="parallax-layer parallax-near" aria-hidden="true" />

      <div className="relative z-10 mx-auto max-w-2xl px-6 py-10">
        <header className="mb-8">
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">← Workflows</Link>
          <p className="mt-5 text-xs uppercase tracking-[0.3em] text-cyan-300/80">Distill</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-100">Upload Recording</h1>
          <p className="mt-2 text-sm text-slate-300/80">Upload a task recording to generate a workflow.</p>
        </header>

        <div className="rounded-xl border border-cyan-300/20 bg-slate-950/80 p-6 backdrop-blur-sm">
          <div
            onDragEnter={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={(e) => { e.preventDefault(); setDragActive(false); }}
            onDrop={onDrop}
            className={`flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed px-4 text-center text-sm transition ${
              dragActive
                ? "border-fuchsia-400/70 bg-slate-900"
                : "border-cyan-300/40 bg-slate-900/70 hover:border-fuchsia-400/70 hover:bg-slate-900"
            }`}
            onClick={() => document.getElementById("file-input")?.click()}
          >
            <input
              id="file-input"
              type="file"
              accept="video/*"
              className="hidden"
              onChange={(e) => onFilePicked(e.target.files?.[0] ?? null)}
            />
            {selectedFile ? (
              <>
                <p className="text-base text-slate-100">{helperText}</p>
                <p className="mt-2 text-xs text-cyan-200">Click to replace video</p>
              </>
            ) : (
              <>
                <p className="text-slate-300">Drag and drop your workflow video</p>
                <p className="mt-2 text-xs text-cyan-200">or click to browse files</p>
              </>
            )}
          </div>

          {(loading || progressPct > 0) ? (
            <div className="mt-5 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">{progressStep || "Starting…"}</span>
                <span className="tabular-nums text-cyan-300/80">{progressPct}%</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-500"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
            </div>
          ) : null}

          {parseOutputs.length > 0 ? (
            <div className="mt-5">
              <p className="mb-2 text-xs uppercase tracking-[0.2em] text-cyan-200/90">Parsed Output</p>
              <div className="max-h-48 overflow-y-auto rounded-lg border border-cyan-300/20 bg-slate-900/80 p-3 font-mono text-xs text-cyan-100/90">
                {parseOutputs.map((line, i) => (
                  <p key={i} className="mb-1 last:mb-0">{line}</p>
                ))}
              </div>
            </div>
          ) : null}

          {error ? <p className="mt-4 text-sm text-rose-400">{error}</p> : null}

          <div className="mt-6 flex items-center gap-3">
            <button
              onClick={onSubmit}
              disabled={loading || !selectedFile}
              className="cyber-button rounded-lg px-5 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Processing…" : "Distill Workflow"}
            </button>
            {createdWorkflowId ? (
              <button
                onClick={() => router.push(`/workflow/${createdWorkflowId}`)}
                className="rounded-lg border border-cyan-400/40 px-4 py-2.5 text-sm font-medium text-cyan-200 transition hover:border-cyan-400/70"
              >
                Open Workflow →
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  );
}
