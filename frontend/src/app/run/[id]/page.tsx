"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { getRun, postContinueRun, RunResponse } from "@/lib/api";

const TERMINAL_STATUSES = new Set(["succeeded", "failed"]);

export default function RunMonitorPage() {
  const params = useParams<{ id: string }>();
  const runId = useMemo(() => params?.id ?? "", [params]);

  const [run, setRun] = useState<RunResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [continuing, setContinuing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isTerminalRef = useRef(false);

  const loadRun = useCallback(async () => {
    if (!runId) return;
    try {
      const response = await getRun(runId);
      setRun(response);
      setError(null);
    } catch (pollError) {
      const message = pollError instanceof Error ? pollError.message : "Failed to load run.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    isTerminalRef.current = !!run && TERMINAL_STATUSES.has(run.status);
  }, [run]);

  useEffect(() => {
    if (!runId) return;
    let timer: ReturnType<typeof setInterval> | undefined;
    void loadRun();
    timer = setInterval(() => {
      if (isTerminalRef.current) {
        return;
      }
      void loadRun();
    }, 2000);
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [runId, loadRun]);

  async function onContinue() {
    if (!runId) return;
    setContinuing(true);
    setError(null);
    try {
      await postContinueRun(runId);
      await loadRun();
    } catch (continueError) {
      const message =
        continueError instanceof Error ? continueError.message : "Failed to continue run.";
      setError(message);
    } finally {
      setContinuing(false);
    }
  }

  if (loading) {
    return <main className="p-6">Loading run...</main>;
  }

  if (error || !run) {
    return (
      <main className="p-6">
        <p className="text-red-600">{error ?? "Run not found."}</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <section className="rounded-lg border bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-bold">Run Monitor</h1>
          <p className="mt-2 text-sm text-gray-600">Run ID: {run.run_id}</p>
          <p className="mt-1 text-sm text-gray-600">Workflow: {run.workflow_id}</p>
          <p className="mt-3">
            <span className="rounded bg-gray-100 px-2 py-1 text-sm">
              Status: {run.status}
            </span>
          </p>
          <p className="mt-2 text-sm text-gray-700">
            Progress: {run.current_step}/{run.total_steps}
          </p>
          {run.status === "waiting_for_auth" ? (
            <button
              onClick={onContinue}
              disabled={continuing}
              className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {continuing ? "Continuing..." : "Continue after auth"}
            </button>
          ) : null}
        </section>

        <section className="rounded-lg border bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Logs</h2>
          {run.logs.length === 0 ? (
            <p className="mt-3 text-sm text-gray-500">No logs yet.</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {run.logs.map((log, index) => (
                <li key={`${log.ts}-${index}`} className="rounded border p-3 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-gray-800">{log.level.toUpperCase()}</span>
                    <span className="text-xs text-gray-500">{new Date(log.ts).toLocaleString()}</span>
                  </div>
                  <p className="mt-1 text-gray-700">{log.message}</p>
                  {log.step_index !== null && log.step_index !== undefined ? (
                    <p className="mt-1 text-xs text-gray-500">Step: {log.step_index}</p>
                  ) : null}
                  {log.screenshot_path ? (
                    <p className="mt-1 break-all text-xs text-gray-500">
                      Screenshot: {log.screenshot_path}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
