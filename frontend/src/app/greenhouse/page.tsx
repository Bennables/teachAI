"use client";

import { useState } from "react";
import Link from "next/link";
import { postGreenhouseApply, type GreenhouseApplyResponse } from "@/lib/api";

export default function GreenhousePage() {
  const [applicationUrl, setApplicationUrl] = useState("");
  const [resume, setResume] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GreenhouseApplyResponse | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!resume) {
      setError("Please select a resume file.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await postGreenhouseApply(applicationUrl, resume);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Apply failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="cyber-shell min-h-screen">
      <div className="parallax-layer parallax-far" aria-hidden="true" />
      <div className="parallax-layer parallax-mid" aria-hidden="true" />
      <div className="parallax-layer parallax-near" aria-hidden="true" />

      <div className="relative z-10 mx-auto max-w-lg px-6 py-10">
        <header className="mb-8">
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">← Workflows</Link>
          <p className="mt-5 text-xs uppercase tracking-[0.3em] text-cyan-300/80">Automation Tool</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-100">Greenhouse Apply</h1>
          <p className="mt-2 text-sm text-slate-300/80">
            Paste the job application URL and upload your resume.
          </p>
        </header>

        <div className="rounded-xl border border-cyan-300/20 bg-slate-950/80 p-6 backdrop-blur-sm">
          <form onSubmit={onSubmit} className="space-y-6">
            <div>
              <label htmlFor="application_url" className="mb-2 block text-sm font-medium text-slate-300">
                Application URL
              </label>
              <input
                id="application_url"
                type="url"
                required
                value={applicationUrl}
                onChange={(e) => { setApplicationUrl(e.target.value); setError(null); setResult(null); }}
                placeholder="https://boards.greenhouse.io/company/jobs/123456"
                className="w-full rounded-lg border border-fuchsia-400/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-cyan-400"
              />
            </div>

            <div>
              <label htmlFor="resume" className="mb-2 block text-sm font-medium text-slate-300">
                Resume
              </label>
              <label className="flex min-h-32 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-cyan-300/40 bg-slate-900/70 px-4 text-center text-sm text-slate-400 transition hover:border-fuchsia-400/70 hover:bg-slate-900">
                <input
                  id="resume"
                  type="file"
                  accept=".pdf,.doc,.docx,application/pdf,application/msword"
                  className="hidden"
                  onChange={(e) => { setResume(e.target.files?.[0] ?? null); setError(null); setResult(null); }}
                />
                {resume ? (
                  <>
                    <span className="text-base text-slate-100">{resume.name}</span>
                    <span className="mt-2 text-xs text-cyan-200">Click to replace</span>
                  </>
                ) : (
                  <>
                    <span>Drop your resume here</span>
                    <span className="mt-2 text-xs text-cyan-200">or click to browse — PDF or DOC</span>
                  </>
                )}
              </label>
            </div>

            {error && (
              <p className="text-sm text-rose-400" role="alert">{error}</p>
            )}

            {result && (
              <div
                className={`rounded-lg border p-3 text-sm ${
                  result.success
                    ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
                    : "border-amber-400/30 bg-amber-400/10 text-amber-200"
                }`}
                role="status"
              >
                {result.message}
                {result.submit_clicked != null && (
                  <span className="mt-1 block text-xs opacity-80">Submit clicked: {String(result.submit_clicked)}</span>
                )}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="cyber-button w-full rounded-lg px-4 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Applying…" : "Apply"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
