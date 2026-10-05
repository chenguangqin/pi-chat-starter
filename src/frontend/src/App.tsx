import { useCallback, useEffect, useState } from "react";
import type { Conversation, Message } from "./api";
import {
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  renameConversation,
} from "./api";
import ConversationList from "./components/ConversationList";
import MessageInput from "./components/MessageInput";
import MessageThread from "./components/MessageThread";
import { useStream } from "./hooks/useStream";

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);

  const loadConversations = useCallback(async () => {
    const convs = await listConversations();
    convs.sort(
      (a, b) =>
        new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
    setConversations(convs);
  }, []);

  const loadMessages = useCallback(async (convId: string) => {
    const msgs = await listMessages(convId);
    setMessages(msgs);
  }, []);

  const handleStreamDone = useCallback(
    (_messageId: string, _fullText: string) => {
      if (activeId) {
        loadMessages(activeId);
        loadConversations();
      }
    },
    [activeId, loadMessages, loadConversations],
  );

  const { streamedText, state, error, send, abort } =
    useStream(handleStreamDone);
  const isStreaming = state === "streaming";

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const handleSelect = useCallback(
    (id: string) => {
      if (isStreaming) return;
      setActiveId(id);
      loadMessages(id);
    },
    [isStreaming, loadMessages],
  );

  const handleCreate = useCallback(async () => {
    const conv = await createConversation();
    setActiveId(conv.id);
    setMessages([]);
    await loadConversations();
  }, [loadConversations]);

  const handleRename = useCallback(
    async (id: string, title: string) => {
      await renameConversation(id, title);
      await loadConversations();
    },
    [loadConversations],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      await deleteConversation(id);
      if (activeId === id) {
        setActiveId(null);
        setMessages([]);
      }
      await loadConversations();
    },
    [activeId, loadConversations],
  );

  const handleSend = useCallback(
    (content: string) => {
      if (!activeId) return;
      setMessages((prev) => [
        ...prev,
        {
          id: `temp-${Date.now()}`,
          role: "user" as const,
          content,
          created_at: new Date().toISOString(),
        },
      ]);
      send(activeId, content);
    },
    [activeId, send],
  );

  return (
    <div className="flex h-screen">
      <ConversationList
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelect}
        onCreate={handleCreate}
        onRename={handleRename}
        onDelete={handleDelete}
      />
      <main className="flex-1 flex flex-col min-w-0">
        {activeId ? (
          <>
            <MessageThread
              messages={messages}
              streamedText={streamedText}
              isStreaming={isStreaming}
              error={error}
            />
            <MessageInput
              onSend={handleSend}
              onStop={abort}
              isStreaming={isStreaming}
              disabled={!activeId}
            />
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-4">
            <p className="text-[13px] text-gray-500">
              No conversations yet
            </p>
            <button
              onClick={handleCreate}
              className="px-4 py-2 text-[13px] bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors duration-100 ease-out"
            >
              New conversation
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
