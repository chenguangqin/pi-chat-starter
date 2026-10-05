import { useCallback, useState } from "react";
import type { Conversation } from "../api";

interface Props {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}

export default function ConversationList({
  conversations,
  activeId,
  onSelect,
  onCreate,
  onRename,
  onDelete,
}: Props) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const startRename = useCallback(
    (conv: Conversation, e: React.MouseEvent) => {
      e.stopPropagation();
      setEditingId(conv.id);
      setEditTitle(conv.title);
    },
    [],
  );

  const commitRename = useCallback(
    (id: string) => {
      const trimmed = editTitle.trim();
      if (trimmed) onRename(id, trimmed);
      setEditingId(null);
    },
    [editTitle, onRename],
  );

  const handleDelete = useCallback(
    (id: string, e: React.MouseEvent) => {
      e.stopPropagation();
      onDelete(id);
    },
    [onDelete],
  );

  return (
    <aside className="w-[280px] shrink-0 bg-gray-50 border-r border-gray-200 flex flex-col h-full">
      <div className="flex items-center justify-between p-4 pb-2">
        <h1 className="text-sm font-semibold text-gray-900">common_agent</h1>
        <button
          onClick={onCreate}
          className="px-3 py-1 text-[13px] bg-indigo-600 text-white rounded-md hover:bg-indigo-700 transition-colors duration-100 ease-out"
        >
          New
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-2">
        {conversations.length === 0 ? (
          <p className="text-[13px] text-gray-500 text-center mt-8">
            No conversations yet
          </p>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              onClick={() => onSelect(conv.id)}
              className={`group flex items-center gap-1 px-3 py-2 rounded-md cursor-pointer transition-colors duration-100 ease-out ${
                conv.id === activeId
                  ? "bg-indigo-50 border-l-2 border-indigo-600"
                  : "hover:bg-gray-100 border-l-2 border-transparent"
              }`}
            >
              {editingId === conv.id ? (
                <input
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={() => commitRename(conv.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename(conv.id);
                    if (e.key === "Escape") setEditingId(null);
                  }}
                  autoFocus
                  className="flex-1 text-[13px] bg-white border border-gray-200 rounded px-1 py-0.5 outline-none focus:border-indigo-600"
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  <span className="flex-1 text-[13px] text-gray-900 truncate leading-normal">
                    {conv.title}
                  </span>
                  <button
                    onClick={(e) => startRename(conv, e)}
                    className="hidden group-hover:inline text-[11px] text-gray-500 hover:text-gray-700 px-1"
                    title="Rename"
                  >
                    ✎
                  </button>
                  <button
                    onClick={(e) => handleDelete(conv.id, e)}
                    className="hidden group-hover:inline text-[11px] text-gray-500 hover:text-red-600 px-1"
                    title="Delete"
                  >
                    ✕
                  </button>
                </>
              )}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
