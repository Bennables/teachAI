"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

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

  const isTerminal = !!run && TERMINAL_STATUSES.has(run.status);

  if (loading) {
    return (
      <main className="cyber-shell min-h-screen">
        <div className="parallax-layer parallax-far" aria-hidden="true" />
        <div className="parallax-layer parallax-mid" aria-hidden="true" />
        <div className="parallax-layer parallax-near" aria-hidden="true" />
        <div className="relative z-10 mx-auto max-w-4xl px-6 py-10">
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">← Workflows</Link>
          <p className="mt-8 text-slate-400">Loading run…</p>
        </div>
      </main>
    );
  }

  if (error || !run) {
    return (
      <main className="cyber-shell min-h-screen">
        <div className="parallax-layer parallax-far" aria-hidden="true" />
        <div className="parallax-layer parallax-mid" aria-hidden="true" />
        <div className="parallax-layer parallax-near" aria-hidden="true" />
        <div className="relative z-10 mx-auto max-w-4xl px-6 py-10">
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">← Workflows</Link>
          <p className="mt-8 text-rose-400">{error ?? "Run not found."}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="cyber-shell min-h-screen">
      <div className="parallax-layer parallax-far" aria-hidden="true" />
      <div className="parallax-layer parallax-mid" aria-hidden="true" />
      <div className="parallax-layer parallax-near" aria-hidden="true" />

      <div className="relative z-10 mx-auto max-w-4xl px-6 py-10">
        <header className="mb-8">
          <Link
            href={`/workflow/${run.workflow_id}`}
            className="text-sm text-cyan-300/70 transition hover:text-cyan-200"
          >
            ← Back to Workflow
          </Link>
          <p className="mt-5 text-xs uppercase tracking-[0.3em] text-cyan-300/80">Run</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-100">Run Monitor</h1>
          <p className="mt-1 text-xs text-slate-500">{run.run_id}</p>
        </header>

        <div className="space-y-6">
          <section className="rounded-xl border border-cyan-300/20 bg-slate-950/80 p-6 backdrop-blur-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`rounded-md px-3 py-1 text-sm font-medium ${
                  run.status === "succeeded"
                    ? "border border-emerald-400/40 bg-emerald-400/10 text-emerald-300"
                    : run.status === "failed"
                    ? "border border-rose-400/40 bg-rose-400/10 text-rose-300"
                    : run.status === "waiting_for_auth"
                    ? "border border-amber-400/40 bg-amber-400/10 text-amber-300"
                    : "border border-cyan-400/30 bg-cyan-400/10 text-cyan-300"
                }`}
              >
                {run.status}
              </span>
              <span className="text-sm text-slate-400">
                Step {run.current_step} / {run.total_steps}
              </span>
            </div>

            {!isTerminal && run.total_steps > 0 ? (
              <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-500"
                  style={{ width: `${Math.round((run.current_step / run.total_steps) * 100)}%` }}
                />
              </div>
            ) : null}

            {run.status === "waiting_for_auth" ? (
              <button
                onClick={onContinue}
                disabled={continuing}
                className="cyber-button mt-5 rounded-lg px-5 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
              >
                {continuing ? "Continuing…" : "Continue after auth"}
              </button>
            ) : null}

            {isTerminal ? (
              <div className="mt-5 flex items-center gap-3 border-t border-cyan-300/10 pt-5">
                <Link
                  href={`/workflow/${run.workflow_id}`}
                  className="cyber-button rounded-lg px-4 py-2 text-sm font-medium"
                >
                  Run Again
                </Link>
                <Link
                  href="/"
                  className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 transition hover:border-slate-500"
                >
                  ← Workflows
                </Link>
              </div>
            ) : null}
          </section>

          <section className="rounded-xl border border-cyan-300/20 bg-slate-950/80 p-6 backdrop-blur-sm">
            <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-200/90">Logs</h2>
            {run.logs.length === 0 ? (
              <p className="mt-4 text-sm text-slate-500">No logs yet.</p>
            ) : (
              <ul className="mt-4 space-y-2">
                {run.logs.map((log, index) => (
                  <li
                    key={`${log.ts}-${index}`}
                    className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span
                        className={`text-xs font-semibold uppercase ${
                          log.level === "error"
                            ? "text-rose-400"
                            : log.level === "warn"
                            ? "text-amber-400"
                            : "text-cyan-400"
                        }`}
                      >
                        {log.level}
                      </span>
                      <span className="text-xs text-slate-500">{new Date(log.ts).toLocaleString()}</span>
                    </div>
                    <p className="mt-1 text-slate-300">{log.message}</p>
                    {log.step_index !== null && log.step_index !== undefined ? (
                      <p className="mt-1 text-xs text-slate-500">Step {log.step_index}</p>
                    ) : null}
                    {log.screenshot_path ? (
                      <p className="mt-1 break-all text-xs text-slate-500">{log.screenshot_path}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
