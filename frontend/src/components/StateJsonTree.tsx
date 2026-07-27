/**
 * 递归 JSON 树查看器
 *
 * 以可折叠的树状结构渲染任意 JavaScript 对象/数组，
 * 审计日志和回放面板共用此组件查看 state 快照。
 */
import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

type StateJsonTreeProps = {
  data: unknown;
  /** 初始展开深度，默认 1（根节点展开） */
  maxDepth?: number;
};

export function StateJsonTree({ data, maxDepth = 1 }: StateJsonTreeProps) {
  return (
    <div className="font-mono text-xs leading-relaxed">
      <TreeNode value={data} depth={0} maxDepth={maxDepth} label="" />
    </div>
  );
}

function TreeNode({
  value,
  depth,
  maxDepth,
  label,
}: {
  value: unknown;
  depth: number;
  maxDepth: number;
  label: string;
}) {
  const [expanded, setExpanded] = useState(depth < maxDepth);

  if (value === null || value === undefined) {
    return <NullNode label={label} />;
  }

  if (typeof value === "string") {
    return <StringNode label={label} value={value} />;
  }

  if (typeof value === "number") {
    return <NumberNode label={label} value={value} />;
  }

  if (typeof value === "boolean") {
    return <BoolNode label={label} value={value} />;
  }

  if (Array.isArray(value)) {
    return (
      <ArrayNode
        label={label}
        value={value}
        depth={depth}
        maxDepth={maxDepth}
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
      />
    );
  }

  if (typeof value === "object") {
    return (
      <ObjectNode
        label={label}
        value={value as Record<string, unknown>}
        depth={depth}
        maxDepth={maxDepth}
        expanded={expanded}
        onToggle={() => setExpanded((v) => !v)}
      />
    );
  }

  return <StringNode label={label} value={String(value)} />;
}

/* ── 叶子节点 ── */

function NullNode({ label }: { label: string }) {
  return (
    <div className="flex items-start py-0.5">
      {label && (
        <span className="mr-1 shrink-0 text-ink/50">{label}:</span>
      )}
      <span className="italic text-ink/30">null</span>
    </div>
  );
}

function StringNode({ label, value }: { label: string; value: string }) {
  const display =
    value.length > 120 ? value.slice(0, 120) + "…" : value;
  return (
    <div className="flex items-start py-0.5">
      {label && (
        <span className="mr-1 shrink-0 text-ink/50">{label}:</span>
      )}
      <span className="text-moss break-all">"{display}"</span>
    </div>
  );
}

function NumberNode({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-start py-0.5">
      {label && (
        <span className="mr-1 shrink-0 text-ink/50">{label}:</span>
      )}
      <span className="text-blue-600">{value}</span>
    </div>
  );
}

function BoolNode({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex items-start py-0.5">
      {label && (
        <span className="mr-1 shrink-0 text-ink/50">{label}:</span>
      )}
      <span className="text-tomato">{value ? "true" : "false"}</span>
    </div>
  );
}

/* ── 容器节点 ── */

function ArrayNode({
  label,
  value,
  depth,
  maxDepth,
  expanded,
  onToggle,
}: {
  label: string;
  value: unknown[];
  depth: number;
  maxDepth: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center gap-0.5 py-0.5 text-left hover:text-ink/85 focus:outline-none"
      >
        <Chevron className="h-3.5 w-3.5 shrink-0 text-ink/30" />
        {label && <span className="text-ink/50">{label}:</span>}
        <span className="text-ink/40">
          [{value.length}]
          {!expanded && " …"}
        </span>
      </button>
      {expanded && (
        <div className="border-l-2 border-ink/10 ml-2.5 pl-3">
          {value.length === 0 ? (
            <div className="py-0.5 text-ink/30 italic">空数组</div>
          ) : (
            value.map((item, i) => (
              <TreeNode
                key={i}
                value={item}
                depth={depth + 1}
                maxDepth={maxDepth}
                label={`${i}`}
              />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function ObjectNode({
  label,
  value,
  depth,
  maxDepth,
  expanded,
  onToggle,
}: {
  label: string;
  value: Record<string, unknown>;
  depth: number;
  maxDepth: number;
  expanded: boolean;
  onToggle: () => void;
}) {
  const Chevron = expanded ? ChevronDown : ChevronRight;
  const keys = Object.keys(value);
  return (
    <div>
      <button
        type="button"
        onClick={onToggle}
        className="flex items-center gap-0.5 py-0.5 text-left hover:text-ink/85 focus:outline-none"
      >
        <Chevron className="h-3.5 w-3.5 shrink-0 text-ink/30" />
        {label && <span className="text-ink/50">{label}:</span>}
        <span className="text-ink/40">
          {"{"}
          {keys.length === 0
            ? "}"
            : !expanded
              ? `${keys.length} key(s) …}`
              : "}"}
        </span>
      </button>
      {expanded && (
        <div className="border-l-2 border-ink/10 ml-2.5 pl-3">
          {keys.map((key) => (
            <TreeNode
              key={key}
              value={value[key]}
              depth={depth + 1}
              maxDepth={maxDepth}
              label={key}
            />
          ))}
        </div>
      )}
    </div>
  );
}
