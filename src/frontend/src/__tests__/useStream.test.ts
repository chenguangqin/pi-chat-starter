import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useStream } from "../hooks/useStream";

function makeSSEChunk(events: Array<{ type: string; [k: string]: unknown }>): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
}

function createMockStream(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  let index = 0;
  return new ReadableStream({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]));
        index++;
      } else {
        controller.close();
      }
    },
  });
}

describe("useStream", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it("accumulates text deltas and fires onDone", async () => {
    const chunks = [
      makeSSEChunk([{ type: "text_delta", delta: "Hello" }]),
      makeSSEChunk([{ type: "text_delta", delta: " world" }]),
      makeSSEChunk([{ type: "done", message_id: "msg-1" }]),
    ];

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: createMockStream(chunks),
    });

    const onDone = vi.fn();
    const { result } = renderHook(() => useStream(onDone));

    expect(result.current.state).toBe("idle");

    await act(async () => {
      result.current.send("conv-1", "hi");
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(result.current.streamedText).toBe("Hello world");
    expect(result.current.state).toBe("idle");
    expect(onDone).toHaveBeenCalledWith("msg-1", "Hello world");
  });

  it("sets error state on error event", async () => {
    const chunks = [
      makeSSEChunk([{ type: "text_delta", delta: "partial" }]),
      makeSSEChunk([{ type: "error", message: "Model error" }]),
    ];

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: createMockStream(chunks),
    });

    const { result } = renderHook(() => useStream());

    await act(async () => {
      result.current.send("conv-1", "hi");
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(result.current.state).toBe("error");
    expect(result.current.error).toBe("Model error");
  });

  it("handles HTTP error responses", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => '{"detail":"Too many active conversations"}',
    });

    const { result } = renderHook(() => useStream());

    await act(async () => {
      result.current.send("conv-1", "hi");
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(result.current.state).toBe("error");
    expect(result.current.error).toContain("503");
  });

  it("handles abort gracefully", async () => {
    let pullCount = 0;
    const neverEndingStream = new ReadableStream<Uint8Array>({
      async pull(controller) {
        pullCount++;
        if (pullCount === 1) {
          const encoder = new TextEncoder();
          controller.enqueue(
            encoder.encode(
              makeSSEChunk([{ type: "text_delta", delta: "start" }]),
            ),
          );
        }
        await new Promise((r) => setTimeout(r, 5000));
      },
    });

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: neverEndingStream,
    });

    const { result } = renderHook(() => useStream());

    await act(async () => {
      result.current.send("conv-1", "hi");
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(result.current.state).toBe("streaming");

    act(() => {
      result.current.abort();
    });

    expect(result.current.state).toBe("idle");
  });
});
