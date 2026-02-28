"use client";

import { useEffect, useMemo, useState } from "react";
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
    return <main className="p-6">Loading workflow...</main>;
  }

  if (error || !data) {
    return (
      <main className="p-6">
        <p className="text-red-600">{error ?? "Workflow not found."}</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <section className="rounded-lg border bg-white p-6 shadow-sm">
          <h1 className="text-2xl font-bold">{data.workflow.name}</h1>
          <p className="mt-2 text-sm text-gray-600">{data.workflow.description}</p>
          <p className="mt-2 text-xs text-gray-500">Workflow ID: {data.workflow_id}</p>
        </section>

        <section className="rounded-lg border bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Parameters</h2>
          <div className="mt-4 space-y-4">
            {data.workflow.parameters.map((parameter) => {
              const inputType = parameter.input_type;
              return (
                <div key={parameter.key}>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    {parameter.description}
                  </label>
                  {inputType === "select" && parameter.options?.length ? (
                    <select
                      className="w-full rounded-md border px-3 py-2"
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
                      className="w-full rounded-md border px-3 py-2"
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
            className="mt-6 rounded-md bg-blue-600 px-4 py-2 text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {startingRun ? "Starting..." : "Start Run"}
          </button>
        </section>

        <section className="rounded-lg border bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold">Workflow JSON</h2>
          <pre className="mt-3 max-h-[420px] overflow-auto rounded-md bg-gray-900 p-4 text-xs text-gray-100">
            {JSON.stringify(data.workflow, null, 2)}
          </pre>
        </section>
      </div>
    </main>
  );
}
