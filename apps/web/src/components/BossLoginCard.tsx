import { CheckCircle2, CircleAlert, LoaderCircle, LogIn, RefreshCw, ShieldCheck, XCircle } from "lucide-react";

import type { BossLoginEvent, BossProviderStatus } from "../api/client";

interface BossLoginCardProps {
  status: BossProviderStatus | null;
  events: BossLoginEvent[];
  loading: boolean;
  onStart: () => void;
  onCancel: () => void;
  onRefresh: () => void;
}

function statusCopy(status: BossProviderStatus | null) {
  if (!status) return { label: "正在检查", className: "bg-slate-100 text-slate-600" };
  if (status.authenticated) return { label: "已登录", className: "bg-emerald-50 text-emerald-700" };
  if (status.status === "not_installed") return { label: "未安装", className: "bg-rose-50 text-rose-700" };
  if (status.status === "incompatible") return { label: "CLI 需更新", className: "bg-rose-50 text-rose-700" };
  if (status.status === "browser_session_missing") return { label: "需打开 Chrome", className: "bg-amber-50 text-amber-700" };
  if (["starting", "waiting_user"].includes(status.status)) return { label: "等待登录", className: "bg-amber-50 text-amber-700" };
  if (status.status === "failed") return { label: "登录失败", className: "bg-rose-50 text-rose-700" };
  return { label: "未登录", className: "bg-amber-50 text-amber-700" };
}

export function BossLoginCard({ status, events, loading, onStart, onCancel, onRefresh }: BossLoginCardProps) {
  const badge = statusCopy(status);
  const active = Boolean(status?.active_login_id) || events.some((event) => ["starting", "waiting_user"].includes(event.status));
  const terminal = events.at(-1)?.status && ["succeeded", "failed", "canceled"].includes(events.at(-1)?.status ?? "");

  return (
    <section className="overflow-hidden rounded-3xl border border-[#cfe4f4] bg-[linear-gradient(135deg,#f8fcff_0%,#eef8fb_55%,#f7fcf8_100%)] shadow-[0_18px_45px_rgba(26,83,112,0.08)]">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/80 px-6 py-5">
        <div className="flex items-start gap-3">
          <div className="rounded-2xl bg-white/90 p-3 text-brand shadow-sm"><ShieldCheck size={21} strokeWidth={1.8} /></div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-base font-semibold text-ink">BOSS 直聘真实来源</h2>
              <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${badge.className}`}>{badge.label}</span>
            </div>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500">登录会在本机项目专用 Chrome 打开 BOSS 官方页面；Safari 等其他浏览器的登录态不会复用。本项目不收集密码、验证码或 Cookie。</p>
          </div>
        </div>
      </div>

      <div className="grid gap-5 px-6 py-5 lg:grid-cols-[1fr_auto] lg:items-center">
        <div>
          <p className="text-sm font-medium text-ink">{status?.authenticated ? "项目 Chrome 中的 BOSS 登录态可用，可以搜索真实岗位。" : status?.message ?? "正在检查本机 BOSS CLI 状态…"}</p>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1.5"><span className={`h-2 w-2 rounded-full ${status?.installed ? "bg-emerald-400" : "bg-rose-400"}`} />CLI {status?.installed ? "已安装" : "未安装"}</span>
            <span>流程：官方页面登录 → 本机保存登录态 → 搜索岗位</span>
          </div>
          {events.length > 0 && <div className="mt-4 space-y-2 rounded-2xl border border-white/90 bg-white/65 p-3">
            {events.slice(-3).map((event) => <div key={event.sequence} className="flex items-start gap-2 text-xs text-slate-600"><span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" /><span>{event.message}</span></div>)}
          </div>}
        </div>

        <div className="flex flex-wrap gap-2 lg:justify-end">
          {status?.authenticated ? <span className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-semibold text-white"><CheckCircle2 size={17} />可搜索</span> : active ? <button type="button" onClick={onCancel} className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-white px-4 py-3 text-sm font-semibold text-rose-700 hover:bg-rose-50"><XCircle size={17} />取消登录</button> : <button type="button" onClick={onStart} disabled={loading || !status?.can_start} className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#203c61] disabled:cursor-not-allowed disabled:opacity-50">{loading ? <LoaderCircle className="animate-spin" size={17} /> : <LogIn size={17} />}在 Chrome 中登录 BOSS</button>}
          <button type="button" onClick={onRefresh} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-4 py-3 text-sm font-semibold text-slate-600 hover:border-brand hover:text-brand"><RefreshCw size={16} />重新检测</button>
        </div>
      </div>

      {terminal && events.at(-1)?.status === "failed" && <div className="flex items-center gap-2 border-t border-rose-100 bg-rose-50/70 px-6 py-3 text-xs text-rose-700"><CircleAlert size={15} />登录没有完成。请在官方窗口确认登录成功后重新发起。</div>}
    </section>
  );
}
