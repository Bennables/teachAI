"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Web Speech API (browser-only, types not in all TS libs)
type SpeechRecognitionInstance = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: { resultIndex: number; results: SpeechRecognitionResultList }) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
};

type VoiceInputProps = {
  onTranscript: (text: string) => void;
  disabled?: boolean;
  className?: string;
};

export function VoiceInput({ onTranscript, disabled, className = "" }: VoiceInputProps) {
  const [isListening, setIsListening] = useState(false);
  const [supported, setSupported] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);

  useEffect(() => {
    const win = typeof window !== "undefined" ? (window as unknown as Record<string, unknown>) : null;
    const Recognition = (win?.SpeechRecognition ?? win?.webkitSpeechRecognition) as (new () => SpeechRecognitionInstance) | undefined;
    setSupported(Boolean(Recognition));
    if (!Recognition) return;
    const rec = new Recognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";

    rec.onresult = (event: { resultIndex: number; results: SpeechRecognitionResultList }) => {
      const last = event.resultIndex;
      const result = event.results[last];
      if (result.isFinal) {
        const transcript = result[0].transcript.trim();
        if (transcript) onTranscript(transcript + " ");
      }
    };

    rec.onerror = (event: { error: string }) => {
      if (event.error === "not-allowed") {
        setIsListening(false);
      }
    };

    rec.onend = () => {
      setIsListening(false);
    };

    recognitionRef.current = rec;
    return () => {
      try {
        rec.abort();
      } catch {
        // ignore
      }
      recognitionRef.current = null;
    };
  }, [onTranscript]);

  const toggle = useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec) return;
    if (isListening) {
      rec.stop();
      setIsListening(false);
    } else {
      rec.start();
      setIsListening(true);
    }
  }, [isListening]);

  if (!supported) {
    return (
      <span className={`text-sm text-amber-600 ${className}`} role="status">
        Voice input not supported in this browser.
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={disabled}
      aria-label={isListening ? "Stop listening" : "Start voice input"}
      className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1 disabled:opacity-50 ${
        isListening
          ? "border-red-300 bg-red-50 text-red-700 hover:bg-red-100"
          : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50"
      } ${className}`}
    >
      {isListening ? (
        <>
          <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" aria-hidden />
          Listening…
        </>
      ) : (
        <>
          <MicIcon />
          Listen
        </>
      )}
    </button>
  );
}

function MicIcon() {
  return (
    <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden>
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z"
      />
    </svg>
  );
}
