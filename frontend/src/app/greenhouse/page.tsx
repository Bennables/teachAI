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
    <main className="min-h-screen bg-gray-50 px-6 py-16">
      <div className="mx-auto max-w-2xl rounded-lg border bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-4">
          <Link href="/" className="text-gray-500 hover:text-gray-700" aria-label="Back to home">
            ← Home
          </Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Greenhouse job apply</h1>
        <p className="mt-1 text-gray-600">
          Enter a Greenhouse job application URL and your details. You can load data from a JSON
          file or the example below.
        </p>

        {/* Load from JSON */}
        <div className="mt-6 rounded-md border border-gray-200 bg-gray-50 p-4">
          <p className="text-sm font-medium text-gray-700">Load from JSON</p>
          <p className="mt-1 text-xs text-gray-500">
            Use a JSON file with keys: application_url, first_name, last_name, email, phone,
            address (optional), submit (optional).
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onLoadExample}
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
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
              className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Choose JSON file…
            </button>
          </div>
        </div>

        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="application_url" className="block text-sm font-medium text-gray-700">
              Greenhouse application URL *
            </label>
            <input
              id="application_url"
              type="url"
              required
              value={form.application_url}
              onChange={(e) => update("application_url", e.target.value)}
              placeholder="https://boards.greenhouse.io/company/jobs/123456"
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="first_name" className="block text-sm font-medium text-gray-700">
                First name *
              </label>
              <input
                id="first_name"
                type="text"
                required
                value={form.first_name}
                onChange={(e) => update("first_name", e.target.value)}
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label htmlFor="last_name" className="block text-sm font-medium text-gray-700">
                Last name *
              </label>
              <input
                id="last_name"
                type="text"
                required
                value={form.last_name}
                onChange={(e) => update("last_name", e.target.value)}
                className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email *
            </label>
            <input
              id="email"
              type="email"
              required
              value={form.email}
              onChange={(e) => update("email", e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label htmlFor="phone" className="block text-sm font-medium text-gray-700">
              Phone *
            </label>
            <input
              id="phone"
              type="tel"
              required
              value={form.phone}
              onChange={(e) => update("phone", e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label htmlFor="address" className="block text-sm font-medium text-gray-700">
              Address (optional)
            </label>
            <input
              id="address"
              type="text"
              value={form.address}
              onChange={(e) => update("address", e.target.value)}
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div>
            <label htmlFor="resume" className="block text-sm font-medium text-gray-700">
              Resume (PDF or DOC) *
            </label>
            <input
              id="resume"
              type="file"
              accept=".pdf,.doc,.docx,application/pdf,application/msword"
              required={!form.resume}
              onChange={(e) => update("resume", e.target.files?.[0] ?? null)}
              className="mt-1 w-full text-sm text-gray-600 file:mr-2 file:rounded-md file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-gray-700"
            />
            {form.resume && (
              <p className="mt-1 text-xs text-gray-500">Selected: {form.resume.name}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input
              id="submit_after"
              type="checkbox"
              checked={form.submit}
              onChange={(e) => update("submit", e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="submit_after" className="text-sm text-gray-700">
              Click submit button after filling (optional)
            </label>
          </div>

          {error && (
            <p className="text-sm text-red-600" role="alert">
              {error}
            </p>
          )}
          {result && (
            <div
              className={`rounded-md p-3 text-sm ${result.success ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"}`}
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
            className="w-full rounded-md bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:pointer-events-none"
          >
            {loading ? "Applying…" : "Apply to Greenhouse"}
          </button>
        </form>
      </div>
    </main>
  );
}
