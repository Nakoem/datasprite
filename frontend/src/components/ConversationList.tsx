/**
 * 会话历史侧边栏列表
 *
 * 展示用户的所有历史会话，支持点击加载和删除。
 * 替换侧边栏中原有的硬编码样例区。
 */
import { MessageSquare, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Conversation } from "../types/agent";

type ConversationListProps = {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
};

/** 格式化相对时间 */
function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diff = now - then;
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}天前`;
  return new Date(iso).toLocaleDateString("zh-CN");
}

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onDelete,
}: ConversationListProps) {
  const [hoverId, setHoverId] = useState<string | null>(null);

  if (conversations.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-xs text-ink/45">
        暂无历史记录
        <br />
        问一个问题开始吧～
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {conversations.map((conv) => {
        const isActive = conv.id === activeId;
        return (
          <div
            key={conv.id}
            className="group relative"
            onMouseEnter={() => setHoverId(conv.id)}
            onMouseLeave={() => setHoverId(null)}
          >
            <button
              type="button"
              onClick={() => onSelect(conv.id)}
              className={`flex w-full items-start gap-2 px-3 py-2.5 text-left text-sm leading-5 transition ${
                isActive
                  ? "bg-moss/12 text-ink border-l-2 border-moss"
                  : "border-l-2 border-transparent text-ink/70 hover:bg-ink/5 hover:text-ink"
              }`}
            >
              <MessageSquare
                className={`mt-0.5 h-4 w-4 shrink-0 ${isActive ? "text-moss" : "text-ink/35"}`}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium leading-5">
                  {conv.title}
                </div>
                <div className="text-[11px] text-ink/40">
                  {relativeTime(conv.updatedAt)}
                </div>
              </div>
            </button>
            {hoverId === conv.id && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(conv.id);
                }}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-ink/30 transition hover:bg-tomato/10 hover:text-tomato"
                title="删除"
                aria-label="删除会话"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
