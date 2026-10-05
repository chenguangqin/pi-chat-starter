import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import type { Message } from "../api";

interface Props {
  messages: Message[];
  streamedText: string;
  isStreaming: boolean;
  error: string | null;
}

function UserBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] bg-indigo-50 rounded-xl px-4 py-3">
        <p className="text-[15px] leading-relaxed text-gray-900 whitespace-pre-wrap">
          {content}
        </p>
      </div>
    </div>
  );
}

function AssistantBubble({ content }: { content: string }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] bg-white border border-gray-200 rounded-xl px-4 py-3">
        <div className="text-[15px] leading-relaxed text-gray-900 prose prose-sm max-w-none">
          <ReactMarkdown>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

function ErrorBubble({ message }: { message: string }) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[80%] bg-red-50 border border-red-600 rounded-xl px-4 py-3">
        <p className="text-[13px] leading-normal text-red-600">{message}</p>
      </div>
    </div>
  );
}

export default function MessageThread({
  messages,
  streamedText,
  isStreaming,
  error,
}: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamedText]);

  if (messages.length === 0 && !isStreaming && !error) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-[13px] text-gray-500">Send a message to start</p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6">
      <div className="max-w-3xl mx-auto flex flex-col gap-4">
        {messages.map((msg) =>
          msg.role === "user" ? (
            <UserBubble key={msg.id} content={msg.content} />
          ) : (
            <AssistantBubble key={msg.id} content={msg.content} />
          ),
        )}
        {isStreaming && streamedText && (
          <AssistantBubble content={streamedText} />
        )}
        {error && <ErrorBubble message={error} />}
        <div ref={endRef} />
      </div>
    </div>
  );
}
