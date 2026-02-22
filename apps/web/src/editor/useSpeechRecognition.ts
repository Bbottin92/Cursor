import { useCallback, useMemo, useRef, useState } from "react";

type SpeechRecognitionType = typeof window & {
  SpeechRecognition?: any;
  webkitSpeechRecognition?: any;
};

function getSpeechRecognitionCtor(): any | null {
  const w = window as unknown as SpeechRecognitionType;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function useSpeechRecognition(options?: {
  onFinal?: (text: string) => void;
}) {
  const ctor = useMemo(() => {
    if (typeof window === "undefined") return null;
    return getSpeechRecognitionCtor();
  }, []);

  const recognitionRef = useRef<any | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);

  const isSupported = !!ctor;

  const start = useCallback(() => {
    if (!ctor) return;
    setError(null);

    const rec = new ctor();
    recognitionRef.current = rec;

    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";

    rec.onresult = (event: any) => {
      let interimText = "";
      let finalText = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        const t = r[0]?.transcript ?? "";
        if (r.isFinal) finalText += t;
        else interimText += t;
      }

      if (interimText) setInterim(interimText.trim());
      if (finalText) {
        const cleaned = finalText.trim();
        setInterim("");
        options?.onFinal?.(cleaned);
      }
    };

    rec.onerror = (e: any) => {
      setError(e?.error ? String(e.error) : "speech_error");
    };

    rec.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
    };

    setIsListening(true);
    rec.start();
  }, [ctor, options]);

  const stop = useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec) return;
    rec.stop();
  }, []);

  const reset = useCallback(() => {
    setInterim("");
    setError(null);
  }, []);

  return { isSupported, isListening, interim, error, start, stop, reset };
}

