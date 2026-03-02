"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { postGreenhouseApply, type GreenhouseApplyResponse } from "@/lib/api";

type GreenhouseForm = {
  application_url: string;
  submit: boolean;
  resume: File | null;
};

const initialForm: GreenhouseForm = {
  application_url: "",
  submit: false,
  resume: null,
};

export default function GreenhousePage() {
  const [form, setForm] = useState<GreenhouseForm>(initialForm);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GreenhouseApplyResponse | null>(null);

  const canSubmit = useMemo(
    () => Boolean(form.application_url.trim() && form.resume && !loading),
    [form.application_url, form.resume, loading]
  );

  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const url = qs.get("application_url");
    if (url) {
      setForm((prev) => ({ ...prev, application_url: url }));
    }
  }, []);

  function update<K extends keyof GreenhouseForm>(key: K, value: GreenhouseForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError(null);
    setResult(null);
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!form.resume) {
      setError("Please attach a resume file.");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await postGreenhouseApply(
        {
          application_url: form.application_url,
          submit: form.submit,
        },
        form.resume
      );
      setResult(response);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Greenhouse run failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="cyber-shell min-h-screen">
      <div className="parallax-layer parallax-far" aria-hidden="true" />
      <div className="parallax-layer parallax-mid" aria-hidden="true" />
      <div className="parallax-layer parallax-near" aria-hidden="true" />

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-5xl flex-col px-6 py-10">
        <header className="mb-6 flex items-center justify-between">
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">
            ← Workflows
          </Link>
          <p className="text-xs uppercase tracking-[0.26em] text-cyan-300/80">Greenhouse Runner</p>
        </header>

        <section className="workflow-card rounded-2xl p-8">
          <h1 className="text-3xl font-semibold text-slate-100">Apply With Link + Resume</h1>
          <p className="mt-3 max-w-2xl text-sm text-slate-300/80">
            Enter only the Greenhouse job URL and your resume. Backend Grok parsing will extract
            applicant details and answer the remaining form fields.
          </p>

          <form onSubmit={onSubmit} className="mt-8 space-y-5">
            <div>
              <label htmlFor="application_url" className="block text-sm font-medium text-slate-300">
                Greenhouse application URL
              </label>
              <input
                id="application_url"
                type="url"
                required
                value={form.application_url}
                onChange={(e) => update("application_url", e.target.value)}
                placeholder="https://boards.greenhouse.io/company/jobs/123456 or https://job-boards.eu.greenhouse.io/company/jobs/123"
                className="mt-1 w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
              />
            </div>

            <div>
              <label htmlFor="resume" className="block text-sm font-medium text-slate-300">
                Resume (PDF or DOC)
              </label>
              <input
                id="resume"
                type="file"
                accept=".pdf,.doc,.docx,application/pdf,application/msword"
                required={!form.resume}
                onChange={(e) => update("resume", e.target.files?.[0] ?? null)}
                className="mt-1 w-full text-sm text-slate-300 file:mr-2 file:rounded-md file:border-0 file:bg-cyan-500/20 file:px-3 file:py-1.5 file:text-cyan-100"
              />
              {form.resume ? (
                <p className="mt-1 text-xs text-cyan-100/80">Selected: {form.resume.name}</p>
              ) : null}
            </div>

            <label className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={form.submit}
                onChange={(e) => update("submit", e.target.checked)}
                className="h-4 w-4 rounded border-cyan-300/40 bg-slate-900 text-cyan-300"
              />
              Click final submit automatically
            </label>

            {error ? (
              <p className="text-sm text-rose-300" role="alert">
                {error}
              </p>
            ) : null}

            {result ? (
              <div
                className={`rounded-lg border p-3 text-sm ${
                  result.success
                    ? "border-emerald-300/30 bg-emerald-500/10 text-emerald-100"
                    : "border-amber-300/30 bg-amber-500/10 text-amber-100"
                }`}
              >
                <p>{result.message}</p>
                {typeof result.submit_clicked === "boolean" ? (
                  <p className="mt-1 text-xs opacity-80">Final submit clicked: {String(result.submit_clicked)}</p>
                ) : null}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={!canSubmit}
              className="cyber-button rounded-lg px-5 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Running Greenhouse automation..." : "Run Greenhouse automation"}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
