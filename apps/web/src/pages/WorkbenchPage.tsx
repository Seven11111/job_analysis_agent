import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ArrowRight, BriefcaseBusiness, Bot, FileUser, MapPin, Search, Target } from "lucide-react";
import { Link } from "react-router-dom";

import { apiClient, type ApplicationListResponse, type ApplicationSummary, type CandidateProfile } from "../api/client";

type DashboardData = {
  profile: CandidateProfile;
  recentApplications: ApplicationSummary[];
  total: number;
};

function parseBackendDate(value: string) {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
}

function formatDateTime(value: string) {
  const date = parseBackendDate(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
}

export function WorkbenchPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function loadDashboard() {
      setLoading(true);
      setError(null);
      try {
        const [profileResponse, allResponse] = await Promise.all([
          apiClient.get<CandidateProfile>("/profile"),
          apiClient.get<ApplicationListResponse>("/applications", { params: { tab: "all", page: 1, limit: 5 } }),
        ]);
        if (active) {
          setData({
            profile: profileResponse.data,
            recentApplications: allResponse.data.items,
            total: allResponse.data.total,
          });
        }
      } catch {
        if (active) setError("工作台数据加载失败，请确认后端服务正在运行。");
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadDashboard();
    return () => { active = false; };
  }, []);

  return (
    <section className="space-y-7">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="text-xs font-semibold uppercase tracking-[0.28em] text-brand">OVERVIEW</p><h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-ink">工作台</h1></div>
        <Link to="/jobs/search" className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700"><Search size={16} />搜索岗位</Link>
      </header>

      {error && <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</div>}

      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard label="已收藏岗位" value={data?.total} icon={<BriefcaseBusiness size={19} />} href="/jobs/manage" loading={loading} />
        <MetricCard label="求职方向" value={data?.profile.target_directions.length} icon={<Target size={19} />} href="/profile" loading={loading} />
        <MetricCard label="意向城市" value={data?.profile.target_cities.length} icon={<MapPin size={19} />} href="/profile" loading={loading} />
      </div>

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(18rem,.65fr)]">
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-xl font-semibold text-ink">最近收藏</h2><p className="mt-1 text-sm text-slate-500">显示最近保存到岗位管理的记录。</p></div><Link to="/jobs/manage" className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">管理岗位<ArrowRight size={15} /></Link></div>
          {loading ? <div className="mt-5 rounded-2xl bg-mist px-4 py-8 text-center text-sm text-slate-500">正在读取岗位…</div> : data?.recentApplications.length ? <div className="mt-5 space-y-3">{data.recentApplications.map((application) => <RecentApplication key={application.id} application={application} />)}</div> : <div className="mt-5 rounded-2xl border border-dashed border-slate-300 px-4 py-10 text-center"><p className="font-medium text-ink">还没有收藏岗位</p><p className="mt-2 text-sm text-slate-500">搜索到感兴趣的岗位后，可以在搜索结果中保存。</p><Link to="/jobs/search" className="mt-4 inline-flex items-center gap-2 rounded-xl border border-brand px-4 py-2 text-sm font-semibold text-brand hover:bg-blue-50"><Search size={15} />去搜索岗位</Link></div>}
        </section>

        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex items-center justify-between gap-3"><div><h2 className="text-xl font-semibold text-ink">个人画像</h2><p className="mt-1 text-sm text-slate-500">用于岗位匹配和 Agent 上下文。</p></div><Link to="/profile" aria-label="编辑个人画像" className="rounded-lg p-2 text-brand transition hover:bg-blue-50"><ArrowRight size={18} /></Link></div>
          {loading ? <div className="mt-5 h-32 animate-pulse rounded-2xl bg-mist" /> : <div className="mt-5 space-y-4">
            <ProfileField label="求职方向" values={data?.profile.target_directions ?? []} />
            <ProfileField label="意向城市" values={data?.profile.target_cities ?? []} />
            <div className="grid grid-cols-2 gap-3"><ProfileValue label="学校" value={data?.profile.school} /><ProfileValue label="专业" value={data?.profile.major} /></div>
            <div className="border-t border-slate-100 pt-4"><p className="text-xs text-slate-400">简历</p><p className="mt-1 text-sm font-medium text-ink">{data?.profile.resumes.find((resume) => resume.is_current)?.title ?? "尚未创建在线简历"}</p><Link to="/profile" className="mt-2 inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">查看并完善<ArrowRight size={14} /></Link></div>
          </div>}
        </section>
      </div>

      <section>
        <div className="mb-4"><h2 className="text-xl font-semibold text-ink">功能入口</h2></div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <EntryCard to="/jobs/search" icon={<Search size={19} />} title="岗位搜索" description="按关键词、城市、日期、薪资和来源查找实习机会。" />
          <EntryCard to="/jobs/manage" icon={<BriefcaseBusiness size={19} />} title="岗位管理" description="维护收藏岗位、状态时间线、备注和匹配分析。" />
          <EntryCard to="/profile" icon={<FileUser size={19} />} title="个人画像" description="维护求职偏好、在线简历，并解析简历附件。" />
          <EntryCard to="/agent" icon={<Bot size={19} />} title="求职 Agent" description="连续对话，搜索岗位并查询或更新本地求职数据。" />
        </div>
      </section>
    </section>
  );
}

