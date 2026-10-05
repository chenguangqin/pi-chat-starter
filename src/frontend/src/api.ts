const HEADERS = {
  "X-Tenant-ID": "default",
  "X-User-ID": "default",
  "Content-Type": "application/json",
};

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { ...HEADERS, ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function listConversations(): Promise<Conversation[]> {
  return request("/api/conversations");
}

export function createConversation(
  title?: string,
): Promise<Conversation> {
  return request("/api/conversations", {
    method: "POST",
    body: title ? JSON.stringify({ title }) : undefined,
  });
}

export function getConversation(id: string): Promise<Conversation> {
  return request(`/api/conversations/${id}`);
}

export function renameConversation(
  id: string,
  title: string,
): Promise<Conversation> {
  return request(`/api/conversations/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title }),
  });
}

export function deleteConversation(id: string): Promise<void> {
  return request(`/api/conversations/${id}`, { method: "DELETE" });
}

export function listMessages(conversationId: string): Promise<Message[]> {
  return request(`/api/conversations/${conversationId}/messages`);
}

export function sendMessageStream(
  conversationId: string,
  content: string,
  signal?: AbortSignal,
): Promise<Response> {
  return fetch(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: HEADERS,
    body: JSON.stringify({ content }),
    signal,
  });
}
