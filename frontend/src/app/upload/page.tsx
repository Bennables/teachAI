"use client";

import { DragEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { postDistillVideo } from "@/lib/api";

function isVideoFile(file: File): boolean {
  return file.type.startsWith("video/");
}

export default function UploadPage() {
  const router = useRouter();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
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
    setError(null);
    try {
      const data = await postDistillVideo(selectedFile, "booking");
      router.push(`/workflow/${data.workflow_id}`);
    } catch (submitError) {
      const message =
        submitError instanceof Error ? submitError.message : "Failed to distill video.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 px-6 py-10">
      <div className="mx-auto max-w-2xl rounded-lg border bg-white p-6 shadow-sm">
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
