import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarDays, CheckCircle2, ExternalLink, Filter, MapPin, Search, Sparkles } from "lucide-react";

import { apiClient, API_BASE_URL, LLM_REQUEST_TIMEOUT_MS, type BossLoginEvent, type BossLoginStartResponse, type BossProviderStatus, type JobDetail, type JobSearchRequest, type JobSearchResponse, type JobSummary, type MatchSummary } from "../api/client";
import { BossLoginCard } from "../components/BossLoginCard";
import { CampusRecruitSearch } from "../components/CampusRecruitSearch";
import { CityPicker, MultiSelect } from "../components/JobSearchFilters";
import { readJobSearchProviders, saveJobSearchProviders, type JobSearchProvider } from "../stores/jobSearchPreferences";

const initialFilters: JobSearchRequest = {
  keyword: "",
  cities: ["上海"],
  published_range: "all",
  salary_mode: "any",
  // 产品范围固定为实习岗位，类型筛选不向用户暴露。
  internship_type: "实习生",
  providers: ["job_pro"],
  page: 1,
  limit: 20,
};

const dateOptions = [["1d", "最近 1 天"], ["3d", "最近 3 天"], ["7d", "最近 7 天"], ["30d", "最近 30 天"]] as const;
const providerOptions = [
  ["boss_agent_cli", "BOSS 本地只读"],
  ["job_pro", "job-pro 校招实习"],
] as const;

function formatDate(value: string | null) { return value ? value.replaceAll("-", "/") : "日期未知"; }
function extractionLabel(value: string) { return ({ provider_api: "Provider 标准化", boss_agent_cli: "BOSS CLI 提取", job_pro: "job-pro 提取", json_ld: "JSON-LD 提取", html_meta: "网页元数据提取" } as Record<string, string>)[value] ?? value; }
function paginationEntries(currentPage: number, totalPages: number): (number | "start-ellipsis" | "end-ellipsis")[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, index) => index + 1);
  const start = Math.max(2, currentPage - 1);
  const end = Math.min(totalPages - 1, currentPage + 1);
  const entries: (number | "start-ellipsis" | "end-ellipsis")[] = [1];
  if (start > 2) entries.push("start-ellipsis");
  for (let page = start; page <= end; page += 1) entries.push(page);
  if (end < totalPages - 1) entries.push("end-ellipsis");
  entries.push(totalPages);
  return entries;
}

