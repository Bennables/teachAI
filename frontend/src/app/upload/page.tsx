"use client";

import { DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { postDistillVideo, WS_BASE_URL, type DistillStatusEvent } from "@/lib/api";

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
  const [streamMessages, setStreamMessages] = useState<string[]>([]);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const helperText = useMemo(() => {
    if (!selectedFile) return "Drag and drop a video file here, or choose a file.";
    return `Selected: ${selectedFile.name}`;
  }, [selectedFile]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [streamMessages]);

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
    setStreamMessages(["Starting distillation..."]);
    try {
      const { job_id } = await postDistillVideo(selectedFile, "booking");
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
            setProgress({ percent: event.percent, message: frameMessage });
            setStreamMessages((prev) => [...prev, frameMessage]);
            if (event.status === "done" && event.workflow_id) {
              ws.close();
              router.push(`/workflow/${event.workflow_id}`);
              resolve();
              return;
            }
            if (event.status === "error") {
              ws.close();
              reject(new Error(event.error ?? event.message ?? "Distillation failed."));
            }
          } catch {
            // ignore malformed websocket frames
          }
        };

        ws.onerror = () => {
          setStreamMessages((prev) => [...prev, "WebSocket connection error."]);
          reject(new Error("Failed to connect to workflow status websocket."));
        };
      });
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : "Failed to distill video.";
      setError(message);
      setStreamMessages((prev) => [...prev, `Error: ${message}`]);
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

        {streamMessages.length > 0 ? (
          <div className="mt-4">
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-500">
              Live stream
            </p>
            <div className="max-h-40 overflow-y-auto rounded-md border bg-gray-50 p-3 font-mono text-xs text-gray-700">
              {streamMessages.map((message, index) => (
                <p key={`${index}-${message}`} className="mb-1 last:mb-0">
                  {message}
                </p>
              ))}
              <div ref={messagesEndRef} />
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
