/**
 * 聊天输入区组件
 * 处理问题输入、发送和停止当前流式请求
 * 发送/停止按钮改用 DaisyUI btn（btn-primary / btn-error）
 */
import { ArrowUp, Square, WandSparkles } from "lucide-react";
import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { BorderBeam } from "border-beam";
import { MetalFx } from "metal-fx";
import { cn } from "../lib/format";

type ComposerProps = {
    value: string;
    disabled: boolean;
    isStreaming: boolean;
    onChange: (value: string) => void;
    onSubmit: () => void;
    onStop: () => void;
};

export function Composer({
    value,
    disabled,
    isStreaming,
    onChange,
    onSubmit,
    onStop,
}: ComposerProps) {
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);
    const [focused, setFocused] = useState(false);

    const submit = (event: FormEvent) => {
        event.preventDefault();
        if (!disabled) onSubmit();
    };

    const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!disabled) onSubmit();
        }
    };

    return (
        <form
            onSubmit={submit}
            className="border-t border-ink/10 bg-parchment/80 px-4 py-4 backdrop-blur"
        >
            <BorderBeam
                size="md"
                colorVariant="ocean"
                theme="light"
                active={focused}
                strength={0.6}
                className="mx-auto max-w-5xl"
            >
                <div className="flex items-end gap-3 border border-ink/15 bg-white/75 p-2 shadow-panel">
                    <div className="hidden h-11 w-11 shrink-0 place-items-center bg-moss/10 text-moss sm:grid">
                        <WandSparkles className="h-5 w-5" aria-hidden="true" />
                    </div>
                    <textarea
                        ref={textareaRef}
                        value={value}
                        onChange={(event) => onChange(event.target.value)}
                        onKeyDown={onKeyDown}
                        onFocus={() => setFocused(true)}
                        onBlur={() => setFocused(false)}
                        rows={1}
                        placeholder="问一个电商数据问题..."
                        className="max-h-36 min-h-11 flex-1 resize-none bg-transparent px-2 py-3 text-[15px] leading-6 text-ink outline-none placeholder:text-ink/35"
                    />
                    <MetalFx variant="circle" preset="chromatic" theme="light" strength={0.85}>
                        <button
                            type={isStreaming ? "button" : "submit"}
                            onClick={isStreaming ? onStop : undefined}
                            disabled={!isStreaming && disabled}
                            className={cn(
                                "btn btn-circle h-11 w-11 shrink-0",
                                isStreaming
                                    ? "btn-error text-error-content"
                                    : "btn-primary text-primary-content",
                                !isStreaming && disabled && "btn-disabled",
                            )}
                            title={isStreaming ? "停止" : "发送"}
                            aria-label={isStreaming ? "停止" : "发送"}
                        >
                            {isStreaming ? (
                                <Square
                                    className="h-4 w-4 fill-current"
                                    aria-hidden="true"
                                />
                            ) : (
                                <ArrowUp className="h-5 w-5" aria-hidden="true" />
                            )}
                        </button>
                    </MetalFx>
                </div>
            </BorderBeam>
        </form>
    );
}
