import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { CalendarDays, CheckCircle2, ExternalLink, Filter, MapPin, Search, Sparkles, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { apiClient, API_BASE_URL, LLM_REQUEST_TIMEOUT_MS, type BossLoginEvent, type BossLoginStartResponse, type BossProviderStatus, type JobDetail, type JobRecommendation, type JobSearchRequest, type JobSearchResponse, type JobSummary, type JobSubscription, type MatchSummary, type RecommendationFeedbackResponse, type SubscriptionFrequency } from "../api/client";
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
  sort_by: "recommended",
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
function subscriptionScheduleLabel(frequency: SubscriptionFrequency, scheduleTime: string, weekday: number, intervalDays: number, monthDay: number) {
  if (frequency === "manual") return "仅手动查新，不会自动运行。";
  if (frequency === "daily") return `每天 ${scheduleTime}（北京时间）`;
  if (frequency === "weekdays") return `每个工作日 ${scheduleTime}（北京时间）`;
  if (frequency === "weekly") return `每周${["", "一", "二", "三", "四", "五", "六", "日"][weekday]} ${scheduleTime}（北京时间）`;
  if (frequency === "interval") return `每隔 ${intervalDays} 天 ${scheduleTime}（北京时间）`;
  return `每月 ${monthDay} 日 ${scheduleTime}（北京时间）`;
}
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

function sortByRecommendationFeedback(items: JobSummary[]): JobSummary[] {
  const feedbackRank = (feedback: JobRecommendation["feedback"]) => feedback === "interested" ? 1 : feedback === "not_interested" ? -1 : 0;
  return [...items].sort((left, right) => {
    const feedbackDifference = feedbackRank(right.recommendation?.feedback ?? null) - feedbackRank(left.recommendation?.feedback ?? null);
    if (feedbackDifference !== 0) return feedbackDifference;
    const scoreDifference = (right.recommendation?.score ?? -1) - (left.recommendation?.score ?? -1);
    if (scoreDifference !== 0) return scoreDifference;
    return (right.published_date ?? "").localeCompare(left.published_date ?? "");
  });
}

function normalizeJobSearchResponse(value: unknown): JobSearchResponse {
  const raw = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const quality = raw.quality && typeof raw.quality === "object" ? raw.quality as Record<string, unknown> : {};
  const context = raw.recommendation_context && typeof raw.recommendation_context === "object"
    ? raw.recommendation_context as Record<string, unknown>
    : {};
  return {
    items: Array.isArray(raw.items) ? raw.items as JobSummary[] : [],
    total: typeof raw.total === "number" ? raw.total : 0,
    page: typeof raw.page === "number" ? raw.page : 1,
    limit: typeof raw.limit === "number" ? raw.limit : 20,
    quality: {
      undisclosed_salary_count: typeof quality.undisclosed_salary_count === "number" ? quality.undisclosed_salary_count : 0,
      missing_published_date_count: typeof quality.missing_published_date_count === "number" ? quality.missing_published_date_count : 0,
      providers: Array.isArray(quality.providers) ? quality.providers as JobSearchResponse["quality"]["providers"] : [],
    },
    recommendation_context: {
      sort_by: context.sort_by === "recommended" ? "recommended" : "newest",
      personalized: context.personalized === true,
      profile_used: context.profile_used === true,
      resume_used: context.resume_used === true,
      message: typeof context.message === "string" ? context.message : "暂无个性化推荐说明。",
    },
  };
}

function FeedbackActions({ feedback, disabled, onSet }: { feedback: JobRecommendation["feedback"]; disabled: boolean; onSet: (value: "interested" | "not_interested" | null) => void }) {
  return <div className="flex flex-wrap items-center gap-2">
    <span className="mr-1 text-xs text-slate-400">这条推荐</span>
    <button type="button" disabled={disabled} aria-pressed={feedback === "interested"} onClick={() => onSet(feedback === "interested" ? null : "interested")} className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs transition disabled:cursor-not-allowed disabled:opacity-40 ${feedback === "interested" ? "bg-teal-100 font-semibold text-teal-800" : "bg-slate-50 text-slate-500 hover:bg-teal-50 hover:text-teal-700"}`}><ThumbsUp size={13} />感兴趣</button>
    <button type="button" disabled={disabled} aria-pressed={feedback === "not_interested"} onClick={() => onSet(feedback === "not_interested" ? null : "not_interested")} className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs transition disabled:cursor-not-allowed disabled:opacity-40 ${feedback === "not_interested" ? "bg-rose-100 font-semibold text-rose-800" : "bg-slate-50 text-slate-500 hover:bg-rose-50 hover:text-rose-700"}`}><ThumbsDown size={13} />不感兴趣</button>
  </div>;
}

