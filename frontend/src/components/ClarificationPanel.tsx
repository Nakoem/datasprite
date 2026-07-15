/**
 * 意图澄清面板
 *
 * 当后端检测到用户查询模糊时，通过 SSE 发回追问选项。
 * 本组件在助手气泡中渲染一组可点击的追问按钮，
 * 用户点击后自动发送对应的问题。
 */
import { HelpCircle } from "lucide-react";

type ClarificationPanelProps = {
  questions: string[];
  onSelect: (question: string) => void;
};

export function ClarificationPanel({ questions, onSelect }: ClarificationPanelProps) {
  return (
    <div className="mt-3 border border-moss/20 bg-moss/8 px-4 py-3">
      <div className="mb-2 flex items-center gap-2 text-sm text-ink/70">
        <HelpCircle className="h-4 w-4 shrink-0 text-moss" aria-hidden="true" />
        <span>需要确认一下～</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onSelect(question)}
            className="border border-moss/25 bg-white/70 px-3 py-2 text-left text-sm leading-5 text-ink/80 transition hover:bg-moss/15 hover:text-ink focus:outline-none focus:ring-2 focus:ring-moss/40"
          >
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
