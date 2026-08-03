/**
 * 全局 toast 通知（轻量事件总线）
 * App.tsx 挂载 toast 容器并监听 TOAST_EVENT，
 * 各组件通过 showToast() 触发提示（复制/导出等操作反馈）。
 * 用自定义事件而非 context，避免 App ↔ 子组件循环依赖。
 */

export const TOAST_EVENT = "app:toast";

export type ToastType = "success" | "error" | "info";

export function showToast(message: string, type: ToastType = "success") {
  window.dispatchEvent(
    new CustomEvent(TOAST_EVENT, { detail: { message, type } }),
  );
}
