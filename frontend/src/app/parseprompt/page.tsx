"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { VoiceInput } from "@/components/VoiceInput";
import { postParsePrompt } from "@/lib/api";

export default function ParsePromptPage() {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const onTranscript = useCallback((newText: string) => {
    setText((prev) => (prev + newText).trimStart());
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSent(false);
    try {
      await postParsePrompt(text);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send prompt");
    } finally {
      setLoading(false);
    }
  }

  return (
    
    <main className="min-h-screen bg-gray-50 px-6 py-16">
      <div className="mx-auto max-w-2xl rounded-lg border bg-white p-8 shadow-sm">
        <div className="mb-6 flex items-center gap-4">
          <Link
            href="/"
            className="text-gray-500 hover:text-gray-700"
            aria-label="Back to home"
          >
            ← Home
          </Link>
        </div>
        <h1 className="text-2xl font-bold text-gray-900">Parse prompt</h1>
        <p className="mt-1 text-gray-600">
          Send raw text to the backend. It will be stored and used for parsing.
        </p>
        <form onSubmit={onSubmit} className="mt-6">
          <div className="flex items-center justify-between gap-2">
            <label htmlFor="prompt-text" className="block text-sm font-medium text-gray-700">
              Raw text
            </label>
            
          </div>
          <textarea
            id="prompt-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste or type your prompt here..."
            rows={8}
            className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2 text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            disabled={loading}
          />
          {error && (
            <p className="mt-2 text-sm text-red-600" role="alert">
              {error}
            </p>
          )}
          {sent && (
            <p className="mt-2 text-sm text-green-600" role="status">
              Sent successfully.
            </p>
          )}
          <button
            type="submit"
            disabled={loading || !text.trim()}
            className="mt-4 inline-flex rounded-md bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50 disabled:pointer-events-none"
          >
            {loading ? "Sending…" : "Send to backend"}
          </button>
        </form>
      </div>
    </main>
  );
}