function MetricCard({ label, value, icon, href, loading }: { label: string; value: number | undefined; icon: ReactNode; href: string; loading: boolean }) {
  return <Link to={href} className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-md">
    <div className="flex items-center justify-between"><span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-brand">{icon}</span><ArrowRight size={17} className="text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-brand" /></div>
    <p className="mt-5 text-sm text-slate-500">{label}</p><p className="mt-1 text-3xl font-semibold tracking-tight text-ink">{loading ? "—" : value ?? 0}</p>
  </Link>;
}

function RecentApplication({ application }: { application: ApplicationSummary }) {
  return <Link to={`/jobs/manage?application=${application.id}`} className="flex min-w-0 items-center justify-between gap-4 rounded-2xl bg-[#f7faff] px-4 py-4 transition hover:bg-blue-50">
    <div className="min-w-0"><p className="truncate font-semibold text-ink">{application.job.title}</p><p className="mt-1 truncate text-sm text-slate-500">{application.job.company_name} · {application.job.city}</p><p className="mt-2 text-xs text-slate-400">收藏于 {formatDateTime(application.saved_at)}</p></div>
    <div className="flex shrink-0 flex-col items-end gap-2"><span className="max-w-32 truncate rounded-full bg-white px-3 py-1 text-xs font-medium text-slate-600 ring-1 ring-slate-200">{application.current_status.name}</span><ArrowRight size={15} className="text-slate-300" /></div>
  </Link>;
}

function ProfileField({ label, values }: { label: string; values: string[] }) {
  return <div><p className="text-xs text-slate-400">{label}</p>{values.length ? <div className="mt-2 flex flex-wrap gap-2">{values.map((value) => <span key={value} className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-brand">{value}</span>)}</div> : <p className="mt-1 text-sm text-slate-400">尚未设置</p>}</div>;
}

function ProfileValue({ label, value }: { label: string; value: string | null | undefined }) {
  return <div className="min-w-0 rounded-xl bg-mist p-3"><p className="text-xs text-slate-400">{label}</p><p className="mt-1 truncate text-sm font-medium text-ink">{value || "尚未填写"}</p></div>;
}

function EntryCard({ to, icon, title, description }: { to: string; icon: ReactNode; title: string; description: string }) {
  return <Link to={to} className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-md">
    <div className="flex items-center justify-between"><span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-brand">{icon}</span><ArrowRight size={17} className="text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-brand" /></div>
    <h3 className="mt-4 font-semibold text-ink">{title}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
  </Link>;
}
