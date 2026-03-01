"use client";

import Link from "next/link";
import { useState } from "react";
import { postGreenhouseApply, type GreenhouseApplyResponse } from "@/lib/api";

type GreenhouseRunForm = {
  application_url: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  address: string;
  submit: boolean;
  resume: File | null;
};

const initialForm: GreenhouseRunForm = {
  application_url: "",
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  address: "",
  submit: false,
  resume: null
};

export default function GreenhouseRunPage() {
  const [form, setForm] = useState<GreenhouseRunForm>(initialForm);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("Idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GreenhouseApplyResponse | null>(null);

  function update<K extends keyof GreenhouseRunForm>(key: K, value: GreenhouseRunForm[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError(null);
  }

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!form.resume) {
      setError("Please attach a resume file.");
      return;
    }

    setIsRunning(true);
    setProgress(10);
    setStatusText("Uploading resume and starting browser session...");
    setError(null);
    setResult(null);

    const progressTicker = window.setInterval(() => {
      // Keep this below completion so users get live feedback during Selenium run time.
      setProgress((prev) => Math.min(92, prev + Math.max(1, (92 - prev) * 0.06)));
    }, 400);

    try {
      const response = await postGreenhouseApply(
        {
          application_url: form.application_url,
          first_name: form.first_name,
          last_name: form.last_name,
          email: form.email,
          phone: form.phone,
          address: form.address || undefined,
          submit: form.submit
        },
        form.resume
      );

      window.clearInterval(progressTicker);
      setProgress(100);
      setStatusText(response.success ? "Completed successfully." : "Completed with warnings.");
      setResult(response);
    } catch (runError) {
      window.clearInterval(progressTicker);
      setProgress(0);
      setStatusText("Failed");
      setError(runError instanceof Error ? runError.message : "Greenhouse run failed.");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-6 py-12 text-slate-100">
      <div className="mx-auto max-w-3xl rounded-2xl border border-cyan-400/30 bg-slate-900/70 p-8 shadow-[0_0_40px_rgba(34,211,238,0.15)]">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Run Greenhouse Program</h1>
          <Link
            href="/"
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:border-slate-500"
          >
            Back Home
          </Link>
        </div>

        <p className="mb-6 text-sm text-slate-300">
          Fill in applicant details, upload a resume, and run the Greenhouse autofill flow.
        </p>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-slate-300">Application URL *</label>
            <input
              type="url"
              required
              value={form.application_url}
              onChange={(e) => update("application_url", e.target.value)}
              placeholder="https://boards.greenhouse.io/company/jobs/12345"
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm text-slate-300">First Name *</label>
              <input
                type="text"
                required
                value={form.first_name}
                onChange={(e) => update("first_name", e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300">Last Name *</label>
              <input
                type="text"
                required
                value={form.last_name}
                onChange={(e) => update("last_name", e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm text-slate-300">Email *</label>
              <input
                type="email"
                required
                value={form.email}
                onChange={(e) => update("email", e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-300">Phone *</label>
              <input
                type="tel"
                required
                value={form.phone}
                onChange={(e) => update("phone", e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-300">Address</label>
            <input
              type="text"
              value={form.address}
              onChange={(e) => update("address", e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-400"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm text-slate-300">Resume (PDF or DOC) *</label>
            <input
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword"
              required={!form.resume}
              onChange={(e) => update("resume", e.target.files?.[0] ?? null)}
              className="block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300 file:mr-3 file:rounded-md file:border-0 file:bg-cyan-500/20 file:px-3 file:py-1.5 file:text-cyan-200"
            />
            {form.resume ? (
              <p className="mt-1 text-xs text-slate-400">Selected: {form.resume.name}</p>
            ) : null}
          </div>

          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={form.submit}
              onChange={(e) => update("submit", e.target.checked)}
              className="h-4 w-4"
            />
            Click final submit button automatically
          </label>

          <div className="rounded-lg border border-slate-700 bg-slate-950 p-3">
            <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
              <span>{statusText}</span>
              <span className="tabular-nums">{Math.round(progress)}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-800">
              <div
                className="h-2 rounded-full bg-gradient-to-r from-violet-500 to-cyan-400 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {error ? (
            <p className="rounded-md border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
              {error}
            </p>
          ) : null}

          {result ? (
            <div
              className={`rounded-md border px-3 py-2 text-sm ${
                result.success
                  ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-200"
                  : "border-amber-400/40 bg-amber-500/10 text-amber-200"
              }`}
            >
              <p>{result.message}</p>
              {typeof result.submit_clicked === "boolean" ? (
                <p className="mt-1 text-xs text-slate-300">
                  Final submit clicked: {String(result.submit_clicked)}
                </p>
              ) : null}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={isRunning}
            className="w-full rounded-lg bg-cyan-500 px-4 py-2 font-medium text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isRunning ? "Running Greenhouse Program..." : "Run Greenhouse Program"}
          </button>
        </form>
      </div>
    </main>
  );
}
