/**
 * 首页空状态组件
 * 展示产品入口信息和可点击的示例问数问题
 * 改用 DaisyUI 组件：badge / card / btn
 */
import { LineChart, Search, ShoppingBag, Sparkles } from "lucide-react";

type EmptyStateProps = {
  examples: string[];
  onUseExample: (example: string) => void;
};

const highlights = [
  { label: "混合检索", icon: Search },
  { label: "SQL 闭环", icon: LineChart },
  { label: "电商数仓", icon: ShoppingBag },
];

export function EmptyState({ examples, onUseExample }: EmptyStateProps) {
  return (
    <div className="mx-auto flex min-h-full max-w-5xl flex-col justify-center px-4 py-12">
      <div className="mb-10 max-w-3xl">
        <div className="badge badge-primary mb-5 px-3 py-3 text-sm font-semibold text-primary-content">
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          智能数据分析系统
        </div>
        <h1 className="text-balance text-4xl font-semibold leading-tight text-ink sm:text-6xl">
          电商问数
        </h1>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {highlights.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="card card-bordered bg-white/55 px-4 py-4 shadow-none">
              <Icon className="mb-5 h-5 w-5 text-brass" aria-hidden="true" />
              <div className="text-sm font-semibold text-ink">{item.label}</div>
            </div>
          );
        })}
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {examples.map((example) => (
          <button
            key={example}
            type="button"
            onClick={() => onUseExample(example)}
            className="btn btn-outline btn-lg min-h-20 justify-start whitespace-normal px-4 text-left text-[15px] font-normal normal-case leading-6"
          >
            {example}
          </button>
        ))}
      </div>
    </div>
  );
}
