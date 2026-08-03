/**
 * 前端应用主组件
 * 负责聊天会话状态、SSE 事件消费和整体页面布局
 */
import {
  Activity,
  BarChart3,
  Eraser,
  History,
  Leaf,
  LogOut,
  Menu,
  MessageSquarePlus,
  Palette,
  Search,
  Server,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AuditLog } from "./components/AuditLog";
import { ClarificationPanel } from "./components/ClarificationPanel";
import { Composer } from "./components/Composer";
import { ConversationList } from "./components/ConversationList";
import { EmptyState } from "./components/EmptyState";
import LoginPage from "./components/LoginPage";
import { MessageBubble } from "./components/MessageBubble";
import { ReplayPanel } from "./components/ReplayPanel";
import {
  UNAUTHORIZED_EVENT,
  streamQuery,
  fetchConversations,
  fetchConversation,
  deleteConversation,
} from "./lib/agentApi";
import { clearToken, getToken } from "./lib/auth";
import { fetchMe } from "./lib/authApi";
import { cn, summarizeResult } from "./lib/format";
import { TOAST_EVENT, type ToastType } from "./lib/toast";
import type { AgentEvent, ChatMessage, Conversation, StepState } from "./types/agent";

const examples = [
  "统计 2025 年第一季度各大区的 GMV，并按 GMV 从高到低排序",
  "统计 2025 年 3 月各商品品类的销量和销售额",
  "查询华东地区 2025 年第一季度销售额最高的前 5 个商品",
  "按会员等级统计 2025 年第一季度的订单数和销售额",
];

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "Vite /api proxy";

