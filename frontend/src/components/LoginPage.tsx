/**
 * 登录页
 * DaisyUI 卡片式登录界面，配色沿用项目「羊皮纸」主题（parchment / ink / moss）。
 */
import { BarChart3, KeyRound, User } from "lucide-react";
import { useState, type FormEvent } from "react";
import { login } from "../lib/authApi";

type LoginPageProps = {
  onSuccess: () => void;
};

export default function LoginPage({ onSuccess }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = username.trim().length > 0 && password.length > 0 && !submitting;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError(null);
    try {
      await login(username.trim(), password);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败，请重试");
      setSubmitting(false);
    }
  };

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-gradient-to-br from-[#f4f2ec] to-[#e4e2d8] px-4">
      {/* 与主界面一致的装饰纹理：网格线 + 颗粒感 */}
      <div className="pointer-events-none fixed inset-0 bg-[linear-gradient(90deg,rgba(20,17,14,0.045)_1px,transparent_1px),linear-gradient(rgba(20,17,14,0.035)_1px,transparent_1px)] bg-[size:48px_48px]" />
      <div className="pointer-events-none fixed inset-0 grain" />

      <div className="card w-full max-w-md border border-ink/10 bg-parchment shadow-panel">
        <div className="card-body gap-6 p-8">
          {/* Logo + 标题 */}
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="grid h-14 w-14 place-items-center bg-ink text-parchment">
              <BarChart3 className="h-7 w-7" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-xl font-semibold tracking-[0.02em] text-ink">问数精灵</h1>
              <p className="mt-1 text-sm text-ink/50">DataSprite Agent · 欢迎回来</p>
            </div>
          </div>

          {/* 登录失败提示 */}
          {error && (
            <div role="alert" className="alert border-none bg-tomato/10 py-2 text-sm text-tomato">
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <label className="label" htmlFor="login-username">
              <span className="label-text text-xs font-semibold uppercase tracking-[0.14em] text-ink/45">用户名</span>
            </label>
            <label className="input input-bordered flex w-full items-center gap-2 border-ink/15 bg-white focus-within:border-moss">
              <User className="h-4 w-4 shrink-0 text-ink/40" aria-hidden="true" />
              <input
                id="login-username"
                type="text"
                className="grow"
                placeholder="admin"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
              />
            </label>

            <label className="label" htmlFor="login-password">
              <span className="label-text text-xs font-semibold uppercase tracking-[0.14em] text-ink/45">密码</span>
            </label>
            <label className="input input-bordered flex w-full items-center gap-2 border-ink/15 bg-white focus-within:border-moss">
              <KeyRound className="h-4 w-4 shrink-0 text-ink/40" aria-hidden="true" />
              <input
                id="login-password"
                type="password"
                className="grow"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </label>

            <button
              type="submit"
              disabled={!canSubmit}
              className="btn mt-2 h-11 w-full border-none bg-moss text-sm font-semibold text-white transition hover:bg-soot disabled:cursor-not-allowed disabled:bg-moss/40"
            >
              {submitting && <span className="loading loading-spinner loading-sm" aria-hidden="true" />}
              {submitting ? "登录中…" : "登 录"}
            </button>
          </form>

          <p className="text-center text-xs text-ink/40">登录即代表你有权限访问该问数系统</p>
        </div>
      </div>
    </div>
  );
}
