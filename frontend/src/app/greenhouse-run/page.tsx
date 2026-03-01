"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { postGreenhouseApply, type GreenhouseApplyResponse } from "@/lib/api";
import { useSearchParams } from "next/navigation";

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
  const searchParams = useSearchParams();
  const [form, setForm] = useState<GreenhouseRunForm>(initialForm);
  const [isRunning, setIsRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("Idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GreenhouseApplyResponse | null>(null);

  useEffect(() => {
    const patch: Partial<GreenhouseRunForm> = {
      application_url: searchParams.get("application_url") ?? "",
      first_name: searchParams.get("first_name") ?? "",
      last_name: searchParams.get("last_name") ?? "",
      email: searchParams.get("email") ?? "",
      phone: searchParams.get("phone") ?? "",
      address: searchParams.get("address") ?? "",
      submit: searchParams.get("submit") === "true",
    };
    setForm((prev) => ({ ...prev, ...patch }));
  }, [searchParams]);

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
    <main className="min-h-screen bg-gray-50 px-6 py-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <section className="rounded-lg border bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center gap-4">
            <Link href="/" className="text-gray-500 hover:text-gray-700">
              ← Home
            </Link>
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Run Greenhouse Program</h1>
          <p className="mt-2 text-sm text-gray-600">
            Fill in applicant details, upload a resume, and run the Greenhouse autofill flow.
          </p>
        </section>

        <section className="rounded-lg border bg-white p-6 shadow-sm">
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Application URL *
              </label>
              <input
                type="url"
                required
                value={form.application_url}
                onChange={(e) => update("application_url", e.target.value)}
                placeholder="https://boards.greenhouse.io/company/jobs/12345"
                className="w-full rounded-md border px-3 py-2"
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  First Name *
                </label>
                <input
                  type="text"
                  required
                  value={form.first_name}
                  onChange={(e) => update("first_name", e.target.value)}
                  className="w-full rounded-md border px-3 py-2"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Last Name *
                </label>
                <input
                  type="text"
                  required
                  value={form.last_name}
                  onChange={(e) => update("last_name", e.target.value)}
                  className="w-full rounded-md border px-3 py-2"
                />
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Email *</label>
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => update("email", e.target.value)}
                  className="w-full rounded-md border px-3 py-2"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Phone *</label>
                <input
                  type="tel"
                  required
                  value={form.phone}
                  onChange={(e) => update("phone", e.target.value)}
                  className="w-full rounded-md border px-3 py-2"
                />
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Address</label>
              <input
                type="text"
                value={form.address}
                onChange={(e) => update("address", e.target.value)}
                className="w-full rounded-md border px-3 py-2"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Resume (PDF or DOC) *
              </label>
              <input
                type="file"
                accept=".pdf,.doc,.docx,application/pdf,application/msword"
                required={!form.resume}
                onChange={(e) => update("resume", e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-gray-600 file:mr-2 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-gray-700"
              />
              {form.resume ? (
                <p className="mt-1 text-xs text-gray-500">Selected: {form.resume.name}</p>
              ) : null}
            </div>

            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={form.submit}
                onChange={(e) => update("submit", e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              Click final submit button automatically
            </label>

            <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
              <div className="mb-2 flex items-center justify-between text-xs text-gray-500">
                <span>{statusText}</span>
                <span className="tabular-nums">{Math.round(progress)}%</span>
              </div>
              <div className="h-2 w-full rounded-full bg-gray-200">
                <div
                  className="h-2 rounded-full bg-blue-600 transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>

            {error ? (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            ) : null}

            {result ? (
              <div
                className={`rounded-md p-3 text-sm ${
                  result.success ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"
                }`}
              >
                <p>{result.message}</p>
                {typeof result.submit_clicked === "boolean" ? (
                  <p className="mt-1 text-xs">Final submit clicked: {String(result.submit_clicked)}</p>
                ) : null}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={isRunning}
              className="w-full rounded-md bg-blue-600 px-4 py-2 text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isRunning ? "Running Greenhouse Program..." : "Run Greenhouse Program"}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