function makeId() {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function upsertStep(steps: StepState[] = [], event: Extract<AgentEvent, { type: "progress" }>) {
  const next = steps.filter((item) => item.step !== event.step);
  next.push({
    step: event.step,
    status: event.status,
    updatedAt: Date.now(),
  });
  return next;
}

type AppView = "chat" | "audit" | "replay";
type AppTheme = "datasprite" | "wireframe";

const THEME_KEY = "datasprite-theme";

function getInitialTheme(): AppTheme {
  try {
    return localStorage.getItem(THEME_KEY) === "wireframe" ? "wireframe" : "datasprite";
  } catch {
    return "datasprite";
  }
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [activeController, setActiveController] = useState<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // 登录鉴权
  const [authenticated, setAuthenticated] = useState<boolean>(() => Boolean(getToken()));

  // 多轮对话 & 查询历史
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [view, setView] = useState<AppView>("chat");

  // 主题切换（datasprite 品牌羊皮纸 ↔ wireframe 线框），localStorage 持久化
  const [theme, setTheme] = useState<AppTheme>(getInitialTheme);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* localStorage 不可用时仅本次会话生效 */
    }
  }, [theme]);
  const toggleTheme = () => setTheme((t) => (t === "datasprite" ? "wireframe" : "datasprite"));

  const isStreaming = Boolean(activeController);
  const canSubmit = draft.trim().length > 0 && !isStreaming;

  const completedCount = useMemo(
    () => messages.filter((message) => message.role === "assistant" && message.status === "done").length,
    [messages],
  );

  // 全局 toast 通知（复制/导出等操作反馈）
  const [toasts, setToasts] = useState<Array<{ id: string; message: string; type: ToastType }>>([]);
  useEffect(() => {
    const handler = (e: Event) => {
      const { message, type } = (e as CustomEvent<{ message: string; type: ToastType }>).detail;
      const id = makeId();
      setToasts((prev) => [...prev, { id, message, type }]);
      window.setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 3000);
    };
    window.addEventListener(TOAST_EVENT, handler);
    return () => window.removeEventListener(TOAST_EVENT, handler);
  }, []);

  // 挂载时校验登录态：token 无效（过期/伪造）则清除并回到登录页
  useEffect(() => {
    if (!getToken()) return;
    fetchMe()
      .then(() => setAuthenticated(true))
      .catch(() => {
        clearToken();
        setAuthenticated(false);
      });
  }, []);

  // 运行中收到 401（token 过期/失效）→ 广播事件 → 回到登录页
  useEffect(() => {
    const handler = () => {
      clearToken();
      setAuthenticated(false);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handler);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
  }, []);

  // 登录后加载历史会话列表（未登录时跳过，避免 401）
  useEffect(() => {
    if (!authenticated) return;
    fetchConversations()
      .then(setConversations)
      .catch(() => {/* 静默失败，非关键功能 */});
  }, [authenticated]);

  /** 退出登录：清除 token 回到登录页 */
  const handleLogout = () => {
    if (isStreaming) return;
    clearToken();
    setAuthenticated(false);
    clearConversation();
  };

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const startQuery = async (rawQuery = draft) => {
    const query = rawQuery.trim();
    if (!query || isStreaming) return;

    // 首次查询生成会话 ID
    const cid = conversationId ?? makeId();
    if (!conversationId) {
      setConversationId(cid);
    }

    const userMessage: ChatMessage = {
      id: makeId(),
      role: "user",
      content: query,
      createdAt: Date.now(),
    };

    const assistantId = makeId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "正在连接问数智能体...",
      createdAt: Date.now(),
      status: "streaming",
      steps: [],
    };

    const controller = new AbortController();
    setActiveController(controller);
    setDraft("");
    setMessages((current) => [...current, userMessage, assistantMessage]);

    const onEvent = (event: AgentEvent) => {
      setMessages((current) =>
        current.map((message) => {
          if (message.id !== assistantId) return message;

          if (event.type === "progress") {
            return {
              ...message,
              content: event.status === "running" ? `正在执行：${event.step}` : message.content,
              steps: upsertStep(message.steps, event),
            };
          }

          if (event.type === "result") {
            return {
              ...message,
              status: "done",
              content: summarizeResult(event.data),
              result: event.data,
            };
          }

          if (event.type === "clarification") {
            return {
              ...message,
              status: "done",
              content: "需要确认一下～",
              clarification: event.questions,
            };
          }

          if (event.type === "summary") {
            return {
              ...message,
              summary: event.summary,
              metricDefinitions: event.metrics,
              columnSources: event.tables,
            };
          }

          // catch-all: error events
          const errorMsg = event.type === "error" ? event.message : "未知错误";
          return {
            ...message,
            status: "error",
            content: "这次查询没有成功。",
            error: errorMsg,
          };
        }),
      );
    };

    try {
      await streamQuery(query, { signal: controller.signal, onEvent }, cid);
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId && message.status === "streaming"
            ? { ...message, status: "done", content: "流程已结束，后端未返回查询结果。" }
            : message,
        ),
      );
      // 查询完成后刷新历史列表
      fetchConversations().then(setConversations).catch(() => {});
    } catch (error) {
      const isAbort = error instanceof DOMException && error.name === "AbortError";
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                status: isAbort ? "done" : "error",
                content: isAbort ? "已停止本次查询。" : "无法连接问数接口。",
                error: isAbort ? undefined : error instanceof Error ? error.message : String(error),
              }
            : message,
        ),
      );
    } finally {
      setActiveController(null);
    }
  };

  const stopQuery = () => {
    activeController?.abort();
  };

  const clearConversation = () => {
    if (isStreaming) return;
    setConversationId(null);
    setMessages([]);
    setDraft("");
    setView("chat");
  };

  /** 加载历史会话 */
  const loadConversation = useCallback(async (id: string) => {
    if (isStreaming) return;
    try {
      const detail = await fetchConversation(id);
      const loaded: ChatMessage[] = detail.messages.map((msg) => ({
        ...msg,
        createdAt: msg.createdAt ? new Date(msg.createdAt).getTime() : Date.now(),
        status: "done" as const,
      }));
      setConversationId(id);
      setMessages(loaded);
      setView("chat");
    } catch {
      // 加载失败静默处理
    }
  }, [isStreaming]);

  /** 删除历史会话 */
  const handleDeleteConversation = useCallback(async (id: string) => {
    try {
      await deleteConversation(id);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      // 如果删除的是当前会话，则清空
      if (id === conversationId) {
        clearConversation();
      }
    } catch {
      // 删除失败静默处理
    }
  }, [conversationId, isStreaming]);

  /** 处理澄清追问：点击追问选项 → 自动发送 */
  const handleClarificationSelect = (question: string) => {
    startQuery(question);
  };

  /** 重试：找到最后一条用户消息，移除失败的助手消息后重新查询 */
  const handleRetry = () => {
    if (isStreaming) return;
    // 找到最后一条用户消息
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    // 移除最后一条助手消息（失败的那条）后重新查询
    setMessages((current) => {
      let lastAssistantIdx = -1;
      for (let i = current.length - 1; i >= 0; i--) {
        if (current[i].role === "assistant") { lastAssistantIdx = i; break; }
      }
      if (lastAssistantIdx === -1) return current;
      return current.slice(0, lastAssistantIdx);
    });
    startQuery(lastUser.content);
  };

  // 未登录 → 渲染登录页；登录成功后进入主界面
  if (!authenticated) {
    return <LoginPage onSuccess={() => setAuthenticated(true)} />;
  }

  // 侧栏内容（桌面 aside + 移动端 drawer 复用）
  const sidebar = (
    <>
      <div className="border-b border-ink/10 px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center bg-ink text-parchment">
            <BarChart3 className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <div className="text-base font-semibold tracking-[0.02em]">电商问数</div>
            <div className="text-xs text-ink/50">DataSprite Agent</div>
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4 scrollbar-hide">
        <button
          type="button"
          onClick={clearConversation}
          disabled={isStreaming}
          className="btn btn-primary h-11 w-full normal-case"
        >
          <MessageSquarePlus className="h-4 w-4" aria-hidden="true" />
          新会话
        </button>

        <section>
          <div className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-[0.16em] text-ink/45">
            <History className="h-3.5 w-3.5" aria-hidden="true" />
            历史会话
          </div>
          <ConversationList
            conversations={conversations}
            activeId={conversationId}
            onSelect={loadConversation}
            onDelete={handleDeleteConversation}
          />
        </section>

        {conversationId && (
          <section className="border-t border-ink/10 pt-4">
            <div className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-[0.16em] text-ink/45">
              <Search className="h-3.5 w-3.5" aria-hidden="true" />
              工具
            </div>
            <ul className="menu menu-vertical gap-0.5 px-0 py-0">
              <li>
                <button
                  type="button"
                  onClick={() => setView("audit")}
                  className={cn(
                    "justify-start",
                    view === "audit" ? "menu-active" : "hover:bg-ink/5",
                  )}
                >
                  审计日志
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => setView("replay")}
                  className={cn(
                    "justify-start",
                    view === "replay" ? "menu-active" : "hover:bg-ink/5",
                  )}
                >
                  流程回放
                </button>
              </li>
            </ul>
          </section>
        )}
      </div>

      <div className="border-t border-ink/10 p-4">
        <div className="tooltip tooltip-right" data-tip={theme === "datasprite" ? "切换到线框主题" : "切换到羊皮纸主题"}>
          <button
            type="button"
            onClick={toggleTheme}
            className="btn btn-ghost btn-sm mb-3 flex h-9 w-full justify-start gap-2 border border-ink/10 normal-case text-ink/60 hover:bg-ink/5"
          >
            <Palette className="h-3.5 w-3.5" aria-hidden="true" />
            {theme === "datasprite" ? "羊皮纸主题" : "线框主题"}
            <span className="ml-auto text-[11px] opacity-50">切换</span>
          </button>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          disabled={isStreaming}
          className="btn btn-outline btn-sm mb-3 h-9 w-full border-ink/15 normal-case text-ink/60 hover:border-tomato/40 hover:text-tomato disabled:cursor-not-allowed disabled:opacity-40"
        >
          <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
          退出登录
        </button>
        <div className="grid gap-2 text-xs text-ink/55">
          <div className="flex items-center justify-between gap-3">
            <span className="inline-flex items-center gap-2">
              <Server className="h-3.5 w-3.5" aria-hidden="true" />
              API
            </span>
            <span className="truncate font-mono">{API_BASE_URL}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-2">
              <Activity className="h-3.5 w-3.5" aria-hidden="true" />
              完成
            </span>
            <span>{completedCount}</span>
          </div>
        </div>
      </div>
    </>
  );

  return (
    <div className="h-dvh overflow-hidden bg-base-100 text-base-content">
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(90deg,rgba(20,17,14,0.045)_1px,transparent_1px),linear-gradient(rgba(20,17,14,0.035)_1px,transparent_1px)] bg-[size:48px_48px]" />
      <div className="pointer-events-none fixed inset-0 grain" />

      <div className="drawer h-full">
        <input id="app-drawer" type="checkbox" className="drawer-toggle" />

        {/* 主内容：桌面侧栏 + 聊天区 */}
        <div className="drawer-content relative grid h-full min-h-0 overflow-hidden lg:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="hidden min-h-0 border-r border-ink/10 bg-base-200/85 backdrop-blur lg:flex lg:flex-col">
            {sidebar}
          </aside>

          <main className="flex min-h-0 min-w-0 flex-col overflow-hidden">
          <header className="flex h-16 shrink-0 items-center justify-between border-b border-ink/10 bg-base-100/88 px-4 backdrop-blur lg:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <label
                htmlFor="app-drawer"
                className="btn btn-ghost btn-circle btn-sm lg:hidden"
                aria-label="打开菜单"
                title="打开菜单"
              >
                <Menu className="h-5 w-5" aria-hidden="true" />
              </label>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink">DataSprite Agent</div>
                <div className="truncate text-xs text-ink/45">FastAPI SSE / LangGraph</div>
              </div>
              {conversationId && (
                <div className="join ml-4 hidden sm:flex">
                  <button
                    type="button"
                    onClick={() => setView("chat")}
                    className={cn(
                      "join-item btn btn-sm normal-case",
                      view === "chat" ? "btn-active" : "btn-ghost",
                    )}
                  >
                    对话
                  </button>
                  <button
                    type="button"
                    onClick={() => setView("audit")}
                    className={cn(
                      "join-item btn btn-sm normal-case",
                      view === "audit" ? "btn-active" : "btn-ghost",
                    )}
                  >
                    审计日志
                  </button>
                  <button
                    type="button"
                    onClick={() => setView("replay")}
                    className={cn(
                      "join-item btn btn-sm normal-case",
                      view === "replay" ? "btn-active" : "btn-ghost",
                    )}
                  >
                    回放
                  </button>
                </div>
              )}
            </div>
            <div className="tooltip tooltip-left" data-tip="清空对话">
              <button
                type="button"
                onClick={clearConversation}
                disabled={messages.length === 0 || isStreaming}
                className="grid h-11 w-11 place-items-center rounded-full text-ink/55 transition hover:bg-ink/5 hover:text-ink disabled:cursor-not-allowed disabled:opacity-35 focus:outline-none focus:ring-2 focus:ring-moss/40 focus:ring-offset-2"
                aria-label="清空"
              >
                <Eraser className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
          </header>

          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain scrollbar-hide">
            {view === "chat" && (
              messages.length === 0 ? (
                <EmptyState examples={examples} onUseExample={(example) => setDraft(example)} />
              ) : (
                <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6 lg:px-8">
                  {messages.map((message) => (
                    <MessageBubble
                      key={message.id}
                      message={message}
                      onClarificationSelect={handleClarificationSelect}
                      onRetry={handleRetry}
                    />
                  ))}
                </div>
              )
            )}
            {view === "audit" && conversationId && (
              <AuditLog conversationId={conversationId} />
            )}
            {view === "replay" && conversationId && (
              <ReplayPanel conversationId={conversationId} />
            )}
          </div>

          <div className="border-t border-ink/10 bg-base-200/45 px-4 py-2 text-center text-xs text-ink/45">
            <span className="inline-flex items-center gap-2">
              <Leaf className="h-3.5 w-3.5 text-moss" aria-hidden="true" />
              {isStreaming ? (
                <span className="inline-flex items-center gap-1.5">
                  <span className="loading loading-dots loading-xs text-moss" />
                  运行中
                </span>
              ) : (
                "就绪"
              )}
            </span>
          </div>
          <Composer
            value={draft}
            disabled={!canSubmit}
            isStreaming={isStreaming}
            onChange={setDraft}
            onSubmit={() => startQuery()}
            onStop={stopQuery}
          />
          </main>
        </div>

        {/* 移动端 drawer 侧栏 */}
        <div className="drawer-side z-40 lg:hidden">
          <label htmlFor="app-drawer" aria-label="关闭侧栏" className="drawer-overlay" />
          <aside className="flex min-h-full w-72 flex-col border-r border-ink/10 bg-base-200/95 backdrop-blur">
            {sidebar}
          </aside>
        </div>
      </div>

      {/* 全局 toast */}
      <div className="toast toast-top toast-end z-50">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "alert alert-soft shadow-panel",
              t.type === "success" && "alert-success",
              t.type === "error" && "alert-error",
              t.type === "info" && "alert-info",
            )}
          >
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
