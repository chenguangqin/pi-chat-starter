import { useCallback, useRef, useState } from "react";
import { sendMessageStream } from "../api";

export type StreamState = "idle" | "streaming" | "error";

export interface StreamResult {
  streamedText: string;
  messageId: string | null;
  state: StreamState;
  error: string | null;
  send: (conversationId: string, content: string) => void;
  abort: () => void;
}

interface SSEEvent {
  type: string;
  delta?: string;
  message_id?: string;
  message?: string;
}

function parseSSELines(text: string): SSEEvent[] {
  const events: SSEEvent[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("data: ")) {
      try {
        events.push(JSON.parse(trimmed.slice(6)) as SSEEvent);
      } catch {
        // skip malformed lines
      }
    }
  }
  return events;
}

export function useStream(
  onDone?: (messageId: string, fullText: string) => void,
): StreamResult {
  const [streamedText, setStreamedText] = useState("");
  const [messageId, setMessageId] = useState<string | null>(null);
  const [state, setState] = useState<StreamState>("idle");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState("idle");
  }, []);

  const send = useCallback(
    (conversationId: string, content: string) => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setStreamedText("");
      setMessageId(null);
      setError(null);
      setState("streaming");

      let accumulated = "";

      (async () => {
        try {
          const res = await sendMessageStream(
            conversationId,
            content,
            controller.signal,
          );

          if (!res.ok) {
            const body = await res.text();
            throw new Error(`${res.status}: ${body}`);
          }

          const reader = res.body?.getReader();
          if (!reader) throw new Error("No response body");

          const decoder = new TextDecoder();
          let doneReading = false;

          while (!doneReading) {
            const { done, value } = await reader.read();
            if (done) {
              doneReading = true;
              break;
            }

            const chunk = decoder.decode(value, { stream: true });
            const events = parseSSELines(chunk);

            for (const evt of events) {
              if (evt.type === "text_delta" && evt.delta) {
                accumulated += evt.delta;
                setStreamedText(accumulated);
              } else if (evt.type === "error") {
                setError(evt.message ?? "Unknown error");
                setState("error");
                return;
              } else if (evt.type === "done") {
                setMessageId(evt.message_id ?? null);
                onDone?.(evt.message_id ?? "", accumulated);
              }
            }
          }

          if (state !== "error") {
            setState("idle");
          }
        } catch (err: unknown) {
          if (err instanceof DOMException && err.name === "AbortError") {
            setState("idle");
            return;
          }
          const msg =
            err instanceof Error ? err.message : "Stream failed";
          setError(msg);
          setState("error");
        }
      })();
    },
    [onDone, state],
  );

  return { streamedText, messageId, state, error, send, abort };
}
