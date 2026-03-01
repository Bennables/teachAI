"use client";

import { DragEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { postDistillVideo, getDistillStatusStreamUrl, type DistillStatusEvent } from "@/lib/api";

function isVideoFile(file: File): boolean {
  return file.type.startsWith("video/");
}

export default function UploadPage() {
  const router = useRouter();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState<{ percent: number; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const helperText = useMemo(() => {
    if (!selectedFile) return "Drag and drop a video file here, or choose a file.";
    return `Selected: ${selectedFile.name}`;
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
    setProgress({ percent: 0, message: "Starting…" });
    setError(null);
    try {
      const { job_id } = await postDistillVideo(selectedFile, "booking");
      const url = getDistillStatusStreamUrl(job_id);
      const res = await fetch(url);
      if (!res.ok || !res.body) throw new Error("Failed to open progress stream.");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event: DistillStatusEvent = JSON.parse(line.slice(6));
              setProgress({ percent: event.percent, message: event.message });
              if (event.status === "done" && event.workflow_id) {
                router.push(`/workflow/${event.workflow_id}`);
                return;
              }
              if (event.status === "error") {
                setError(event.error ?? "Distillation failed.");
                return;
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      }
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : "Failed to distill video.";
      setError(message);
    } finally {
      setLoading(false);
      setProgress(null);
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 px-6 py-10">
      <div className="mx-auto max-w-2xl rounded-lg border bg-white p-6 shadow-sm">
        <div className="mb-5">
          <Link href="/" className="text-sm text-gray-500 hover:text-gray-700">← Workflows</Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Upload Recording</h1>
        <p className="mt-2 text-sm text-gray-600">
          Upload a task recording to generate a workflow.
        </p>

        <div
          onDragEnter={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={(event) => {
            event.preventDefault();
            setDragActive(false);
          }}
          onDrop={onDrop}
          className={`mt-6 rounded-lg border-2 border-dashed p-8 text-center ${
            dragActive ? "border-blue-500 bg-blue-50" : "border-gray-300 bg-gray-50"
          }`}
        >
          <p className="text-sm text-gray-700">{helperText}</p>
          <label className="mt-4 inline-flex cursor-pointer rounded-md border px-3 py-2 text-sm">
            Choose File
            <input
              type="file"
              accept="video/*"
              className="hidden"
              onChange={(event) => onFilePicked(event.target.files?.[0] ?? null)}
            />
          </label>
        </div>

        {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}

        {progress ? (
          <div className="mt-4">
            <div className="mb-1 flex justify-between text-xs text-gray-500">
              <span>{progress.message}</span>
              <span>{Math.round(progress.percent)}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
              <div
                className="h-full rounded-full bg-blue-600 transition-[width] duration-300"
                style={{ width: `${Math.min(100, Math.max(0, progress.percent))}%` }}
              />
            </div>
          </div>
        ) : null}

        <button
          onClick={onSubmit}
          disabled={loading || !selectedFile}
          className="mt-6 rounded-md bg-blue-600 px-4 py-2 text-white disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Processing..." : "Distill Workflow"}
        </button>
      </div>
    </main>
  );
}
