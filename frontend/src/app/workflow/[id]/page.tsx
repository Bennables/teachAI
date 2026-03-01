"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { getWorkflow, postRun, WorkflowByIdResponse } from "@/lib/api";

function getInputType(inputType: string): string {
  if (inputType === "number") return "number";
  if (inputType === "date") return "date";
  if (inputType === "time") return "time";
  return "text";
}

export default function WorkflowPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const workflowId = useMemo(() => params?.id ?? "", [params]);

  const [data, setData] = useState<WorkflowByIdResponse | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [startingRun, setStartingRun] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!workflowId) return;
    let active = true;

    async function loadWorkflow() {
      setLoading(true);
      setError(null);
      try {
        const workflowResponse = await getWorkflow(workflowId);
        if (!active) return;
        setData(workflowResponse);

        const defaults: Record<string, string> = {};
        workflowResponse.workflow.parameters.forEach((parameter) => {
          defaults[parameter.key] = parameter.example ?? "";
        });
        setParamValues(defaults);
      } catch (loadError) {
        if (!active) return;
        const message =
          loadError instanceof Error ? loadError.message : "Failed to load workflow.";
        setError(message);
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadWorkflow();
    return () => {
      active = false;
    };
  }, [workflowId]);

  async function startRun() {
    if (!data) return;
    setStartingRun(true);
    setError(null);
    try {
      const run = await postRun(data.workflow_id, paramValues);
      router.push(`/run/${run.run_id}`);
    } catch (runError) {
      const message = runError instanceof Error ? runError.message : "Failed to start run.";
      setError(message);
    } finally {
      setStartingRun(false);
    }
  }

  if (loading) {
    return (
      <main className="cyber-shell min-h-screen">
        <div className="parallax-layer parallax-far" aria-hidden="true" />
        <div className="parallax-layer parallax-mid" aria-hidden="true" />
        <div className="parallax-layer parallax-near" aria-hidden="true" />
        <div className="relative z-10 mx-auto max-w-4xl px-6 py-10">
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">← Workflows</Link>
          <p className="mt-8 text-slate-400">Loading workflow…</p>
        </div>
      </main>
    );
  }

  if (error || !data) {
    return (
      <main className="cyber-shell min-h-screen">
        <div className="parallax-layer parallax-far" aria-hidden="true" />
        <div className="parallax-layer parallax-mid" aria-hidden="true" />
        <div className="parallax-layer parallax-near" aria-hidden="true" />
        <div className="relative z-10 mx-auto max-w-4xl px-6 py-10">
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">← Workflows</Link>
          <p className="mt-8 text-rose-400">{error ?? "Workflow not found."}</p>
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
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">← Workflows</Link>
          <p className="mt-5 text-xs uppercase tracking-[0.3em] text-cyan-300/80">Workflow</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-100">{data.workflow.name}</h1>
          {data.workflow.description ? (
            <p className="mt-2 text-sm text-slate-300/80">{data.workflow.description}</p>
          ) : null}
          <p className="mt-1 text-xs text-slate-500">ID: {data.workflow_id}</p>
        </header>

        <section className="mb-6 rounded-xl border border-cyan-300/20 bg-slate-950/80 p-6 backdrop-blur-sm">
          <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-200/90">Parameters</h2>
          {data.workflow.parameters.length === 0 ? (
            <p className="mt-4 text-sm text-slate-400">No parameters required.</p>
          ) : (
            <div className="mt-5 space-y-5">
              {data.workflow.parameters.map((parameter) => {
                const inputType = parameter.input_type;
                return (
                  <div key={parameter.key}>
                    <label className="mb-2 block text-sm font-medium text-slate-300">
                      {parameter.description}
                    </label>
                    {inputType === "select" && parameter.options?.length ? (
                      <select
                        className="w-full rounded-lg border border-fuchsia-400/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-cyan-400"
                        value={paramValues[parameter.key] ?? ""}
                        onChange={(event) =>
                          setParamValues((current) => ({
                            ...current,
                            [parameter.key]: event.target.value
                          }))
                        }
                      >
                        {parameter.options.map((option) => (
                          <option key={option} value={option} className="bg-slate-900">
                            {option}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type={getInputType(inputType)}
                        className="w-full rounded-lg border border-fuchsia-400/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-cyan-400"
                        value={paramValues[parameter.key] ?? ""}
                        onChange={(event) =>
                          setParamValues((current) => ({
                            ...current,
                            [parameter.key]: event.target.value
                          }))
                        }
                        placeholder={parameter.example}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          )}
          {error ? <p className="mt-4 text-sm text-rose-400">{error}</p> : null}
          <button
            onClick={startRun}
            disabled={startingRun}
            className="cyber-button mt-6 rounded-lg px-5 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            {startingRun ? "Starting…" : "Start Run"}
          </button>
        </section>

        <section className="rounded-xl border border-cyan-300/20 bg-slate-950/80 p-6 backdrop-blur-sm">
          <h2 className="text-sm font-semibold uppercase tracking-[0.2em] text-cyan-200/90">Workflow JSON</h2>
          <pre className="mt-4 max-h-[420px] overflow-auto rounded-lg bg-slate-900/80 p-4 text-xs text-slate-300">
            {JSON.stringify(data.workflow, null, 2)}
          </pre>
        </section>
      </div>
    </main>
  );
}
