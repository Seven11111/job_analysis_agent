import { useCallback, useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import {
  CalendarDays,
  Check,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  GripVertical,
  History,
  Pencil,
  Plus,
  Save,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import {
  apiClient,
  LLM_REQUEST_TIMEOUT_MS,
  type ApplicationDetail,
  type ApplicationListResponse,
  type ApplicationSummary,
  type MatchSummary,
  type StatusDefinition,
  type StatusEvent,
} from "../api/client";

type AnalysisFilter = "all" | "pending_analysis" | "analyzed";
type ManagementFilters = { q: string; city: string; statusId: string; analysisState: AnalysisFilter };
type StatusColor = "blue" | "amber" | "indigo" | "violet" | "green" | "teal" | "rose" | "slate";

const statusColors: { value: StatusColor; label: string; className: string }[] = [
  { value: "blue", label: "蓝色", className: "bg-blue-50 text-blue-700 ring-blue-100" },
  { value: "amber", label: "橙色", className: "bg-amber-50 text-amber-800 ring-amber-100" },
  { value: "indigo", label: "靛蓝", className: "bg-indigo-50 text-indigo-700 ring-indigo-100" },
  { value: "violet", label: "紫色", className: "bg-violet-50 text-violet-700 ring-violet-100" },
  { value: "green", label: "绿色", className: "bg-green-50 text-green-700 ring-green-100" },
  { value: "teal", label: "青色", className: "bg-teal-50 text-teal-700 ring-teal-100" },
  { value: "rose", label: "红色", className: "bg-rose-50 text-rose-700 ring-rose-100" },
  { value: "slate", label: "灰色", className: "bg-slate-100 text-slate-700 ring-slate-200" },
];

function getColorClass(color: string | null) {
  if (color === "orange") return statusColors.find((item) => item.value === "amber")!.className;
  if (color === "purple") return statusColors.find((item) => item.value === "violet")!.className;
  return statusColors.find((item) => item.value === color)?.className ?? "bg-slate-100 text-slate-700 ring-slate-200";
}

function formatDate(value: string | null) {
  return value ? value.slice(0, 10).replaceAll("-", "/") : "日期未知";
}

function asUtcDate(value: string) {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
}

function formatDateTime(value: string | null) {
  if (!value) return "未记录";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(asUtcDate(value));
}

function toBeijingInput(value?: string | null) {
  const date = value ? asUtcDate(value) : new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "00";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

function toApiDateTime(value: string) {
  return `${value}:00+08:00`;
}

export function JobManagementPage() {
  const [searchParams] = useSearchParams();
  const requestedApplicationId = Number(searchParams.get("application")) || null;
  const [filters, setFilters] = useState<ManagementFilters>({ q: "", city: "", statusId: "", analysisState: "all" });
  const [filterDraft, setFilterDraft] = useState<ManagementFilters>({ q: "", city: "", statusId: "", analysisState: "all" });
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const [totalApplications, setTotalApplications] = useState(0);
  const [statuses, setStatuses] = useState<StatusDefinition[]>([]);
  const [selected, setSelected] = useState<ApplicationDetail | null>(null);
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [managingStatuses, setManagingStatuses] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatuses = useCallback(async () => {
    const response = await apiClient.get<StatusDefinition[]>("/applications/status-definitions");
    setStatuses(response.data);
    return response.data;
  }, []);

  const selectApplication = useCallback(async (application: ApplicationSummary) => {
    setDetailLoading(true);
    setError(null);
    try {
      const [detailResponse, matchResponse] = await Promise.all([
        apiClient.get<ApplicationDetail>(`/applications/${application.id}`),
        apiClient.get<MatchSummary[]>(`/jobs/${application.job.id}/matches`),
      ]);
      setSelected(detailResponse.data);
      setNote(detailResponse.data.note ?? "");
      setMatches(matchResponse.data);
    } catch {
      setError("岗位详情或分析历史加载失败，请稍后重试。");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const load = useCallback(async (nextFilters: ManagementFilters) => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        tab: nextFilters.analysisState,
        page: 1,
        limit: 50,
        ...(nextFilters.q.trim() ? { q: nextFilters.q.trim() } : {}),
        ...(nextFilters.city.trim() ? { city: nextFilters.city.trim() } : {}),
        ...(nextFilters.statusId ? { status_id: Number(nextFilters.statusId) } : {}),
      };
      const [applicationResponse] = await Promise.all([
        apiClient.get<ApplicationListResponse>("/applications", { params }),
        loadStatuses(),
      ]);
      const items = applicationResponse.data.items;
      setApplications(items);
      setTotalApplications(applicationResponse.data.total);
      const requested = items.find((item) => item.id === requestedApplicationId);
      if (items.length === 0) {
        setSelected(null);
        setMatches([]);
      } else {
        await selectApplication(requested ?? items[0]);
      }
    } catch {
      setError("岗位管理数据加载失败，请确认后端服务正在运行。");
    } finally {
      setLoading(false);
    }
  }, [loadStatuses, requestedApplicationId, selectApplication]);

  useEffect(() => { void load(filters); }, [load, filters]);

  async function refreshSelected() {
    if (selected) await selectApplication(selected);
  }

  async function changeStatus(statusId: number, effectiveAt: string, eventNote: string) {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.post(`/applications/${selected.id}/status`, {
        to_status_id: statusId,
        effective_at: toApiDateTime(effectiveAt),
        note: eventNote || null,
      });
      await refreshSelected();
      await refreshApplicationList();
    } catch {
      setError("状态更新失败，请检查状态和生效时间后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function updateTimelineEvent(eventId: number, values: { to_status_id?: number; effective_at?: string; note?: string | null }) {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      const payload = { ...values, effective_at: values.effective_at ? toApiDateTime(values.effective_at) : undefined };
      await apiClient.patch(`/applications/${selected.id}/timeline/${eventId}`, payload);
      await refreshSelected();
      await refreshApplicationList();
    } catch {
      setError("历史记录修改失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function refreshApplicationList() {
    const params = {
      tab: filters.analysisState,
      page: 1,
      limit: 50,
      ...(filters.q.trim() ? { q: filters.q.trim() } : {}),
      ...(filters.city.trim() ? { city: filters.city.trim() } : {}),
      ...(filters.statusId ? { status_id: Number(filters.statusId) } : {}),
    };
    const response = await apiClient.get<ApplicationListResponse>("/applications", { params });
    setApplications(response.data.items);
    setTotalApplications(response.data.total);
  }

  async function saveNote() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.patch(`/applications/${selected.id}`, { note });
      await refreshSelected();
      await refreshApplicationList();
    } catch {
      setError("备注保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function analyzeJob() {
    if (!selected) return;
    setAnalyzing(true);
    setError(null);
    try {
      const response = await apiClient.post<MatchSummary>(`/jobs/${selected.job.id}/matches`, {}, { timeout: LLM_REQUEST_TIMEOUT_MS });
      setMatches((current) => [response.data, ...current]);
      await refreshApplicationList();
    } catch (requestError) {
      const detail = (requestError as { response?: { data?: { detail?: { message?: string } } } }).response?.data?.detail?.message;
      setError(detail ? `岗位分析失败：${detail}` : "岗位分析失败，请检查模型配置和后端日志后重试。");
    } finally {
      setAnalyzing(false);
    }
  }

  async function deleteApplication() {
    if (!selected) return;
    const confirmed = window.confirm("从岗位管理中移除此岗位？状态时间线会一并移除；岗位来源记录和已生成的分析报告会保留。");
    if (!confirmed) return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.delete(`/applications/${selected.id}`);
      setSelected(null);
      setMatches([]);
      await load(filters);
    } catch {
      setError("移除岗位失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  const selectedStatus = useMemo(
    () => selected ? (statuses.find((item) => item.id === selected.current_status.id) ?? selected.current_status) : null,
    [selected, statuses],
  );

  return <section className="w-full min-w-0 space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div><p className="text-xs font-semibold uppercase tracking-[0.28em] text-brand">TRACK / 02</p><h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-ink">岗位管理</h1><p className="mt-2 text-sm text-slate-500">维护岗位进度、分析匹配度，或移除不再跟踪的岗位。</p></div>
      <button type="button" onClick={() => setManagingStatuses(true)} className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-brand/40 hover:text-brand"><Pencil size={15} />管理状态</button>
    </header>

    <form onSubmit={(event) => { event.preventDefault(); setFilters(filterDraft); }} className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:grid-cols-2 xl:grid-cols-4 xl:items-end">
      <label className="text-xs font-medium text-slate-500">岗位或公司<input value={filterDraft.q} onChange={(event) => setFilterDraft((current) => ({ ...current, q: event.target.value }))} placeholder="搜索名称、公司" className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-[#fbfdff] px-3 text-sm text-ink outline-none focus:border-brand" /></label>
      <label className="text-xs font-medium text-slate-500">城市<input value={filterDraft.city} onChange={(event) => setFilterDraft((current) => ({ ...current, city: event.target.value }))} placeholder="例如：杭州" className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-[#fbfdff] px-3 text-sm text-ink outline-none focus:border-brand" /></label>
      <label className="text-xs font-medium text-slate-500">当前状态<select value={filterDraft.statusId} onChange={(event) => setFilterDraft((current) => ({ ...current, statusId: event.target.value }))} className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-ink outline-none focus:border-brand"><option value="">所有状态</option>{statuses.map((status) => <option key={status.id} value={status.id}>{status.name}</option>)}</select></label>
      <label className="text-xs font-medium text-slate-500">分析状态<select value={filterDraft.analysisState} onChange={(event) => setFilterDraft((current) => ({ ...current, analysisState: event.target.value as AnalysisFilter }))} className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-ink outline-none focus:border-brand"><option value="all">全部</option><option value="pending_analysis">未分析</option><option value="analyzed">已分析</option></select></label>
      <div className="flex justify-end gap-2 sm:col-span-2 xl:col-span-4">
        <button type="button" onClick={() => { const empty: ManagementFilters = { q: "", city: "", statusId: "", analysisState: "all" }; setFilterDraft(empty); setFilters(empty); }} className="h-10 rounded-lg border border-slate-200 px-4 text-sm font-medium text-slate-600 hover:bg-slate-50">重置</button>
        <button type="submit" className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-ink px-4 text-sm font-semibold text-white hover:bg-slate-700"><Check size={15} />筛选</button>
      </div>
    </form>
    {!loading && <p className="-mt-4 text-xs text-slate-400">当前条件匹配 {totalApplications} 个岗位，列表最多显示前 50 个。</p>}
    {error && <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</div>}

    <div className="grid min-w-0 grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(25rem,0.95fr)] 2xl:grid-cols-[minmax(0,1.1fr)_minmax(28rem,0.9fr)]">
      <div className="min-w-0 space-y-3">
        {loading && <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">正在读取收藏岗位…</div>}
        {!loading && applications.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center"><p className="font-semibold text-ink">没有符合条件的岗位</p><p className="mt-2 text-sm text-slate-500">调整筛选条件，或先到岗位搜索页收藏感兴趣的岗位。</p></div>}
        {applications.map((application) => <button type="button" key={application.id} onClick={() => void selectApplication(application)} className={`w-full min-w-0 rounded-2xl border p-5 text-left transition ${selected?.id === application.id ? "border-brand bg-[#f2f9ff]" : "border-slate-200 bg-white hover:border-brand/50"}`}>
          <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h2 className="truncate font-semibold text-ink">{application.job.title}</h2><p className="mt-1 truncate text-sm text-slate-500">{application.job.company_name} · {application.job.city}</p></div><StatusPill status={application.current_status} /></div>
          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-400"><span className="inline-flex items-center gap-1"><CalendarDays size={14} />收藏于 {formatDateTime(application.saved_at)}</span><span className="truncate">{application.note || "暂无备注"}</span></div>
        </button>)}
      </div>
      {selected ? <Detail
        key={selected.id}
        selected={selected}
        statuses={statuses}
        selectedStatus={selectedStatus}
        matches={matches}
        note={note}
        setNote={setNote}
        saving={saving || detailLoading}
        analyzing={analyzing}
        onStatusChange={changeStatus}
        onTimelineUpdate={updateTimelineEvent}
        onSaveNote={() => void saveNote()}
        onAnalyze={() => void analyzeJob()}
        onDelete={() => void deleteApplication()}
      /> : <div className="flex min-h-[540px] min-w-0 items-center justify-center rounded-3xl border border-dashed border-slate-300 bg-white/70 text-center text-sm text-slate-400">{detailLoading ? "正在加载岗位详情…" : "选择收藏岗位查看详情和进度"}</div>}
    </div>
    {managingStatuses && <StatusManager statuses={statuses} onClose={() => setManagingStatuses(false)} onChanged={() => void loadStatuses()} />}
  </section>;
}

function StatusPill({ status }: { status: StatusDefinition }) {
  return <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${getColorClass(status.color)}`}>{status.name}</span>;
}

function Detail({
  selected,
  statuses,
  selectedStatus,
  matches,
  note,
  setNote,
  saving,
  analyzing,
  onStatusChange,
  onTimelineUpdate,
  onSaveNote,
  onAnalyze,
  onDelete,
}: {
  selected: ApplicationDetail;
  statuses: StatusDefinition[];
  selectedStatus: StatusDefinition | null;
  matches: MatchSummary[];
  note: string;
  setNote: (value: string) => void;
  saving: boolean;
  analyzing: boolean;
  onStatusChange: (statusId: number, effectiveAt: string, note: string) => Promise<void>;
  onTimelineUpdate: (eventId: number, values: { to_status_id?: number; effective_at?: string; note?: string | null }) => Promise<void>;
  onSaveNote: () => void;
  onAnalyze: () => void;
  onDelete: () => void;
}) {
  const [statusId, setStatusId] = useState(selectedStatus?.id ?? selected.current_status.id);
  const [effectiveAt, setEffectiveAt] = useState(toBeijingInput());
  const [statusNote, setStatusNote] = useState("");
  const latestMatch = matches[0] ?? null;
  const [activeMatchId, setActiveMatchId] = useState<number | null>(latestMatch?.id ?? null);
  const activeMatch = matches.find((match) => match.id === activeMatchId) ?? latestMatch;

  useEffect(() => {
    setStatusId(selectedStatus?.id ?? selected.current_status.id);
  }, [selected.current_status.id, selectedStatus?.id]);

  useEffect(() => {
    setActiveMatchId(latestMatch?.id ?? null);
  }, [latestMatch?.id]);

  return <aside className="min-w-0 rounded-3xl border border-slate-200/90 bg-white p-5 shadow-[0_18px_50px_rgba(24,64,96,0.08)] sm:p-6 xl:sticky xl:top-6 xl:max-h-[calc(100vh-3rem)] xl:overflow-y-auto">
    <div className="flex items-start justify-between gap-4"><div className="min-w-0"><p className="text-xs font-semibold uppercase tracking-[0.22em] text-brand">岗位详情</p><h2 className="mt-3 break-words text-2xl font-semibold tracking-tight text-ink">{selected.job.title}</h2><p className="mt-2 text-sm text-slate-600">{selected.job.company_name} · {selected.job.city} · {formatDate(selected.job.published_date)}</p></div><div className="flex shrink-0 items-center gap-2"><a href={selected.job.detail_url} target="_blank" rel="noreferrer" aria-label="打开岗位来源" className="rounded-xl border border-slate-200 p-2 text-slate-500 hover:text-brand"><ExternalLink size={18} /></a><button type="button" onClick={onDelete} disabled={saving} aria-label="移除岗位" className="rounded-xl border border-rose-100 p-2 text-rose-600 hover:bg-rose-50 disabled:opacity-50"><Trash2 size={18} /></button></div></div>

    <section className="mt-6 rounded-2xl border border-slate-200 p-5">
      <h3 className="inline-flex items-center gap-2 font-semibold text-ink"><History size={17} />状态时间线</h3><p className="mt-1 text-xs text-slate-500">每条历史都可以修改状态、实际发生时间和备注。</p>
      <div className="mt-4 space-y-3">{selected.timeline.length ? selected.timeline.map((event) => <TimelineEventEditor key={event.id} event={event} statuses={statuses} saving={saving} onSave={(values) => onTimelineUpdate(event.id, values)} />) : <p className="text-sm text-slate-400">暂无状态记录。</p>}</div>
    </section>

    <form className="mt-6 rounded-2xl bg-[#f2f9ff] p-5" onSubmit={(event) => { event.preventDefault(); void onStatusChange(statusId, effectiveAt, statusNote); setStatusNote(""); }}>
      <div className="flex items-center justify-between gap-3"><label htmlFor="application-status" className="text-sm font-semibold text-ink">当前状态</label>{selectedStatus && <StatusPill status={selectedStatus} />}</div>
      <select id="application-status" value={statusId} disabled={saving} onChange={(event) => setStatusId(Number(event.target.value))} className="mt-3 h-11 w-full rounded-xl border border-blue-100 bg-white px-3 text-sm font-semibold text-ink outline-none focus:border-brand">
        {!statuses.some((item) => item.id === selected.current_status.id) && <option value={selected.current_status.id}>{selected.current_status.name}（已停用）</option>}
        {statuses.map((status) => <option key={status.id} value={status.id}>{status.name}</option>)}
      </select>
      <label className="mt-4 block text-xs font-medium text-slate-500" htmlFor="status-effective-at">状态生效时间（北京时间）</label>
      <input id="status-effective-at" type="datetime-local" value={effectiveAt} onChange={(event) => setEffectiveAt(event.target.value)} disabled={saving} className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-ink outline-none focus:border-brand" />
      <input value={statusNote} onChange={(event) => setStatusNote(event.target.value)} disabled={saving} placeholder="本次进度备注（可选）" className="mt-3 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-brand" />
      <button type="submit" disabled={saving || statusId === selected.current_status.id} className="mt-3 inline-flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 text-sm font-semibold text-white transition hover:bg-[#0d76c0] disabled:cursor-not-allowed disabled:opacity-50"><Check size={16} />记录状态变化</button>
      <p className="mt-2 text-xs text-slate-500">可以补录过去发生的进度；提交时间会另行记录。</p>
    </form>

    <div className="mt-6"><div className="flex items-center justify-between"><h3 className="font-semibold text-ink">我的备注</h3><button type="button" onClick={onSaveNote} disabled={saving} className="inline-flex items-center gap-1 text-xs font-semibold text-brand"><Save size={14} />保存</button></div><textarea value={note} onChange={(event) => setNote(event.target.value)} rows={3} placeholder="记录投递准备、沟通信息或下一步行动…" className="mt-3 w-full resize-y rounded-xl border border-slate-200 bg-[#fbfdff] p-3 text-sm outline-none focus:border-brand" /></div>

    <section className="mt-7 rounded-2xl border border-slate-200 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><div><h3 className="inline-flex items-center gap-2 font-semibold text-ink"><Sparkles size={17} className="text-brand" />岗位匹配分析</h3><p className="mt-1 text-xs text-slate-500">基于当前画像、简历和岗位快照调用配置的 LLM。</p></div><button type="button" onClick={onAnalyze} disabled={analyzing || saving} className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:opacity-50"><Sparkles size={15} />{analyzing ? "模型分析中…" : latestMatch ? "重新分析" : "分析岗位"}</button></div>
      {matches.length > 1 && <label className="mt-4 block text-xs font-medium text-slate-500">分析历史<select value={activeMatch?.id ?? ""} onChange={(event) => setActiveMatchId(Number(event.target.value))} className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-ink">{matches.map((match, index) => <option key={match.id} value={match.id}>{index === 0 ? "最近一次" : `历史分析 ${index}`} · {formatDateTime(match.created_at)} · {match.match_score} 分</option>)}</select></label>}
      {activeMatch ? <MatchReportCard match={activeMatch} /> : <div className="mt-4 rounded-xl bg-mist px-4 py-5 text-center text-sm text-slate-500">还没有分析记录。点击“分析岗位”后将调用 LLM 生成匹配报告。</div>}
    </section>

  </aside>;
}

function MatchReportCard({ match }: { match: MatchSummary }) {
  const recommendation = ({ strong_match: "高度匹配", match: "较为匹配", observe: "建议观察", not_recommended: "暂不推荐" } as Record<string, string>)[match.recommendation] ?? match.recommendation;
  return <div className="mt-4 min-w-0 space-y-4"><div className="flex min-w-0 items-start justify-between gap-4 rounded-xl bg-[#f1fbf8] p-4"><div className="min-w-0"><p className="text-xs font-semibold text-teal-700">{recommendation} · {formatDateTime(match.created_at)}</p><p className="mt-2 break-words text-sm leading-6 text-slate-700">{match.summary}</p></div><div className="shrink-0 text-center"><p className="text-3xl font-semibold text-teal-700">{match.match_score}</p><p className="text-xs text-slate-500">匹配分</p></div></div>
    <MatchPoints title="匹配证据" points={match.matched_points} color="text-teal-700" />
    <MatchPoints title="待补足" points={match.missing_points} color="text-amber-700" />
    <MatchPoints title="风险提示" points={match.risk_points} color="text-rose-700" />
    <MatchPoints title="下一步建议" points={match.next_actions} color="text-brand" />
    <p className="text-right text-xs text-slate-400">{match.analysis_mode === "rules_v1" ? "历史版本：规则初筛" : `模型：${match.analysis_mode}`}</p>
  </div>;
}

function MatchPoints({ title, points, color }: { title: string; points: string[]; color: string }) {
  if (!points.length) return null;
  return <div className="min-w-0"><h4 className={`text-xs font-semibold ${color}`}>{title}</h4><ul className="mt-2 list-inside list-disc space-y-1 break-words text-sm leading-6 text-slate-600">{points.map((point, index) => <li key={`${title}-${index}`}>{point}</li>)}</ul></div>;
}

function TimelineEventEditor({ event, statuses, saving, onSave }: { event: StatusEvent; statuses: StatusDefinition[]; saving: boolean; onSave: (values: { to_status_id?: number; effective_at?: string; note?: string | null }) => void }) {
  const [editing, setEditing] = useState(false);
  const [statusId, setStatusId] = useState(event.to_status.id);
  const [effectiveAt, setEffectiveAt] = useState(toBeijingInput(event.effective_at));
  const [note, setNote] = useState(event.note ?? "");
  const eventStatuses = statuses.some((item) => item.id === event.to_status.id) ? statuses : [event.to_status, ...statuses];

  if (!editing) return <div className="relative border-l-2 border-blue-100 pb-1 pl-4"><span className="absolute -left-[5px] top-1 h-2 w-2 rounded-full bg-brand" /><div className="flex items-start justify-between gap-3"><StatusPill status={event.to_status} /><button type="button" onClick={() => setEditing(true)} aria-label="编辑这条状态历史" className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-brand"><Pencil size={14} /></button></div><p className="mt-2 text-xs text-slate-400">{formatDateTime(event.effective_at)}（北京时间）</p>{event.note && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{event.note}</p>}</div>;

  return <form className="rounded-xl border border-blue-100 bg-[#fbfdff] p-4" onSubmit={(submitEvent) => { submitEvent.preventDefault(); onSave({ ...(statusId !== event.to_status.id ? { to_status_id: statusId } : {}), effective_at: effectiveAt, note: note || null }); setEditing(false); }}>
    <label className="block text-xs font-medium text-slate-500">状态</label><select value={statusId} onChange={(inputEvent) => setStatusId(Number(inputEvent.target.value))} className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm">{eventStatuses.map((status) => <option key={status.id} value={status.id}>{status.name}{status.enabled ? "" : "（已停用）"}</option>)}</select>
    <label className="mt-3 block text-xs font-medium text-slate-500">生效时间（北京时间）</label><input type="datetime-local" value={effectiveAt} onChange={(inputEvent) => setEffectiveAt(inputEvent.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm" />
    <label className="mt-3 block text-xs font-medium text-slate-500">备注</label><textarea value={note} onChange={(inputEvent) => setNote(inputEvent.target.value)} rows={2} className="mt-1 w-full rounded-lg border border-slate-200 bg-white p-3 text-sm" />
    <div className="mt-3 flex justify-end gap-2"><button type="button" onClick={() => setEditing(false)} className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600">取消</button><button type="submit" disabled={saving} className="rounded-lg bg-brand px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">保存修改</button></div>
  </form>;
}

function StatusManager({ statuses, onClose, onChanged }: { statuses: StatusDefinition[]; onClose: () => void; onChanged: () => void }) {
  const [name, setName] = useState("");
  const [color, setColor] = useState<StatusColor>("blue");
  const [orderedStatuses, setOrderedStatuses] = useState(statuses);
  const [draggedStatusId, setDraggedStatusId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const orderChanged = orderedStatuses.some((status, index) => statuses[index]?.id !== status.id);

  useEffect(() => {
    setOrderedStatuses((current) => {
      const incomingById = new Map(statuses.map((status) => [status.id, status]));
      const retained = current.flatMap((status) => {
        const refreshed = incomingById.get(status.id);
        if (!refreshed) return [];
        incomingById.delete(status.id);
        return [refreshed];
      });
      return [...retained, ...incomingById.values()];
    });
  }, [statuses]);

  function moveStatus(statusId: number, offset: -1 | 1) {
    setOrderedStatuses((current) => {
      const from = current.findIndex((status) => status.id === statusId);
      const to = from + offset;
      if (from < 0 || to < 0 || to >= current.length) return current;
      const next = [...current];
      [next[from], next[to]] = [next[to], next[from]];
      return next;
    });
  }

  function dropStatus(sourceStatusId: number, targetStatusId: number) {
    if (sourceStatusId === targetStatusId) return;
    setOrderedStatuses((current) => {
      const next = [...current];
      const from = next.findIndex((status) => status.id === sourceStatusId);
      const to = next.findIndex((status) => status.id === targetStatusId);
      if (from < 0 || to < 0) return current;
      const [moved] = next.splice(from, 1);
      next.splice(to, 0, moved);
      return next;
    });
    setDraggedStatusId(null);
  }

  async function saveOrder() {
    setSaving(true);
    setError(null);
    try {
      for (const [index, status] of orderedStatuses.entries()) {
        await apiClient.patch(`/applications/status-definitions/${status.id}`, { sort_order: (index + 1) * 10 });
      }
      onChanged();
    } catch {
      setError("顺序保存失败；已保存的部分仍保留，请检查列表后再次保存。");
    } finally {
      setSaving(false);
    }
  }

  async function createStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const sortOrder = (Math.max(0, ...orderedStatuses.map((status) => status.sort_order)) + 10);
      await apiClient.post("/applications/status-definitions", { name: name.trim(), color, sort_order: sortOrder });
      setName("");
      onChanged();
    } catch {
      setError("新增失敗；狀態名稱可能已存在。");
    } finally {
      setSaving(false);
    }
  }

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div role="dialog" aria-modal="true" aria-labelledby="status-manager-title" className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl">
      <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand">STATUS SETTINGS</p><h2 id="status-manager-title" className="mt-1 text-2xl font-semibold text-ink">自定义岗位状态</h2><p className="mt-2 text-sm text-slate-500">可调整显示名称、颜色和顺序；停用后不会影响已有历史。</p></div><button type="button" onClick={onClose} aria-label="关闭状态管理" className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"><X size={18} /></button></div>
      {error && <p role="alert" className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      <form onSubmit={(event) => void createStatus(event)} className="mt-5 grid gap-3 rounded-2xl bg-mist p-4 sm:grid-cols-[1fr_130px_auto] sm:items-end">
        <label className="text-xs font-medium text-slate-500">新增状态<input required maxLength={64} value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：等待笔试" className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-ink" /></label>
        <ColorSelect value={color} onChange={setColor} />
        <button type="submit" disabled={saving || !name.trim()} className="inline-flex h-10 items-center justify-center gap-1 rounded-lg bg-brand px-3 text-sm font-semibold text-white disabled:opacity-50"><Plus size={15} />添加</button>
      </form>
      <p className="mt-5 text-xs text-slate-500">拖动状态行调整展示顺序，也可以用右侧箭头微调。</p>
      <div className="mt-3 space-y-2">{orderedStatuses.map((status, index) => <div key={status.id} draggable={!saving} onDragStart={(event) => { setDraggedStatusId(status.id); event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", String(status.id)); }} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "move"; }} onDrop={(event) => { event.preventDefault(); const draggedId = Number(event.dataTransfer.getData("text/plain")) || draggedStatusId; if (draggedId !== null) dropStatus(draggedId, status.id); }} onDragEnd={() => setDraggedStatusId(null)} className={`flex items-center gap-2 rounded-2xl transition ${draggedStatusId === status.id ? "opacity-40" : ""}`}>
        <span aria-label="拖动以调整顺序" className="cursor-grab touch-none rounded-lg p-2 text-slate-400 active:cursor-grabbing"><GripVertical size={18} /></span>
        <div className="min-w-0 flex-1"><StatusDefinitionRow status={status} saving={saving} onMoveUp={() => moveStatus(status.id, -1)} onMoveDown={() => moveStatus(status.id, 1)} canMoveUp={index > 0} canMoveDown={index < orderedStatuses.length - 1} onSave={async (patch) => { setSaving(true); setError(null); try { await apiClient.patch(`/applications/status-definitions/${status.id}`, patch); onChanged(); } catch { setError("状态修改失败，请重试。"); } finally { setSaving(false); } }} onDisable={async () => { if (!window.confirm(`停用“${status.name}”？已有时间线记录会保留。`)) return; setSaving(true); try { await apiClient.delete(`/applications/status-definitions/${status.id}`); onChanged(); } catch { setError("状态停用失败，请重试。"); } finally { setSaving(false); } }} /></div>
      </div>)}</div>
      <div className="mt-6 flex justify-between"><button type="button" onClick={() => void saveOrder()} disabled={saving || !orderChanged} className="inline-flex items-center gap-2 rounded-xl border border-brand px-4 py-2.5 text-sm font-semibold text-brand disabled:cursor-not-allowed disabled:opacity-40"><Save size={15} />保存顺序</button><button type="button" onClick={onClose} className="rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-white">完成</button></div>
    </div>
  </div>;
}

function ColorSelect({ value, onChange }: { value: StatusColor; onChange: (value: StatusColor) => void }) {
  return <label className="text-xs font-medium text-slate-500">颜色<select value={value} onChange={(event) => onChange(event.target.value as StatusColor)} className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-2 text-sm text-ink">{statusColors.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>;
}

function StatusDefinitionRow({ status, saving, onSave, onDisable, onMoveUp, onMoveDown, canMoveUp, canMoveDown }: { status: StatusDefinition; saving: boolean; onSave: (patch: { name: string; color: StatusColor }) => Promise<void>; onDisable: () => Promise<void>; onMoveUp: () => void; onMoveDown: () => void; canMoveUp: boolean; canMoveDown: boolean }) {
  const [name, setName] = useState(status.name);
  const initialColor = status.color === "orange" ? "amber" : status.color === "purple" ? "violet" : status.color;
  const [color, setColor] = useState<StatusColor>((statusColors.some((item) => item.value === initialColor) ? initialColor : "slate") as StatusColor);
  const changed = name.trim() !== status.name || color !== initialColor;
  return <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-3 sm:grid-cols-[minmax(8rem,1fr)_120px_auto_auto_auto_auto] sm:items-end">
    <label className="text-xs font-medium text-slate-500">状态名称<input value={name} onChange={(event) => setName(event.target.value)} maxLength={64} className="mt-1 h-10 w-full rounded-lg border border-slate-200 px-3 text-sm text-ink" /></label>
    <ColorSelect value={color} onChange={setColor} />
    <button type="button" disabled={saving || !canMoveUp} onClick={onMoveUp} aria-label={`上移${status.name}`} className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 px-2 text-slate-500 hover:text-brand disabled:opacity-30"><ChevronUp size={17} /></button>
    <button type="button" disabled={saving || !canMoveDown} onClick={onMoveDown} aria-label={`下移${status.name}`} className="inline-flex h-10 items-center justify-center rounded-lg border border-slate-200 px-2 text-slate-500 hover:text-brand disabled:opacity-30"><ChevronDown size={17} /></button>
    <button type="button" disabled={saving || !changed || !name.trim()} onClick={() => void onSave({ name: name.trim(), color })} className="inline-flex h-10 items-center justify-center gap-1 rounded-lg border border-brand px-3 text-xs font-semibold text-brand disabled:opacity-40"><Save size={14} />保存</button>
    <button type="button" disabled={saving} onClick={() => void onDisable()} aria-label={`停用${status.name}`} className="inline-flex h-10 items-center justify-center rounded-lg px-3 text-rose-600 hover:bg-rose-50 disabled:opacity-40"><Trash2 size={15} /><span className="ml-1 text-xs">停用</span></button>
  </div>;
}
