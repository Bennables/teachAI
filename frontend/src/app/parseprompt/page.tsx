"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { VoiceInput } from "@/components/VoiceInput";
import { postParsePrompt, type ParsePromptResponse } from "@/lib/api";

export default function ParsePromptPage() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ParsePromptResponse | null>(null);

  const onTranscript = useCallback((newText: string) => {
    setText((prev) => (prev + newText).trimStart());
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const parsed = await postParsePrompt(text);
      setResult(parsed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send prompt");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="cyber-shell min-h-screen">
      <div className="parallax-layer parallax-far" aria-hidden="true" />
      <div className="parallax-layer parallax-mid" aria-hidden="true" />
      <div className="parallax-layer parallax-near" aria-hidden="true" />

      <div className="relative z-10 mx-auto max-w-2xl px-6 py-10">
        <header className="mb-8">
          <Link href="/" className="text-sm text-cyan-300/70 transition hover:text-cyan-200">← Workflows</Link>
          <p className="mt-5 text-xs uppercase tracking-[0.3em] text-cyan-300/80">Dev Tool</p>
          <h1 className="mt-2 text-3xl font-semibold text-slate-100">Parse Prompt</h1>
          <p className="mt-2 text-sm text-slate-300/80">Route text into booking or greenhouse actions.</p>
        </header>

        <div className="rounded-xl border border-cyan-300/20 bg-slate-950/80 p-6 backdrop-blur-sm">
          <form onSubmit={onSubmit} className="space-y-5">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label htmlFor="prompt-text" className="text-sm font-medium text-slate-300">
                  Raw text
                </label>
                <VoiceInput
                  onTranscript={onTranscript}
                  disabled={loading}
                  className="listen-button rounded-md px-3 py-1.5 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-60"
                />
              </div>
              <textarea
                id="prompt-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste or type your prompt here…"
                rows={8}
                disabled={loading}
                className="w-full rounded-lg border border-fuchsia-400/30 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-cyan-400 disabled:opacity-60"
              />
            </div>

            {error ? (
              <p className="text-sm text-rose-400" role="alert">{error}</p>
            ) : null}

            {result ? (
              <div className="rounded-lg border border-emerald-300/30 bg-emerald-500/10 p-3 text-sm text-emerald-200" role="status">
                <p>{result.message}</p>
                <p className="mt-1 text-xs text-emerald-100/80">Route: {result.route}</p>
                {result.booking_job_id ? (
                  <p className="mt-1 text-xs text-emerald-100/80">Booking job: {result.booking_job_id}</p>
                ) : null}
                {result.missing_fields.length ? (
                  <p className="mt-1 text-xs text-amber-200">
                    Missing fields: {result.missing_fields.join(", ")}
                  </p>
                ) : null}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={loading || !text.trim()}
              className="cyber-button rounded-lg px-5 py-2.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Sending…" : "Send to backend"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
