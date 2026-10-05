import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  onSend: (content: string) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled: boolean;
}

export default function MessageInput({
  onSend,
  onStop,
  isStreaming,
  disabled,
}: Props) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [text, adjustHeight]);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  }, [text, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (isStreaming) return;
        handleSubmit();
      }
    },
    [handleSubmit, isStreaming],
  );

  return (
    <div className="border-t border-gray-200 bg-gray-50 px-6 py-3">
      <div className="max-w-3xl mx-auto flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Send a message…"
          rows={1}
          disabled={disabled && !isStreaming}
          className="flex-1 resize-none text-[15px] leading-normal bg-white border border-gray-200 rounded-md px-3 py-2 outline-none focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 disabled:opacity-50 placeholder:text-gray-500"
        />
        {isStreaming ? (
          <button
            onClick={onStop}
            className="shrink-0 w-9 h-9 flex items-center justify-center bg-indigo-600 hover:bg-indigo-700 text-white rounded-md transition-colors duration-100 ease-out"
            title="Stop"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="currentColor"
            >
              <rect width="14" height="14" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!text.trim() || disabled}
            className="shrink-0 w-9 h-9 flex items-center justify-center bg-indigo-600 hover:bg-indigo-700 text-white rounded-md transition-colors duration-100 ease-out disabled:opacity-40 disabled:cursor-not-allowed"
            title="Send"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M8 14V2M8 2L2 8M8 2L14 8" />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
