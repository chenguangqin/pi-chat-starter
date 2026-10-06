import { useCallback, useRef, useState } from "react";
import { sendMessageStream } from "../api";

export type StreamState = "idle" | "streaming" | "error";

export interface StreamResult {
  streamedText: string;
  messageId: string | null;
  state: StreamState;
  /**
   * What the agent is doing right now, from the backend's `status` events —
   * "thinking" while it reasons (no text is produced yet), "responding" once the
   * answer starts. Null when idle. The model can reason for ten seconds before the
   * first token, so without this the UI would show nothing at all for that whole time.
   */
  status: string | null;
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
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState("idle");
    setStatus(null);
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
          // Network chunks do not align with SSE frame boundaries, so a frame can be
          // split across two reads. Parsing each chunk on its own silently dropped any
          // such frame as malformed JSON — i.e. lost tokens, which with ~240 deltas per
          // reply happens routinely. Frames are separated by a blank line; accumulate
          // here and keep the trailing partial frame for the next read.
          let buffer = "";
          let doneReading = false;

          while (!doneReading) {
            const { done, value } = await reader.read();
            if (done) {
              doneReading = true;
              buffer += decoder.decode();
            } else {
              buffer += decoder.decode(value, { stream: true });
            }

            const frames = buffer.split("\n\n");
            // On the final read there is no trailing separator, so flush everything.
            buffer = doneReading ? "" : (frames.pop() ?? "");

            for (const frame of frames) {
              for (const evt of parseSSELines(frame)) {
                if (evt.type === "text_delta" && evt.delta) {
                  accumulated += evt.delta;
                  setStreamedText(accumulated);
                } else if (evt.type === "status") {
                  setStatus(evt.message ?? null);
                } else if (evt.type === "error") {
                  setError(evt.message ?? "Unknown error");
                  setState("error");
                  setStatus(null);
                  return;
                } else if (evt.type === "done") {
                  setMessageId(evt.message_id ?? null);
                  setStatus(null);
                  onDone?.(evt.message_id ?? "", accumulated);
                }
              }
            }
          }

          if (state !== "error") {
            setState("idle");
          }
          setStatus(null);
        } catch (err: unknown) {
          setStatus(null);
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

  return { streamedText, messageId, state, status, error, send, abort };
}
