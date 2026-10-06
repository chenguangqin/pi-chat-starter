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

  it("keeps deltas whose SSE frame is split across network chunks", async () => {
    // Regression test. Network chunks do not align with SSE frame boundaries, and the
    // hook used to parse each chunk independently — every frame straddling a boundary
    // was dropped as malformed JSON, silently losing tokens. The other tests here all
    // happen to deliver one whole frame per chunk, so none of them caught it.
    const whole = makeSSEChunk([
      { type: "text_delta", delta: "Hello" },
      { type: "text_delta", delta: " split" },
      { type: "text_delta", delta: " world" },
      { type: "done", message_id: "msg-2" },
    ]);
    // Cut the payload at awkward offsets: mid-JSON, and between the two newlines
    // that terminate a frame.
    const cuts = [7, 23, 41, 58, 70];
    const chunks: string[] = [];
    let prev = 0;
    for (const cut of [...cuts, whole.length]) {
      if (cut > prev) chunks.push(whole.slice(prev, cut));
      prev = cut;
    }
    expect(chunks.length).toBeGreaterThan(3);

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      body: createMockStream(chunks),
    });

    const onDone = vi.fn();
    const { result } = renderHook(() => useStream(onDone));

    await act(async () => {
      result.current.send("conv-1", "hi");
      await new Promise((r) => setTimeout(r, 50));
    });

    expect(result.current.streamedText).toBe("Hello split world");
    expect(onDone).toHaveBeenCalledWith("msg-2", "Hello split world");
  });

  it("exposes status events and clears them on done", async () => {
    const chunks = [
      makeSSEChunk([{ type: "status", message: "thinking" }]),
      makeSSEChunk([{ type: "status", message: "responding" }]),
      makeSSEChunk([{ type: "text_delta", delta: "hi" }]),
      makeSSEChunk([{ type: "done", message_id: "msg-3" }]),
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

    expect(result.current.streamedText).toBe("hi");
    expect(result.current.status).toBeNull();
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