function RecommendationPreview({ job, onFeedback, feedbackDisabled = false }: { job: JobSummary; onFeedback: (value: "interested" | "not_interested" | null) => void; feedbackDisabled?: boolean }) {
  const recommendation = job.recommendation;
  if (!recommendation) return null;
  return <section className="mt-5 rounded-2xl border border-blue-100 bg-[#f5faff] p-4">
    <div className="flex items-start justify-between gap-3">
      <div><p className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink"><Sparkles size={15} className="text-brand" />智能推荐依据</p><p className="mt-1 text-xs leading-5 text-slate-500">规则参考，不代表录用概率；简历未提及不等于不具备。</p></div>
      <span className="shrink-0 rounded-full bg-white px-3 py-1 text-sm font-semibold text-brand">{recommendation.score === null ? "完善画像" : `${recommendation.score} 分`}</span>
    </div>
    {recommendation.matched_points.length > 0 && <div className="mt-3 space-y-1.5">{recommendation.matched_points.slice(0, 3).map((point) => <p key={point} className="flex items-start gap-2 text-xs leading-5 text-slate-600"><CheckCircle2 size={14} className="mt-0.5 shrink-0 text-teal-600" />{point}</p>)}</div>}
    {recommendation.missing_points.length > 0 && <p className="mt-2 text-xs leading-5 text-amber-700">待核对：{recommendation.missing_points[0]}</p>}
    {recommendation.unknown_points.length > 0 && <p className="mt-2 text-xs leading-5 text-slate-500">未知：{recommendation.unknown_points[0]}</p>}
    <div className="mt-3 border-t border-blue-100 pt-3"><FeedbackActions feedback={recommendation.feedback} disabled={feedbackDisabled} onSet={onFeedback} /></div>
  </section>;
}

