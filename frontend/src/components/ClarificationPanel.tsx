/**
 * 意图澄清面板
 *
 * 当后端检测到用户查询模糊时，通过 SSE 发回追问选项。
 * 本组件在助手气泡中渲染一组可点击的追问按钮，
 * 用户点击后自动发送对应的问题。
 * 改用 DaisyUI card + btn-outline。
 */
import { HelpCircle } from "lucide-react";

type ClarificationPanelProps = {
  questions: string[];
  onSelect: (question: string) => void;
};

export function ClarificationPanel({ questions, onSelect }: ClarificationPanelProps) {
  return (
    <div className="card card-bordered mt-3 border-moss/25 bg-moss/[0.06] shadow-none">
      <div className="card-body gap-3 p-4">
        <div className="flex items-center gap-2 text-sm text-ink/70">
          <HelpCircle className="h-4 w-4 shrink-0 text-moss" aria-hidden="true" />
          <span>需要确认一下～</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {questions.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => onSelect(question)}
              className="btn btn-sm btn-outline h-auto min-h-0 justify-start whitespace-normal px-3 py-2 text-left text-[13px] font-normal normal-case leading-5"
            >
              {question}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