function SearchCard({ job, active, onSelect }: { job: JobSummary; active: boolean; onSelect: () => void }) {
  return <button type="button" onClick={onSelect} className={`group w-full rounded-2xl border p-5 text-left transition ${active ? "border-brand bg-[#f2f9ff] shadow-[0_10px_30px_rgba(22,136,216,0.12)]" : "border-slate-200/90 bg-white hover:-translate-y-0.5 hover:border-brand/50 hover:shadow-lg"}`}>
    <div className="flex items-start justify-between gap-5"><div className="min-w-0"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-teal-400" /><h2 className="truncate text-xl font-semibold tracking-tight text-ink">{job.title}</h2></div><p className="mt-2 font-medium text-slate-600">{job.company_name}</p><div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-500"><span className="inline-flex items-center gap-1.5"><MapPin size={15} />{job.city}{job.district ? ` · ${job.district}` : ""}</span><span className="inline-flex items-center gap-1.5"><CalendarDays size={15} />{formatDate(job.published_date)}</span></div></div><span className="shrink-0 rounded-full bg-[#e7f7f2] px-3 py-1 text-xs font-semibold text-teal-700">{job.salary.display}</span></div>
    <div className="mt-5 flex flex-wrap items-center gap-2 text-xs"><span className="rounded-full bg-blue-50 px-3 py-1 font-medium text-brand">{job.job_type}</span>{job.education && <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">{job.education}</span>}<span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">{extractionLabel(job.extraction_method)}</span><span className="ml-auto text-slate-400">来源：{job.source.name}</span></div>
  </button>;
}

function DetailPanel({ job, onRefresh, onSave, onAnalyze, saving, analyzing }: { job: JobDetail | null; onRefresh: () => void; onSave: () => void; onAnalyze: () => void; saving: boolean; analyzing: boolean }) {
  if (!job) return <div className="flex min-h-[560px] items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 p-8 text-center text-slate-400">选择一个岗位查看详情</div>;
  return <aside className="sticky top-6 max-h-[calc(100vh-3rem)] min-w-0 overflow-y-auto rounded-3xl border border-slate-200/90 bg-white p-5 shadow-[0_18px_50px_rgba(24,64,96,0.08)] sm:p-6">
    <div className="flex min-w-0 items-start gap-4">
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-brand">岗位详情</p>
        <h2 className="mt-3 break-words text-2xl font-semibold leading-tight tracking-tight text-ink">{job.title}</h2>
        <p className="mt-3 break-words text-sm leading-6 text-slate-600">{job.company_name} <span className="px-1 text-slate-300">·</span> {job.city} <span className="px-1 text-slate-300">·</span> {formatDate(job.published_date)}</p>
      </div>
      <span className="max-w-32 shrink-0 rounded-full bg-[#e7f7f2] px-3 py-1.5 text-center text-xs font-semibold leading-5 text-teal-700">{job.salary.display}</span>
    </div>
    <div className="mt-5 flex flex-wrap gap-2 text-xs"><span className="max-w-full break-words rounded-full bg-blue-50 px-3 py-1.5 text-brand">来源：{job.source.name}</span><span className="rounded-full bg-slate-100 px-3 py-1.5 text-slate-600">提取：{extractionLabel(job.extraction_method)}</span></div>
    <div className="mt-5 grid grid-cols-2 gap-3 text-sm"><Info label="实习类型" value={job.job_type} /><Info label="学历要求" value={job.education ?? "未说明"} /><Info label="实习时长" value={job.internship_months ? `${job.internship_months} 个月` : "未说明"} /><Info label="转正机会" value={job.conversion_chance === "possible" || job.conversion_chance === "yes" ? "来源已说明" : "未说明"} /></div>
    <div className="mt-6 space-y-5 text-sm leading-7 text-slate-600"><DetailBlock title="岗位描述" value={job.description} /><DetailBlock title="任职要求" value={job.requirements} /><DetailBlock title="工作内容" value={job.responsibilities} /></div>
    {job.latest_match && <MatchPreview match={job.latest_match} />}
    <div className="mt-6 grid grid-cols-2 gap-3"><a href={job.detail_url} target="_blank" rel="noreferrer" className="col-span-2 inline-flex items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#0d76c0]"><ExternalLink size={16} />打开来源链接</a><button type="button" onClick={onSave} disabled={job.is_saved || saving} className={`rounded-xl border px-3 py-3 text-sm font-semibold ${job.is_saved ? "border-teal-200 bg-teal-50 text-teal-700" : "border-brand text-brand hover:bg-blue-50"}`}>{job.is_saved ? "已收藏" : saving ? "保存中" : "保存岗位"}</button><button type="button" onClick={onAnalyze} disabled={analyzing || saving} className="inline-flex items-center justify-center gap-2 rounded-xl border border-ink px-3 py-3 text-sm font-semibold text-ink hover:bg-slate-50 disabled:opacity-50">{analyzing ? "分析中…" : job.latest_match ? "重新分析" : job.id ? "分析岗位" : "保存并分析"}</button></div><button type="button" onClick={onRefresh} className="mt-4 w-full text-center text-xs text-slate-400 hover:text-brand">重新加载详情</button>
  </aside>;
}

function MatchPreview({ match }: { match: MatchSummary }) {
  return <div className="mt-7 rounded-2xl border border-teal-100 bg-[#f1fbf8] p-5"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">岗位匹配分析</p><p className="mt-2 text-sm leading-6 text-slate-600">{match.summary}</p></div><div className="text-right"><p className="text-3xl font-semibold text-teal-700">{match.match_score}</p><p className="text-xs text-slate-500">匹配分</p></div></div>{match.matched_points.length > 0 && <div className="mt-4 space-y-2 text-sm text-slate-600">{match.matched_points.slice(0, 3).map((point) => <p key={point} className="flex items-start gap-2"><CheckCircle2 size={16} className="mt-0.5 shrink-0 text-teal-600" />{point}</p>)}</div>}<p className="mt-4 text-xs text-slate-400">{match.analysis_mode === "rules_v1" ? "规则初筛 · 用户主动触发" : match.analysis_mode}</p></div>;
}

function Info({ label, value }: { label: string; value: string }) { return <div className="rounded-xl bg-mist px-4 py-3"><p className="text-xs text-slate-400">{label}</p><p className="mt-1 font-medium text-ink">{value}</p></div>; }
function DetailBlock({ title, value }: { title: string; value: string | null }) { return <div><h3 className="font-semibold text-ink">{title}</h3><p className="mt-1">{value || "来源未提供"}</p></div>; }

export function JobSearchPage() {
  const [searchMode, setSearchMode] = useState<"internships" | "campus">("internships");
  const [filters, setFilters] = useState(() => ({
    ...initialFilters,
    providers: readJobSearchProviders(initialFilters.providers as JobSearchProvider[]),
  }));
  const [result, setResult] = useState<JobSearchResponse | null>(null);
  const [pageDraft, setPageDraft] = useState("1");
  const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bossStatus, setBossStatus] = useState<BossProviderStatus | null>(null);
  const [bossLoginEvents, setBossLoginEvents] = useState<BossLoginEvent[]>([]);
  const [bossLoginLoading, setBossLoginLoading] = useState(false);

  const refreshBossStatus = useCallback(async (): Promise<BossProviderStatus | null> => {
    try {
      const response = await apiClient.get<BossProviderStatus>("/providers/boss/status");
      setBossStatus(response.data);
      return response.data;
    } catch {
      const unavailable: BossProviderStatus = { provider: "boss_agent_cli", installed: false, authenticated: false, status: "not_installed", message: "无法连接后端，请先启动 API 服务", active_login_id: null, can_start: false };
      setBossStatus(unavailable);
      return null;
    }
  }, []);

  const startBossLogin = useCallback(async (): Promise<boolean> => {
    setBossLoginLoading(true); setBossLoginEvents([]); setError(null);
    try {
      const response = await apiClient.post<BossLoginStartResponse>("/providers/boss/login/start");
      setBossStatus((current) => current ? { ...current, status: response.data.status as BossProviderStatus["status"], message: response.data.message, active_login_id: response.data.run_id, can_start: false } : current);
      return true;
    } catch (requestError) {
      const detail = (requestError as { response?: { data?: { detail?: { message?: string } } } }).response?.data?.detail?.message;
      setError(detail ?? "无法启动 BOSS 登录流程，请确认 boss-agent-cli 已安装并可在后端环境中找到。");
      return false;
    } finally { setBossLoginLoading(false); }
  }, []);

  const cancelBossLogin = useCallback(async () => {
    const runId = bossStatus?.active_login_id;
    if (!runId) return;
    try { await apiClient.post(`/providers/boss/login/${runId}/cancel`); await refreshBossStatus(); }
    catch { setError("取消 BOSS 登录流程失败，请稍后重试。"); }
  }, [bossStatus?.active_login_id, refreshBossStatus]);

  const loadDetail = useCallback(async (job: JobSummary) => {
    setSelectedJob(null); setDetailLoading(true); setError(null);
    try { const path = job.id ? `/jobs/${job.id}` : `/jobs/search-results/${job.result_token}`; const response = await apiClient.get<JobDetail>(path); setSelectedJob(response.data); }
    catch { setError("岗位详情已过期或加载失败，请重新搜索。"); }
    finally { setDetailLoading(false); }
  }, []);

  const search = useCallback(async (nextFilters: JobSearchRequest) => {
    if (nextFilters.providers?.includes("boss_agent_cli")) {
      const currentStatus = await refreshBossStatus();
      if (!currentStatus?.authenticated) {
        const started = await startBossLogin();
        if (started) setError("BOSS 登录页已在项目专用 Chrome 中打开；完成登录后再次点击“搜索”即可继续，本次条件已保留。");
        return;
      }
    }
    setLoading(true); setError(null);
    try { const response = await apiClient.post<JobSearchResponse>("/jobs/search", nextFilters); setResult(response.data); if (response.data.items.length > 0) await loadDetail(response.data.items[0]); else setSelectedJob(null); }
    catch (requestError) {
      const responseDetail = (requestError as { response?: { data?: { detail?: { quality?: Array<{ provider?: string; error?: string }> } } } }).response?.data?.detail;
      const providerError = responseDetail?.quality?.find((item) => item.provider === "boss_agent_cli")?.error;
      const message = requestError instanceof Error ? requestError.message : "岗位搜索失败";
      setError(message.includes("Network Error") ? "无法连接后端，请先启动 API 服务。" : providerError ? `BOSS 来源暂时不可用：${providerError}` : "岗位来源暂时不可用，请查看来源状态后重试。");
      setResult(null); setSelectedJob(null);
    }
    finally { setLoading(false); }
  }, [loadDetail, refreshBossStatus, startBossLogin]);

  const saveJob = useCallback(async (): Promise<JobDetail | null> => {
    if (!selectedJob) return null;
    if (selectedJob.is_saved) return selectedJob;
    setSaving(true); setError(null);
    try {
      let saved = selectedJob;
      if (!selectedJob.id && selectedJob.result_token) { const response = await apiClient.post<JobDetail>(`/jobs/search-results/${selectedJob.result_token}/save`); saved = response.data; }
      if (saved.id) await apiClient.post("/applications", { job_id: saved.id });
      setSelectedJob({ ...saved, is_saved: true });
      setResult((current) => current ? { ...current, items: current.items.map((item) => item.result_token === selectedJob.result_token ? { ...item, id: saved.id, result_token: null, is_saved: true } : item) } : current);
      return { ...saved, is_saved: true };
    } catch (requestError) { setError(requestError instanceof Error && requestError.message.includes("409") ? "这个岗位已经保存过了。" : "保存岗位失败，请稍后重试。" ); return null; }
    finally { setSaving(false); }
  }, [selectedJob]);

  const analyzeSelectedJob = useCallback(async () => {
    if (!selectedJob) return;
    setAnalyzing(true); setError(null);
    try {
      const saved = selectedJob.id ? selectedJob : await saveJob();
      if (!saved?.id) return;
      const response = await apiClient.post<MatchSummary>(`/jobs/${saved.id}/matches`, {}, { timeout: LLM_REQUEST_TIMEOUT_MS });
      setSelectedJob({ ...saved, latest_match: response.data });
      setResult((current) => current ? { ...current, items: current.items.map((item) => item.result_token === selectedJob.result_token ? { ...item, id: saved.id, result_token: null, is_saved: true, latest_match: response.data } : item) } : current);
    } catch { setError("岗位分析失败，请先完善个人画像或稍后重试。"); }
    finally { setAnalyzing(false); }
  }, [saveJob, selectedJob]);

  useEffect(() => { void refreshBossStatus(); }, [refreshBossStatus]);
  useEffect(() => { saveJobSearchProviders(filters.providers ?? []); }, [filters.providers]);
  useEffect(() => {
    const runId = bossStatus?.active_login_id;
    if (!runId) return;
    const source = new EventSource(`${API_BASE_URL}/providers/boss/login/${runId}/events`);
    const handleEvent = (event: MessageEvent<string>) => {
      const payload = JSON.parse(event.data) as BossLoginEvent;
      setBossLoginEvents((current) => [...current, payload]);
      setBossStatus((current) => current ? { ...current, status: payload.status as BossProviderStatus["status"], message: payload.message } : current);
      if (["succeeded", "failed", "canceled"].includes(payload.status)) { source.close(); void refreshBossStatus(); }
    };
    source.addEventListener("boss_login", handleEvent);
    source.onerror = () => source.close();
    return () => source.close();
  }, [bossStatus?.active_login_id, refreshBossStatus]);
  const resultLabel = useMemo(() => result ? `${result.total} 个岗位` : "等待搜索", [result]);
  const totalPages = result ? Math.ceil(result.total / result.limit) : 0;
  const bossSelected = filters.providers?.includes("boss_agent_cli") ?? false;
  const bossSearchBlocked = bossSelected && !bossStatus?.authenticated;
  const noProviderSelected = (filters.providers?.length ?? 0) === 0;
  function updateFilter<K extends keyof JobSearchRequest>(key: K, value: JobSearchRequest[K]) { setFilters((current) => ({ ...current, [key]: value, page: 1 })); }
  function toggleFilterValue(key: "cities" | "providers", value: string) {
    setFilters((current) => {
      const values = (current[key] ?? []) as string[];
      const next = values.includes(value) ? values.filter((item) => item !== value) : [...values, value];
      return { ...current, [key]: next, page: 1 };
    });
  }
  function goToPage(page: number) {
    if (!result || loading) return;
    if (page < 1 || page > totalPages) return;
    const nextFilters = { ...filters, page };
    setFilters(nextFilters);
    void search(nextFilters);
  }
  function updatePageSize(limit: number) {
    const nextFilters = { ...filters, limit, page: 1 };
    setFilters(nextFilters);
    void search(nextFilters);
  }
  function submitPageJump() {
    const page = Number(pageDraft);
    if (!Number.isInteger(page) || page < 1 || page > totalPages) {
      setPageDraft(String(result?.page ?? 1));
      return;
    }
    goToPage(page);
  }

  useEffect(() => {
    if (result) setPageDraft(String(result.page));
  }, [result?.page]);

  return <section className="space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-[0.28em] text-brand">RESEARCH / 01</p><h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-ink">岗位搜索</h1><p className="mt-2 text-sm text-slate-500">{searchMode === "internships" ? "搜索结果先临时展示，只有你确认后才会写入岗位库。" : "查阅企业校招公告；公告结果与实习岗位管理分开。"}</p></div>
      {searchMode === "internships" && <div className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-500"><span className="mr-2 inline-block h-2 w-2 rounded-full bg-teal-400" />{resultLabel}</div>}
    </header>
    <div role="tablist" aria-label="岗位信息类型" className="inline-flex rounded-2xl border border-slate-200 bg-white p-1 shadow-sm">
      <button type="button" role="tab" aria-selected={searchMode === "internships"} onClick={() => setSearchMode("internships")} className={`rounded-xl px-4 py-2.5 text-sm font-medium transition ${searchMode === "internships" ? "bg-ink text-white shadow-sm" : "text-slate-500 hover:text-ink"}`}>实习岗位</button>
      <button type="button" role="tab" aria-selected={searchMode === "campus"} onClick={() => setSearchMode("campus")} className={`rounded-xl px-4 py-2.5 text-sm font-medium transition ${searchMode === "campus" ? "bg-teal-700 text-white shadow-sm" : "text-slate-500 hover:text-ink"}`}>校招资讯</button>
    </div>
    {searchMode === "campus" ? <CampusRecruitSearch /> : <>
    {bossSelected && <BossLoginCard status={bossStatus} events={bossLoginEvents} loading={bossLoginLoading} onStart={() => void startBossLogin()} onCancel={() => void cancelBossLogin()} onRefresh={() => void refreshBossStatus()} />}
    <form onSubmit={(event) => { event.preventDefault(); if (noProviderSelected) { setError("请至少选择一个岗位来源后再搜索。"); return; } const nextFilters = { ...filters, page: 1 }; setFilters(nextFilters); void search(nextFilters); }} className="rounded-3xl border border-slate-200/90 bg-white p-5 shadow-[0_14px_40px_rgba(24,64,96,0.06)] sm:p-6">
      <div className="grid gap-3 xl:grid-cols-[minmax(16rem,1.65fr)_minmax(9rem,.8fr)_minmax(9rem,.8fr)_minmax(12rem,1fr)_auto]">
        <label className="relative block"><Search className="absolute left-4 top-3.5 text-slate-400" size={19} /><input value={filters.keyword ?? ""} onChange={(event) => updateFilter("keyword", event.target.value)} placeholder="搜索岗位或公司，例如 Python 后端" className="h-12 w-full rounded-xl border border-slate-200 bg-[#fbfdff] pl-11 pr-4 text-sm outline-none transition focus:border-brand focus:ring-4 focus:ring-brand/10" /></label>
        <label className="relative block"><CalendarDays className="absolute left-4 top-3.5 text-slate-400" size={18} /><select value={filters.published_range} onChange={(event) => updateFilter("published_range", event.target.value as JobSearchRequest["published_range"])} className="h-12 w-full appearance-none rounded-xl border border-slate-200 bg-[#fbfdff] pl-11 pr-3 text-sm outline-none focus:border-brand"><option value="all">不限日期</option>{dateOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="relative block"><Filter className="absolute left-4 top-3.5 text-slate-400" size={18} /><select value={filters.salary_mode} onChange={(event) => updateFilter("salary_mode", event.target.value as JobSearchRequest["salary_mode"])} className="h-12 w-full appearance-none rounded-xl border border-slate-200 bg-[#fbfdff] pl-11 pr-3 text-sm outline-none focus:border-brand"><option value="any">不限薪资</option><option value="disclosed_only">只看已公开</option></select></label>
        <MultiSelect label="来源" values={filters.providers ?? []} options={providerOptions} onToggle={(value) => toggleFilterValue("providers", value)} />
        <button type="submit" disabled={loading || bossLoginLoading || noProviderSelected} className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-ink px-6 text-sm font-semibold text-white transition hover:bg-[#203c61] disabled:cursor-not-allowed disabled:opacity-60"><Search size={17} />{bossSearchBlocked ? "在 Chrome 登录" : noProviderSelected ? "选择来源" : loading ? "搜索中" : "搜索"}</button>
      </div>
      <div className="mt-4 border-t border-slate-100 pt-4">
        <CityPicker values={filters.cities ?? []} onChange={(cities) => updateFilter("cities", cities)} />
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-400"><span>仅搜索实习岗位；城市和来源可多选，搜索结果不会自动保存。</span>{noProviderSelected && <span className="text-amber-600">至少选择一个岗位来源后才能搜索。</span>}{filters.providers?.includes("job_pro") && filters.published_range !== "all" && <span className="text-amber-600">job-pro 部分岗位未提供发布日期，选择日期范围会排除日期未知的岗位。</span>}</div>
    </form>
    {error && <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</div>}
    {result && <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500"><Sparkles size={16} className="text-brand" />来源：{result.quality.providers.map((provider) => `${provider.provider} ${provider.status === "success" ? "可用" : "失败"}`).join(" · ")}<span className="ml-auto">{result.quality.undisclosed_salary_count} 个岗位薪资未公开 · {result.quality.missing_published_date_count} 个岗位日期未知</span></div>}
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(25rem,0.95fr)] 2xl:grid-cols-[minmax(0,1.1fr)_minmax(28rem,0.9fr)]">
      <div className="min-w-0 space-y-4">
        {loading && <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">正在读取岗位来源…</div>}
        {!loading && result?.items.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center"><p className="text-lg font-semibold text-ink">没有符合条件的岗位</p><p className="mt-2 text-sm text-slate-500">可以放宽城市或发布日期条件后再试。</p></div>}
        {!loading && result?.items.map((job) => <SearchCard key={job.result_token ?? job.id} job={job} active={selectedJob?.id === job.id && selectedJob?.result_token === job.result_token} onSelect={() => void loadDetail(job)} />)}
        {!loading && !result && !error && <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center text-sm text-slate-500">提交条件后显示岗位。</div>}
        {!loading && result && result.total > result.limit && <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3">
          <p className="text-sm text-slate-500">共 {result.total} 个岗位 · 第 {result.page} / {totalPages} 页</p>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <label className="mr-1 flex items-center gap-2 text-xs text-slate-500">每页<select value={filters.limit} onChange={(event) => updatePageSize(Number(event.target.value))} className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-ink"><option value={10}>10</option><option value={20}>20</option><option value={50}>50</option></select></label>
            <button type="button" onClick={() => goToPage(result.page - 1)} disabled={result.page <= 1 || loading} className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:border-brand hover:text-brand disabled:cursor-not-allowed disabled:opacity-40">上一页</button>
            {paginationEntries(result.page, totalPages).map((entry) => typeof entry === "number" ? <button key={entry} type="button" onClick={() => goToPage(entry)} disabled={loading} aria-current={entry === result.page ? "page" : undefined} className={`min-w-9 rounded-lg border px-2.5 py-2 text-sm transition disabled:cursor-not-allowed ${entry === result.page ? "border-ink bg-ink font-semibold text-white" : "border-slate-200 text-slate-600 hover:border-brand hover:text-brand"}`}>{entry}</button> : <span key={entry} aria-hidden="true" className="px-1 text-slate-400">…</span>)}
            <button type="button" onClick={() => goToPage(result.page + 1)} disabled={result.page >= totalPages || loading} className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 transition hover:border-brand hover:text-brand disabled:cursor-not-allowed disabled:opacity-40">下一页</button>
            <form className="flex items-center gap-1.5 pl-1" onSubmit={(event) => { event.preventDefault(); submitPageJump(); }}>
              <label htmlFor="job-search-page-jump" className="text-xs text-slate-500">跳至</label>
              <input id="job-search-page-jump" type="number" min={1} max={totalPages} value={pageDraft} onChange={(event) => setPageDraft(event.target.value)} disabled={loading} className="h-9 w-16 rounded-lg border border-slate-200 px-2 text-center text-sm text-ink outline-none focus:border-brand" />
              <button type="submit" disabled={loading} className="h-9 rounded-lg border border-slate-200 px-2.5 text-xs font-medium text-slate-600 hover:border-brand hover:text-brand disabled:opacity-40">确定</button>
            </form>
          </div>
        </div>}
      </div>
      {detailLoading ? <div className="flex min-h-[560px] items-center justify-center rounded-3xl border border-slate-200 bg-white text-sm text-slate-500">正在读取岗位详情…</div> : <DetailPanel job={selectedJob} onRefresh={() => selectedJob && void loadDetail(selectedJob)} onSave={() => void saveJob()} onAnalyze={() => void analyzeSelectedJob()} saving={saving} analyzing={analyzing} />}
    </div>
    </>}
  </section>;
}
