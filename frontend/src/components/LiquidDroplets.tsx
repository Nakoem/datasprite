/**
 * 可拖拽液态水滴组
 *
 * 若干圆形水滴可用鼠标/手指拖拽；Liquid 的液态壳跟随（effect="morph" + observe），
 * 把水滴拖近另一滴时 goo 桥接融合，拖动中的水滴 dissolve 融化邻近滴。
 * 纯装饰交互，不参与任何业务逻辑。
 */
import { useRef, useState, type PointerEvent } from "react";
import { Liquid } from "liquid-gooey";

type Drop = { x: number; y: number };

const INITIAL: Drop[] = [
  { x: 0, y: 0 },
  { x: 38, y: 7 },
  { x: 76, y: 0 },
  { x: 114, y: 7 },
  { x: 152, y: 2 },
];

const DROP_SIZE = 52;

export function LiquidDroplets() {
  const [drops, setDrops] = useState(INITIAL);
  const [dragId, setDragId] = useState<number | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ id: number; offX: number; offY: number } | null>(null);

  const onDown = (id: number, e: PointerEvent) => {
    const box = boxRef.current;
    if (!box) return;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    const rect = box.getBoundingClientRect();
    const d = drops[id];
    dragRef.current = {
      id,
      offX: e.clientX - rect.left - d.x,
      offY: e.clientY - rect.top - d.y,
    };
    setDragId(id);
  };

  const onMove = (e: PointerEvent) => {
    const box = boxRef.current;
    const drag = dragRef.current;
    if (!box || !drag) return;
    const rect = box.getBoundingClientRect();
    const x = e.clientX - rect.left - drag.offX;
    const y = e.clientY - rect.top - drag.offY;
    setDrops((ds) => ds.map((d, i) => (i === drag.id ? { x, y } : d)));
  };

  const onUp = () => {
    dragRef.current = null;
    setDragId(null);
  };

  return (
    <Liquid
      blur={24}
      contrast={24}
      fill="rgba(94, 120, 85, 0.35)"
      filterPadding={40}
      ref={boxRef}
      className="relative h-24"
    >
      {drops.map((d, i) => (
        <Liquid.Item
          key={i}
          morph={{ shape: true, bounce: 0.6, speed: 1.1 }}
          dissolve={{ mix: 0.9 }}
          observe
        >
          <div
            onPointerDown={(e) => onDown(i, e)}
            onPointerMove={onMove}
            onPointerUp={onUp}
            onPointerCancel={onUp}
            className="absolute rounded-full"
            style={{
              left: d.x,
              top: d.y,
              width: DROP_SIZE,
              height: DROP_SIZE,
              transform: "translate(-50%, -50%)",
              cursor: "grab",
              touchAction: "none",
              background:
                i === 2 ? "rgba(217, 128, 107, 0.7)" : "rgba(94, 120, 85, 0.55)",
            }}
          />
        </Liquid.Item>
      ))}
    </Liquid>
  );
}
