"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  postGreenhouseApply,
  type GreenhouseApplyParams,
  type GreenhouseApplyResponse
} from "@/lib/api";

const EXAMPLE_JSON_URL = "/greenhouse-applicant-example.json";

const defaultForm: GreenhouseApplyParams & { resume: null | File } = {
  application_url: "",
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  address: "",
  submit: false,
  resume: null
};

function isApplicantJson(obj: unknown): obj is Record<string, unknown> {
  return typeof obj === "object" && obj !== null && !Array.isArray(obj);
}

function applyJsonToForm(obj: Record<string, unknown>): Partial<typeof defaultForm> {
  const out: Partial<typeof defaultForm> = {};
  if (typeof obj.application_url === "string") out.application_url = obj.application_url;
  if (typeof obj.first_name === "string") out.first_name = obj.first_name;
  if (typeof obj.last_name === "string") out.last_name = obj.last_name;
  if (typeof obj.email === "string") out.email = obj.email;
  if (typeof obj.phone === "string") out.phone = obj.phone;
  if (typeof obj.address === "string") out.address = obj.address;
  if (typeof obj.submit === "boolean") out.submit = obj.submit;
  return out;
}

export default function GreenhousePage() {
  const [form, setForm] = useState(defaultForm);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GreenhouseApplyResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
    setError(null);
    setResult(null);
  }

  function loadFromJson(obj: unknown) {
    if (!isApplicantJson(obj)) {
      setError("Invalid JSON: expected an object with application_url, first_name, etc.");
      return;
    }
    const patch = applyJsonToForm(obj);
    setForm((prev) => ({ ...prev, ...patch }));
    setError(null);
  }

  function onLoadExample() {
    fetch(EXAMPLE_JSON_URL)
      .then((r) => r.json())
      .then(loadFromJson)
      .catch(() => setError("Could not load example JSON."));
  }

  function onJsonFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const obj = JSON.parse(reader.result as string);
        loadFromJson(obj);
      } catch {
        setError("Invalid JSON in file.");
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.resume) {
      setError("Please select a resume file.");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await postGreenhouseApply(
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

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-5xl flex-col px-6 py-10">
        <div className="workflow-card rounded-2xl p-8">
          <div className="mb-6 flex items-center gap-4">
            <Link href="/" className="text-cyan-200/80 hover:text-cyan-100" aria-label="Back to home">
              ← Home
            </Link>
          </div>
          <h1 className="text-2xl font-semibold text-slate-100">Greenhouse job apply</h1>
          <p className="mt-2 text-sm text-slate-300/80">
            Enter a Greenhouse job application URL and your details. You can load data from a JSON
            file or the example below.
          </p>

          <div className="mt-6 rounded-lg border border-cyan-300/20 bg-slate-900/70 p-4">
            <p className="text-sm font-medium text-slate-200">Load from JSON</p>
            <p className="mt-1 text-xs text-slate-400">
              Use a JSON file with keys: application_url, first_name, last_name, email, phone,
              address (optional), submit (optional).
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onLoadExample}
                className="rounded-md border border-cyan-300/40 bg-cyan-400/10 px-3 py-1.5 text-sm font-medium text-cyan-100 hover:bg-cyan-400/20"
              >
                Load example
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".json,application/json"
                onChange={onJsonFileChange}
                className="hidden"
                aria-label="Upload JSON file"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="rounded-md border border-fuchsia-300/40 bg-fuchsia-400/10 px-3 py-1.5 text-sm font-medium text-fuchsia-100 hover:bg-fuchsia-400/20"
              >
                Choose JSON file...
              </button>
            </div>
          </div>

          <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="application_url" className="block text-sm font-medium text-slate-300">
              Greenhouse application URL *
            </label>
            <input
              id="application_url"
              type="url"
              required
              value={form.application_url}
              onChange={(e) => update("application_url", e.target.value)}
              placeholder="https://boards.greenhouse.io/company/jobs/123456"
              className="mt-1 w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="first_name" className="block text-sm font-medium text-slate-300">
                First name *
              </label>
              <input
                id="first_name"
                type="text"
                required
                value={form.first_name}
                onChange={(e) => update("first_name", e.target.value)}
                className="mt-1 w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
              />
            </div>
            <div>
              <label htmlFor="last_name" className="block text-sm font-medium text-slate-300">
                Last name *
              </label>
              <input
                id="last_name"
                type="text"
                required
                value={form.last_name}
                onChange={(e) => update("last_name", e.target.value)}
                className="mt-1 w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
              />
            </div>
          </div>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-300">
              Email *
            </label>
            <input
              id="email"
              type="email"
              required
              value={form.email}
              onChange={(e) => update("email", e.target.value)}
              className="mt-1 w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
            />
          </div>
          <div>
            <label htmlFor="phone" className="block text-sm font-medium text-slate-300">
              Phone *
            </label>
            <input
              id="phone"
              type="tel"
              required
              value={form.phone}
              onChange={(e) => update("phone", e.target.value)}
              className="mt-1 w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
            />
          </div>
          <div>
            <label htmlFor="address" className="block text-sm font-medium text-slate-300">
              Address (optional)
            </label>
            <input
              id="address"
              type="text"
              value={form.address}
              onChange={(e) => update("address", e.target.value)}
              className="mt-1 w-full rounded-lg border border-cyan-300/30 bg-slate-900 px-3 py-2 text-slate-100 outline-none transition focus:border-fuchsia-400"
            />
          </div>
          <div>
            <label htmlFor="resume" className="block text-sm font-medium text-slate-300">
              Resume (PDF or DOC) *
            </label>
            <input
              id="resume"
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword"
              required={!form.resume}
              onChange={(e) => update("resume", e.target.files?.[0] ?? null)}
              className="mt-1 w-full text-sm text-slate-300 file:mr-2 file:rounded-md file:border-0 file:bg-cyan-500/20 file:px-3 file:py-1.5 file:text-cyan-100"
            />
            {form.resume && (
              <p className="mt-1 text-xs text-slate-400">Selected: {form.resume.name}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input
              id="submit_after"
              type="checkbox"
              checked={form.submit}
              onChange={(e) => update("submit", e.target.checked)}
              className="h-4 w-4 rounded border-cyan-300/40 bg-slate-900 text-cyan-400 focus:ring-cyan-500"
            />
            <label htmlFor="submit_after" className="text-sm text-slate-300">
              Click submit button after filling (optional)
            </label>
          </div>

          {error && (
            <p className="text-sm text-rose-300" role="alert">
              {error}
            </p>
          )}
          {result && (
            <div
              className={`rounded-md border p-3 text-sm ${
                result.success
                  ? "border-emerald-300/40 bg-emerald-300/10 text-emerald-100"
                  : "border-amber-300/40 bg-amber-300/10 text-amber-100"
              }`}
              role="status"
            >
              {result.message}
              {result.submit_clicked != null && (
                <span className="block mt-1">Submit clicked: {String(result.submit_clicked)}</span>
              )}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="cyber-button w-full rounded-lg px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Applying…" : "Apply to Greenhouse"}
          </button>
          </form>
        </div>
      </div>
    </main>
  );
}
