"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

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
        <div className="relative z-10 mx-auto w-full max-w-5xl px-6 py-10">
          <p className="text-slate-300">Loading workflow...</p>
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
        <div className="relative z-10 mx-auto w-full max-w-5xl px-6 py-10">
          <p className="text-rose-300">{error ?? "Workflow not found."}</p>
        </div>
      </main>
    );
  }

  return (
    <main className="cyber-shell min-h-screen">
      <div className="parallax-layer parallax-far" aria-hidden="true" />
      <div className="parallax-layer parallax-mid" aria-hidden="true" />
      <div className="parallax-layer parallax-near" aria-hidden="true" />

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-5xl flex-col px-6 py-10">
        <section className="workflow-card rounded-2xl p-6">
          <div className="mb-4">
            <Link href="/" className="text-cyan-200/80 hover:text-cyan-100">
              ← Home
            </Link>
          </div>
          <h1 className="text-2xl font-semibold text-slate-100">{data.workflow.name}</h1>
          <p className="mt-2 text-sm text-slate-300/80">{data.workflow.description}</p>
          <p className="mt-2 text-xs text-slate-400">Workflow ID: {data.workflow_id}</p>
        </section>

        <section className="mt-6 workflow-card rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-slate-100">Parameters</h2>
          <div className="mt-4 space-y-4">
            {data.workflow.parameters.map((parameter) => {
              const inputType = parameter.input_type;
              return (
                <div key={parameter.key}>
                  <label className="mb-1 block text-sm font-medium text-slate-300">
                    {parameter.description}
                  </label>
                  {inputType === "select" && parameter.options?.length ? (
                    <select
                      className="w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
                      value={paramValues[parameter.key] ?? ""}
                      onChange={(event) =>
                        setParamValues((current) => ({
                          ...current,
                          [parameter.key]: event.target.value
                        }))
                      }
                    >
                      {parameter.options.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={getInputType(inputType)}
                      className="w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
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
          <button
            onClick={startRun}
            disabled={startingRun}
            className="cyber-button mt-6 rounded-lg px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60"
          >
            {startingRun ? "Starting..." : "Start Run"}
          </button>
        </section>

        <section className="mt-6 workflow-card rounded-2xl p-6">
          <h2 className="text-lg font-semibold text-slate-100">Workflow JSON</h2>
          <pre className="mt-3 max-h-[420px] overflow-auto rounded-lg border border-cyan-300/20 bg-slate-900/80 p-4 text-xs text-cyan-100/90">
            {JSON.stringify(data.workflow, null, 2)}
          </pre>
        </section>
      </div>
    </main>
  );
}
