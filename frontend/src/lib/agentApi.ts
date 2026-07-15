/**
 * 智能体接口客户端
 * 封装后端 /api/query SSE 流式接口请求与事件解析逻辑，
 * 以及会话历史的 CRUD 接口。
 */
import type { AgentEvent, Conversation, ConversationDetail } from "../types/agent";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

type QueryOptions = {
  signal?: AbortSignal;
  onEvent: (event: AgentEvent) => void;
};

export async function streamQuery(
  query: string,
  options: QueryOptions,
  conversationId?: string | null,
) {
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ query, conversation_id: conversationId || undefined }),
    signal: options.signal,
  });

  if (!response.ok) {
    throw new Error(`接口请求失败：HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error("浏览器未返回可读取的流式响应。");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split(/\n\n/);
    buffer = chunks.pop() ?? "";

    for (const chunk of chunks) {
      const event = parseSseChunk(chunk);
      if (event) {
        options.onEvent(event);
      }
    }
  }

  buffer += decoder.decode();
  const tail = parseSseChunk(buffer);
  if (tail) {
    options.onEvent(tail);
  }
}

function parseSseChunk(chunk: string): AgentEvent | null {
  const payload = chunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.replace(/^data:\s?/, ""))
    .join("\n")
    .trim();

  if (!payload) return null;

  try {
    return JSON.parse(payload) as AgentEvent;
  } catch {
    return {
      type: "error",
      message: `无法解析后端事件：${payload}`,
    };
  }
}

// ── 会话历史 API ──

export async function fetchConversations(): Promise<Conversation[]> {
  const response = await fetch(`${API_BASE_URL}/api/conversations`);
  if (!response.ok) {
    throw new Error(`获取会话列表失败：HTTP ${response.status}`);
  }
  return response.json();
}

export async function fetchConversation(id: string): Promise<ConversationDetail> {
  const response = await fetch(`${API_BASE_URL}/api/conversations/${id}`);
  if (!response.ok) {
    throw new Error(`获取会话详情失败：HTTP ${response.status}`);
  }
  return response.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/conversations/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new Error(`删除会话失败：HTTP ${response.status}`);
  }
}