function SearchCard({ job, active, onSelect, onFeedback, feedbackDisabled }: { job: JobSummary; active: boolean; onSelect: () => void; onFeedback: (value: "interested" | "not_interested" | null) => void; feedbackDisabled: boolean }) {
  return <article className={`rounded-2xl border p-4 transition ${active ? "border-brand bg-[#f2f9ff] shadow-[0_10px_30px_rgba(22,136,216,0.12)]" : "border-slate-200/90 bg-white hover:border-brand/50 hover:shadow-lg"}`}>
    <button type="button" onClick={onSelect} className="group w-full text-left">
      <div className="flex items-start justify-between gap-5"><div className="min-w-0"><div className="flex items-center gap-2"><span className="h-2 w-2 rounded-full bg-teal-400" /><h2 className="truncate text-xl font-semibold tracking-tight text-ink group-hover:text-brand">{job.title}</h2></div><p className="mt-2 font-medium text-slate-600">{job.company_name}</p><div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-500"><span className="inline-flex items-center gap-1.5"><MapPin size={15} />{job.city}{job.district ? ` · ${job.district}` : ""}</span><span className="inline-flex items-center gap-1.5"><CalendarDays size={15} />{formatDate(job.published_date)}</span></div></div><span className="shrink-0 rounded-full bg-[#e7f7f2] px-3 py-1 text-xs font-semibold text-teal-700">{job.salary.display}</span></div>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-xs"><span className="rounded-full bg-blue-50 px-3 py-1 font-medium text-brand">{job.job_type}</span>{job.education && <span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">{job.education}</span>}<span className="rounded-full bg-slate-100 px-3 py-1 text-slate-600">{extractionLabel(job.extraction_method)}</span><span className="ml-auto text-slate-400">来源：{job.source.name}</span></div>
    </button>
    <RecommendationPreview job={job} onFeedback={onFeedback} feedbackDisabled={feedbackDisabled} />
  </article>;
}

function DetailPanel({ job, onRefresh, onSave, onAnalyze, onFeedback, feedbackDisabled, saving, analyzing }: { job: JobDetail | null; onRefresh: () => void; onSave: () => void; onAnalyze: () => void; onFeedback: (value: "interested" | "not_interested" | null) => void; feedbackDisabled: boolean; saving: boolean; analyzing: boolean }) {
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
    <RecommendationPreview job={job} onFeedback={onFeedback} feedbackDisabled={feedbackDisabled} />
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
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
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
  const [feedbackLoadingToken, setFeedbackLoadingToken] = useState<string | null>(null);
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null);
  const [editingSubscriptionId, setEditingSubscriptionId] = useState<number | null>(null);
  const [subscriptionModalOpen, setSubscriptionModalOpen] = useState(false);
  const [subscriptionName, setSubscriptionName] = useState("");
  const [subscriptionFrequency, setSubscriptionFrequency] = useState<SubscriptionFrequency>("manual");
  const [subscriptionTime, setSubscriptionTime] = useState("09:00");
  const [subscriptionWeekday, setSubscriptionWeekday] = useState(1);
  const [subscriptionIntervalDays, setSubscriptionIntervalDays] = useState(3);
  const [subscriptionMonthDay, setSubscriptionMonthDay] = useState(1);
  const [subscriptionSaving, setSubscriptionSaving] = useState(false);
  const [subscriptionError, setSubscriptionError] = useState<string | null>(null);

  const editSubscriptionParam = searchParams.get("editSubscription");
  useEffect(() => {
    if (!editSubscriptionParam) return;
    let cancelled = false;
    async function loadSubscriptionForEdit() {
      try {
        const response = await apiClient.get<JobSubscription>(`/subscriptions/${editSubscriptionParam}`);
        if (cancelled) return;
        const subscription = response.data;
        setEditingSubscriptionId(subscription.id);
        setSubscriptionName(subscription.name);
        setSubscriptionFrequency(subscription.frequency);
        setSubscriptionTime(subscription.schedule_time);
        setSubscriptionWeekday(subscription.weekday ?? 1);
        setSubscriptionIntervalDays(subscription.interval_days ?? 3);
        setSubscriptionMonthDay(subscription.month_day ?? 1);
        setFilters((current) => ({
          ...initialFilters,
          ...subscription.filters,
          page: 1,
          limit: current.limit,
          providers: (subscription.filters.providers ?? []) as JobSearchProvider[],
          cities: subscription.filters.cities ?? [],
        }));
      } catch {
        if (!cancelled) setError("无法读取要编辑的岗位查新条件。");
      }
    }
    void loadSubscriptionForEdit();
    return () => { cancelled = true; };
  }, [editSubscriptionParam]);

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
    setFeedbackNotice(null);
    if (nextFilters.providers?.includes("boss_agent_cli")) {
      const currentStatus = await refreshBossStatus();
      if (!currentStatus?.authenticated) {
        const started = await startBossLogin();
        if (started) setError("BOSS 登录页已在项目专用 Chrome 中打开；完成登录后再次点击“搜索”即可继续，本次条件已保留。");
        return;
      }
    }
    setLoading(true); setError(null);
    try {
      const response = await apiClient.post<JobSearchResponse>("/jobs/search", nextFilters);
      const normalized = normalizeJobSearchResponse(response.data);
      setResult(normalized);
      if (normalized.items.length > 0) await loadDetail(normalized.items[0]); else setSelectedJob(null);
    }
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

  const updateRecommendationFeedback = useCallback(async (job: JobSummary, feedback: "interested" | "not_interested" | null) => {
    if (!job.result_token) return;
    const token = job.result_token;
    setFeedbackLoadingToken(token);
    setFeedbackNotice(null);
    try {
      const response = await apiClient.put<RecommendationFeedbackResponse>(`/jobs/search-results/${token}/feedback`, { feedback });
      setResult((current) => {
        if (!current) return current;
        const items = current.items.map((item) => item.result_token === token && item.recommendation
          ? { ...item, recommendation: { ...item.recommendation, feedback: response.data.feedback } }
          : item);
        return { ...current, items: current.recommendation_context.sort_by === "recommended" ? sortByRecommendationFeedback(items) : items };
      });
      setSelectedJob((current) => current?.result_token === token && current.recommendation
        ? { ...current, recommendation: { ...current.recommendation, feedback: response.data.feedback } }
        : current);
      setFeedbackNotice(response.data.message);
    } catch {
      setError("推荐反馈未能保存到当前搜索，请稍后重试。");
    } finally {
      setFeedbackLoadingToken(null);
    }
  }, []);

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

  function openSubscriptionModal() {
    if (!filters.providers?.length) {
      setSubscriptionError("请至少选择一个岗位来源后再保存查新条件。");
      return;
    }
    if (!editingSubscriptionId) {
      setSubscriptionName(`${filters.keyword?.trim() || filters.cities?.[0] || "岗位"} 查新`);
      setSubscriptionFrequency("manual");
      setSubscriptionIntervalDays(3);
      setSubscriptionMonthDay(1);
    }
    setSubscriptionError(null);
    setSubscriptionModalOpen(true);
  }

  async function saveSubscription(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!filters.providers?.length) {
      setSubscriptionError("请至少选择一个岗位来源后再保存查新条件。");
      return;
    }
    setSubscriptionSaving(true);
    setSubscriptionError(null);
    const payload = {
      name: subscriptionName.trim(),
      filters: { ...filters, page: 1 },
      frequency: subscriptionFrequency,
      schedule_time: subscriptionTime,
      weekday: subscriptionFrequency === "weekly" ? subscriptionWeekday : null,
      interval_days: subscriptionFrequency === "interval" ? subscriptionIntervalDays : null,
      month_day: subscriptionFrequency === "monthly" ? subscriptionMonthDay : null,
    };
    try {
      if (editingSubscriptionId) await apiClient.patch(`/subscriptions/${editingSubscriptionId}`, payload);
      else await apiClient.post("/subscriptions", payload);
      setSubscriptionModalOpen(false);
      navigate("/jobs/subscriptions");
    } catch (requestError) {
      const detail = (requestError as { response?: { data?: { detail?: { message?: string } | string } } }).response?.data?.detail;
      setSubscriptionError(typeof detail === "string" ? detail : detail?.message ?? "无法保存岗位查新，请检查条件后重试。");
    } finally {
      setSubscriptionSaving(false);
    }
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
    {editingSubscriptionId && <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-teal-200 bg-[#f1fbf8] px-4 py-3 text-sm text-teal-800"><span>正在编辑已保存的岗位查新条件。修改后点击“更新查新条件”保存。</span><button type="button" onClick={() => navigate("/jobs/search")} className="font-semibold underline underline-offset-2">取消编辑</button></div>}
    <form onSubmit={(event) => { event.preventDefault(); if (noProviderSelected) { setError("请至少选择一个岗位来源后再搜索。"); return; } const nextFilters = { ...filters, page: 1 }; setFilters(nextFilters); void search(nextFilters); }} className="rounded-3xl border border-slate-200/90 bg-white p-5 shadow-[0_14px_40px_rgba(24,64,96,0.06)] sm:p-6">
      <div className="grid gap-3 xl:grid-cols-[minmax(14rem,1.5fr)_minmax(8rem,.75fr)_minmax(8rem,.75fr)_minmax(9rem,.9fr)_minmax(9rem,.8fr)_auto]">
        <label className="relative block"><Search className="absolute left-4 top-3.5 text-slate-400" size={19} /><input value={filters.keyword ?? ""} onChange={(event) => updateFilter("keyword", event.target.value)} placeholder="搜索岗位或公司，例如 Python 后端" className="h-12 w-full rounded-xl border border-slate-200 bg-[#fbfdff] pl-11 pr-4 text-sm outline-none transition focus:border-brand focus:ring-4 focus:ring-brand/10" /></label>
        <label className="relative block"><CalendarDays className="absolute left-4 top-3.5 text-slate-400" size={18} /><select value={filters.published_range} onChange={(event) => updateFilter("published_range", event.target.value as JobSearchRequest["published_range"])} className="h-12 w-full appearance-none rounded-xl border border-slate-200 bg-[#fbfdff] pl-11 pr-3 text-sm outline-none focus:border-brand"><option value="all">不限日期</option>{dateOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="relative block"><Filter className="absolute left-4 top-3.5 text-slate-400" size={18} /><select value={filters.salary_mode} onChange={(event) => updateFilter("salary_mode", event.target.value as JobSearchRequest["salary_mode"])} className="h-12 w-full appearance-none rounded-xl border border-slate-200 bg-[#fbfdff] pl-11 pr-3 text-sm outline-none focus:border-brand"><option value="any">不限薪资</option><option value="disclosed_only">只看已公开</option></select></label>
        <MultiSelect label="来源" values={filters.providers ?? []} options={providerOptions} onToggle={(value) => toggleFilterValue("providers", value)} />
        <label className="relative block"><Sparkles className="absolute left-3.5 top-3.5 text-slate-400" size={17} /><select value={filters.sort_by ?? "recommended"} onChange={(event) => updateFilter("sort_by", event.target.value as JobSearchRequest["sort_by"])} className="h-12 w-full appearance-none rounded-xl border border-slate-200 bg-[#fbfdff] pl-10 pr-3 text-sm outline-none focus:border-brand"><option value="recommended">智能推荐</option><option value="newest">最新发布</option></select></label>
        <button type="submit" disabled={loading || bossLoginLoading || noProviderSelected} className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-ink px-6 text-sm font-semibold text-white transition hover:bg-[#203c61] disabled:cursor-not-allowed disabled:opacity-60"><Search size={17} />{bossSearchBlocked ? "在 Chrome 登录" : noProviderSelected ? "选择来源" : loading ? "搜索中" : "搜索"}</button>
      </div>
      <div className="mt-4 border-t border-slate-100 pt-4">
        <CityPicker values={filters.cities ?? []} onChange={(cities) => updateFilter("cities", cities)} />
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4"><p className="text-xs leading-5 text-slate-400">仅搜索实习岗位；城市和来源可多选，搜索结果不会自动保存。查新结果只在岗位查新页展示，不会自动加入岗位管理。</p><div className="flex items-center gap-3"><span className="text-xs text-amber-600">{noProviderSelected ? "至少选择一个岗位来源" : filters.providers?.includes("job_pro") && filters.published_range !== "all" ? "job-pro 部分岗位日期未知，日期筛选会排除这些结果" : ""}</span><button type="button" onClick={openSubscriptionModal} disabled={noProviderSelected} className="inline-flex h-10 items-center gap-2 rounded-xl border border-teal-200 bg-white px-4 text-sm font-semibold text-teal-800 transition hover:bg-[#f1fbf8] disabled:cursor-not-allowed disabled:opacity-50"><CalendarDays size={16} />{editingSubscriptionId ? "更新查新条件" : "保存为岗位查新"}</button></div></div>
    </form>
    {error && <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</div>}
    {result && <div className="rounded-2xl border border-blue-100 bg-[#f5faff] px-4 py-3 text-sm text-slate-600"><div className="flex flex-wrap items-center gap-2"><Sparkles size={16} className="text-brand" /><span className="font-semibold text-ink">{result.recommendation_context.sort_by === "recommended" ? "智能推荐" : "最新发布"}</span><span>{result.recommendation_context.message}</span></div><p className="mt-1 text-xs text-slate-400">{result.recommendation_context.sort_by === "recommended" ? "智能排序中，感兴趣岗位前置、不感兴趣岗位后置。" : "当前按发布日期排序；反馈仅在切换到智能推荐排序时影响顺序。"} 反馈只保留在本次搜索的服务进程内，岗位需手动保存。来源：{result.quality.providers.map((provider) => `${provider.provider} ${provider.status === "success" ? "可用" : "失败"}`).join(" · ")} · {result.quality.undisclosed_salary_count} 个岗位薪资未公开 · {result.quality.missing_published_date_count} 个岗位日期未知</p>{feedbackNotice && <p role="status" className="mt-1 text-xs text-teal-700">{feedbackNotice}</p>}</div>}
    <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(25rem,0.95fr)] 2xl:grid-cols-[minmax(0,1.1fr)_minmax(28rem,0.9fr)]">
      <div className="min-w-0 space-y-4">
        {loading && <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">正在读取岗位来源…</div>}
        {!loading && result?.items.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center"><p className="text-lg font-semibold text-ink">没有符合条件的岗位</p><p className="mt-2 text-sm text-slate-500">可以放宽城市或发布日期条件后再试。</p></div>}
        {!loading && result?.items.map((job) => <SearchCard key={job.result_token ?? job.id} job={job} active={selectedJob?.id === job.id && selectedJob?.result_token === job.result_token} onSelect={() => void loadDetail(job)} onFeedback={(value) => void updateRecommendationFeedback(job, value)} feedbackDisabled={!job.result_token || feedbackLoadingToken === job.result_token} />)}
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
      {detailLoading ? <div className="flex min-h-[560px] items-center justify-center rounded-3xl border border-slate-200 bg-white text-sm text-slate-500">正在读取岗位详情…</div> : <DetailPanel job={selectedJob} onRefresh={() => selectedJob && void loadDetail(selectedJob)} onSave={() => void saveJob()} onAnalyze={() => void analyzeSelectedJob()} onFeedback={(value) => selectedJob && void updateRecommendationFeedback(selectedJob, value)} feedbackDisabled={!selectedJob?.result_token || feedbackLoadingToken === selectedJob?.result_token} saving={saving} analyzing={analyzing} />}
    </div>
    {subscriptionModalOpen && <div className="fixed inset-0 z-50 grid place-items-center bg-ink/35 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSubscriptionModalOpen(false); }}>
      <form onSubmit={(event) => void saveSubscription(event)} role="dialog" aria-modal="true" aria-labelledby="subscription-modal-title" className="w-full max-w-xl space-y-5 rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">JOB DISCOVERY</p><h2 id="subscription-modal-title" className="mt-1 text-xl font-semibold text-ink">{editingSubscriptionId ? "更新岗位查新" : "保存岗位查新"}</h2><p className="mt-1 text-sm leading-5 text-slate-500">按当前搜索条件查找新岗位；结果需要你确认后才进入岗位管理。</p></div><button type="button" aria-label="关闭" onClick={() => setSubscriptionModalOpen(false)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-ink"><X size={18} /></button></div>
        <label className="block text-sm font-medium text-slate-700">查新名称<input required maxLength={120} value={subscriptionName} onChange={(event) => setSubscriptionName(event.target.value)} placeholder="例如：杭州 Agent 实习" className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-teal-600 focus:ring-4 focus:ring-teal-600/10" /></label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-slate-700">查新频率<select value={subscriptionFrequency} onChange={(event) => setSubscriptionFrequency(event.target.value as SubscriptionFrequency)} className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-600"><option value="manual">仅手动</option><option value="daily">每天</option><option value="weekdays">每个工作日</option><option value="weekly">每周</option><option value="interval">间隔 N 天</option><option value="monthly">每月</option></select></label>
          {subscriptionFrequency !== "manual" && <label className="block text-sm font-medium text-slate-700">{subscriptionFrequency === "daily" ? "每天运行时间" : "运行时间"}（北京时间）<input type="time" step={60} value={subscriptionTime} onChange={(event) => setSubscriptionTime(event.target.value)} required className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-teal-600" /><span className="mt-1 block text-xs font-normal text-slate-400">24 小时制，精确到分钟，例如 08:35；不设置秒。</span></label>}
          {subscriptionFrequency === "weekly" && <label className="block text-sm font-medium text-slate-700">每周几<select value={subscriptionWeekday} onChange={(event) => setSubscriptionWeekday(Number(event.target.value))} className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-600">{[[1, "周一"], [2, "周二"], [3, "周三"], [4, "周四"], [5, "周五"], [6, "周六"], [7, "周日"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>}
          {subscriptionFrequency === "interval" && <label className="block text-sm font-medium text-slate-700">间隔天数<input type="number" min={2} max={30} step={1} value={subscriptionIntervalDays} onChange={(event) => { const days = Number(event.target.value); setSubscriptionIntervalDays(Math.min(30, Math.max(2, days || 2))); }} className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-600" /><span className="mt-1 block text-xs font-normal text-slate-400">可设置每 2–30 天查新一次。</span></label>}
          {subscriptionFrequency === "monthly" && <label className="block text-sm font-medium text-slate-700">每月几号<select value={subscriptionMonthDay} onChange={(event) => setSubscriptionMonthDay(Number(event.target.value))} className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-600">{Array.from({ length: 31 }, (_, index) => index + 1).map((day) => <option key={day} value={day}>{day} 日</option>)}</select><span className="mt-1 block text-xs font-normal text-slate-400">当月没有该日期时，按当月最后一天执行。</span></label>}
        </div>
        <div className="rounded-xl bg-[#f8faf9] px-3 py-3 text-xs leading-5 text-slate-500"><p className="font-semibold text-ink">计划预览：{subscriptionScheduleLabel(subscriptionFrequency, subscriptionTime, subscriptionWeekday, subscriptionIntervalDays, subscriptionMonthDay)}</p><p className="mt-1">按 Linux cron 的分钟级调度思路，在指定北京时间分钟检查一次；仅本地后端运行期间执行。间隔查新最低为每 2 天一次，不发送外部通知。</p></div>
        {subscriptionError && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{subscriptionError}</p>}
        <div className="flex justify-end gap-3 border-t border-slate-100 pt-4"><button type="button" onClick={() => setSubscriptionModalOpen(false)} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600">取消</button><button type="submit" disabled={subscriptionSaving || !subscriptionName.trim()} className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{subscriptionSaving && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}{subscriptionSaving ? "保存中…" : editingSubscriptionId ? "保存修改" : "创建查新"}</button></div>
      </form>
    </div>}
    </>}
  </section>;
}
