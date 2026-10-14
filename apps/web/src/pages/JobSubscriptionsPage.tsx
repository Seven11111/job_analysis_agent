import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  BellRing,
  BriefcaseBusiness,
  CalendarClock,
  Check,
  Clock3,
  ExternalLink,
  LoaderCircle,
  Pencil,
  Pause,
  Play,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";

import {
  apiClient,
  type JobSubscription,
  type SubscriptionRunDetail,
  type SubscriptionRunItem,
  type SubscriptionRunStatus,
  type SubscriptionRunSummary,
  type SubscriptionSaveResponse,
  type SubscriptionFrequency,
} from "../api/client";

const providerLabels: Record<string, string> = {
  boss_agent_cli: "BOSS 直聘",
  job_pro: "job-pro",
};

const statusLabels: Record<SubscriptionRunStatus, { label: string; className: string }> = {
  running: { label: "查新中", className: "bg-blue-50 text-blue-700" },
  succeeded: { label: "发现新岗位", className: "bg-teal-50 text-teal-700" },
  no_new: { label: "暂无新岗位", className: "bg-slate-100 text-slate-600" },
  partial_failed: { label: "部分来源失败", className: "bg-amber-50 text-amber-700" },
  failed: { label: "查新失败", className: "bg-rose-50 text-rose-700" },
  interrupted: { label: "运行中断", className: "bg-rose-50 text-rose-700" },
};

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "尚未运行";
  const normalized = /Z|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(normalized));
}

function frequencyLabel(subscription: JobSubscription): string {
  if (subscription.frequency === "manual") return "仅手动查新";
  if (subscription.frequency === "daily") return `每天 ${subscription.schedule_time}`;
  if (subscription.frequency === "weekdays") return `每个工作日 ${subscription.schedule_time}`;
  if (subscription.frequency === "interval") return `每 ${subscription.interval_days ?? 3} 天 ${subscription.schedule_time}`;
  if (subscription.frequency === "monthly") return `每月 ${subscription.month_day ?? 1} 日 ${subscription.schedule_time}`;
  const weekday = ["", "周一", "周二", "周三", "周四", "周五", "周六", "周日"][subscription.weekday ?? 1];
  return `每周${weekday.slice(1)} ${subscription.schedule_time}`;
}

function schedulePreview(frequency: SubscriptionFrequency, time: string, weekday: number, intervalDays: number, monthDay: number): string {
  if (frequency === "manual") return "仅手动查新，不会自动运行。";
  if (frequency === "daily") return `每天 ${time}（北京时间）`;
  if (frequency === "weekdays") return `每个工作日 ${time}（北京时间）`;
  if (frequency === "weekly") return `每周${["", "一", "二", "三", "四", "五", "六", "日"][weekday]} ${time}（北京时间）`;
  if (frequency === "interval") return `每隔 ${intervalDays} 天 ${time}（北京时间）`;
  return `每月 ${monthDay} 日 ${time}（北京时间）`;
}

function filterSummary(subscription: JobSubscription): string[] {
  const filters = subscription.filters;
  return [
    filters.keyword?.trim() || filters.company?.trim() || "不限关键词",
    filters.cities?.length ? filters.cities.join("、") : "不限城市",
    filters.providers?.map((provider) => providerLabels[provider] ?? provider).join("、") || "未选择来源",
    filters.published_range && filters.published_range !== "all" ? `最近 ${filters.published_range.replace("d", " 天")}` : "不限日期",
  ];
}

function StatusPill({ run }: { run: SubscriptionRunSummary | null }) {
  if (!run) return <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-500">尚未查新</span>;
  const status = statusLabels[run.status];
  return <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${status.className}`}>{status.label}</span>;
}

function RunItemCard({
  item,
  saving,
  onSave,
}: {
  item: SubscriptionRunItem;
  saving: boolean;
  onSave: () => void;
}) {
  const { job } = item;
  return <article className="rounded-2xl border border-slate-200 bg-white p-4 transition hover:border-teal-200 hover:shadow-[0_10px_26px_rgba(19,89,78,0.07)] sm:p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="break-words text-base font-semibold tracking-tight text-ink">{job.title}</h3>
          {item.is_new && <span className="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] font-semibold text-teal-700">新发现</span>}
        </div>
        <p className="mt-1 text-sm text-slate-600">{job.company_name}</p>
      </div>
      <span className="shrink-0 rounded-full bg-[#e7f7f2] px-3 py-1 text-xs font-semibold text-teal-700">{job.salary.display}</span>
    </div>
    <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-slate-500">
      <span>{job.city || "地点未说明"}</span>
      <span>{job.published_date || "发布日期未知"}</span>
      <span>{providerLabels[item.provider] ?? item.provider}</span>
    </div>
    <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
      <a href={job.detail_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-xs font-medium text-brand hover:underline">
        查看来源 <ExternalLink size={13} />
      </a>
      {item.saved_job_id ? (
        <span className="inline-flex items-center gap-1.5 rounded-lg bg-teal-50 px-3 py-2 text-xs font-semibold text-teal-700"><Check size={14} />已在岗位管理</span>
      ) : (
        <button type="button" disabled={saving} onClick={onSave} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white transition hover:bg-[#29435e] disabled:opacity-50">
          {saving ? <LoaderCircle size={14} className="animate-spin" /> : <BriefcaseBusiness size={14} />}
          保存到岗位管理
        </button>
      )}
    </div>
  </article>;
}

export function JobSubscriptionsPage() {
  const [subscriptions, setSubscriptions] = useState<JobSubscription[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [runs, setRuns] = useState<SubscriptionRunSummary[]>([]);
  const [runDetail, setRunDetail] = useState<SubscriptionRunDetail | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);
  const [savingItemId, setSavingItemId] = useState<number | null>(null);
  const [changingId, setChangingId] = useState<number | null>(null);
  const [editingSubscription, setEditingSubscription] = useState<JobSubscription | null>(null);
  const [editName, setEditName] = useState("");
  const [editFrequency, setEditFrequency] = useState<SubscriptionFrequency>("manual");
  const [editTime, setEditTime] = useState("09:00");
  const [editWeekday, setEditWeekday] = useState(1);
  const [editIntervalDays, setEditIntervalDays] = useState(3);
  const [editMonthDay, setEditMonthDay] = useState(1);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const loadSubscriptions = useCallback(async (preferredId?: number | null) => {
    setLoading(true);
    try {
      const response = await apiClient.get<{ items: JobSubscription[] }>("/subscriptions");
      setSubscriptions(response.data.items);
      setSelectedId((currentId) => {
        const nextId = preferredId ?? currentId ?? response.data.items[0]?.id ?? null;
        return response.data.items.some((item) => item.id === nextId) ? nextId : response.data.items[0]?.id ?? null;
      });
      setError(null);
    } catch {
      setError("无法读取岗位查新，请确认后端已启动。");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRunDetail = useCallback(async (subscriptionId: number, runId: number, nextPage = 1) => {
    try {
      const response = await apiClient.get<SubscriptionRunDetail>(`/subscriptions/${subscriptionId}/runs/${runId}`, {
        params: { page: nextPage, limit: 20 },
      });
      setRunDetail(response.data);
      setPage(nextPage);
    } catch {
      setError("这次查新的预览已过期或暂时无法读取。");
    }
  }, []);

  useEffect(() => { void loadSubscriptions(); }, [loadSubscriptions]);

  useEffect(() => {
    if (!editingSubscription) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape" && !savingEdit) setEditingSubscription(null);
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [editingSubscription, savingEdit]);

  useEffect(() => {
    if (!selectedId) {
      setRuns([]);
      setRunDetail(null);
      return;
    }
    let cancelled = false;
    async function loadSelectedRuns() {
      try {
        const response = await apiClient.get<{ items: SubscriptionRunSummary[] }>(`/subscriptions/${selectedId}/runs`, {
          params: { page: 1, limit: 10 },
        });
        if (cancelled) return;
        setRuns(response.data.items);
        const latest = response.data.items[0];
        if (latest) await loadRunDetail(selectedId!, latest.id);
        else setRunDetail(null);
      } catch {
        if (!cancelled) setRuns([]);
      }
    }
    void loadSelectedRuns();
    return () => { cancelled = true; };
  }, [selectedId, loadRunDetail]);

  const selectedSubscription = useMemo(
    () => subscriptions.find((item) => item.id === selectedId) ?? null,
    [subscriptions, selectedId],
  );

  function openSubscriptionEditor(subscription: JobSubscription) {
    setEditingSubscription(subscription);
    setEditName(subscription.name);
    setEditFrequency(subscription.frequency);
    setEditTime(subscription.schedule_time);
    setEditWeekday(subscription.weekday ?? 1);
    setEditIntervalDays(subscription.interval_days ?? 3);
    setEditMonthDay(subscription.month_day ?? 1);
    setEditError(null);
  }

  async function saveSubscriptionSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingSubscription) return;
    setSavingEdit(true);
    setEditError(null);
    const subscriptionId = editingSubscription.id;
    try {
      await apiClient.patch(`/subscriptions/${subscriptionId}`, {
        name: editName.trim(),
        frequency: editFrequency,
        schedule_time: editTime,
        weekday: editFrequency === "weekly" ? editWeekday : null,
        interval_days: editFrequency === "interval" ? editIntervalDays : null,
        month_day: editFrequency === "monthly" ? editMonthDay : null,
      });
      setEditingSubscription(null);
      await loadSubscriptions(subscriptionId);
    } catch (requestError) {
      const message = (requestError as { response?: { data?: { detail?: { message?: string } | string } } }).response?.data?.detail;
      setEditError(typeof message === "string" ? message : message?.message ?? "保存失败，请检查设置后重试。");
    } finally {
      setSavingEdit(false);
    }
  }

  async function runNow(subscription: JobSubscription) {
    setRunningId(subscription.id);
    setError(null);
    try {
      const response = await apiClient.post<SubscriptionRunSummary>(`/subscriptions/${subscription.id}/runs`);
      await loadSubscriptions(subscription.id);
      await loadRunDetail(subscription.id, response.data.id);
    } catch (requestError) {
      const message = (requestError as { response?: { data?: { detail?: { message?: string } } } }).response?.data?.detail?.message;
      setError(message ?? "启动查新失败，请稍后重试。");
    } finally {
      setRunningId(null);
    }
  }

  async function toggleSubscription(subscription: JobSubscription) {
    setChangingId(subscription.id);
    try {
      await apiClient.patch(`/subscriptions/${subscription.id}`, { enabled: !subscription.enabled });
      await loadSubscriptions(subscription.id);
    } catch {
      setError("更新查新状态失败，请重试。");
    } finally {
      setChangingId(null);
    }
  }

  async function deleteSubscription(subscription: JobSubscription) {
    if (!window.confirm(`删除“${subscription.name}”？岗位查新记录也会一并删除，已保存到岗位管理的岗位不会受影响。`)) return;
    setChangingId(subscription.id);
    try {
      await apiClient.delete(`/subscriptions/${subscription.id}`);
      await loadSubscriptions(selectedId === subscription.id ? null : selectedId);
    } catch {
      setError("删除岗位查新失败，请重试。");
    } finally {
      setChangingId(null);
    }
  }

  async function saveItem(item: SubscriptionRunItem) {
    setSavingItemId(item.id);
    try {
      const response = await apiClient.post<SubscriptionSaveResponse>(`/subscriptions/items/${item.id}/save`);
      setRunDetail((current) => current ? {
        ...current,
        items: current.items.map((candidate) => candidate.id === item.id
          ? { ...candidate, saved_job_id: response.data.job_id }
          : candidate),
      } : current);
    } catch {
      setError("岗位保存失败，请稍后重试；查新预览仍然保留。");
    } finally {
      setSavingItemId(null);
    }
  }

  const totalPages = runDetail ? Math.max(1, Math.ceil(runDetail.total_items / runDetail.limit)) : 1;

  return <section className="space-y-7">
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-brand">DISCOVERY / 03</p>
        <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-ink">岗位查新</h1>
        <p className="mt-2 text-sm text-slate-500">保存搜索条件，查看新发现；确认后再加入岗位管理。</p>
      </div>
      <Link to="/jobs/search" className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#29435e]"><Search size={16} />去岗位搜索</Link>
    </header>

    <aside className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-[#fffaf0] px-4 py-4 text-sm text-amber-900 sm:px-5">
      <BellRing size={18} className="mt-0.5 shrink-0 text-amber-700" />
      <div><p className="font-semibold">仅应用内查新，不发送外部消息</p><p className="mt-1 leading-6 text-amber-800">每日/每周任务只会在本地后端运行时执行；QQ、邮件等通知渠道留待后续版本。</p></div>
    </aside>

    {error && <div role="alert" className="flex items-start gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700"><AlertCircle size={17} className="mt-0.5 shrink-0" />{error}</div>}

    <div className="grid items-start gap-6 xl:grid-cols-[minmax(19rem,0.82fr)_minmax(0,1.18fr)]">
      <section className="space-y-4">
        <div className="flex items-center justify-between px-1">
          <div><h2 className="text-lg font-semibold text-ink">我的查新条件</h2><p className="mt-1 text-xs text-slate-500">{subscriptions.length} 条已保存</p></div>
          <Link to="/jobs/search" className="text-sm font-medium text-brand hover:underline">＋ 从搜索创建</Link>
        </div>
        {loading && <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500"><LoaderCircle size={18} className="mx-auto mb-2 animate-spin" />正在读取查新配置…</div>}
        {!loading && subscriptions.length === 0 && <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
          <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-[#e7f7f2] text-teal-700"><Search size={21} /></div>
          <h3 className="mt-4 font-semibold text-ink">还没有保存查新条件</h3>
          <p className="mx-auto mt-2 max-w-xs text-sm leading-6 text-slate-500">先在岗位搜索中选择关键词、城市和来源，再保存为查新条件。</p>
          <Link to="/jobs/search" className="mt-5 inline-flex rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-ink hover:border-brand hover:text-brand">开始搜索</Link>
        </div>}
        {!loading && subscriptions.map((subscription) => {
          const active = subscription.id === selectedId;
          return <article key={subscription.id} className={`rounded-2xl border bg-white p-4 transition ${active ? "border-teal-300 shadow-[0_12px_32px_rgba(19,89,78,0.09)]" : "border-slate-200 hover:border-slate-300"}`}>
            <button type="button" onClick={() => setSelectedId(subscription.id)} className="w-full text-left">
              <div className="flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate font-semibold text-ink">{subscription.name}</h3><p className="mt-1 flex items-center gap-1.5 text-xs text-slate-500"><CalendarClock size={13} />{frequencyLabel(subscription)}</p></div><StatusPill run={subscription.latest_run} /></div>
              <div className="mt-3 flex flex-wrap gap-1.5">{filterSummary(subscription).map((value) => <span key={value} className="max-w-full truncate rounded-full bg-slate-50 px-2.5 py-1 text-[11px] text-slate-500">{value}</span>)}</div>
              <p className="mt-3 text-xs text-slate-400">上次查新：{formatDateTime(subscription.last_run_at)}{subscription.latest_run ? ` · 新发现 ${subscription.latest_run.new_count} 个` : ""}</p>
            </button>
            <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-100 pt-3">
              <button type="button" disabled={runningId === subscription.id || changingId === subscription.id} onClick={() => void runNow(subscription)} className="inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-2 text-xs font-semibold text-white hover:bg-[#29435e] disabled:opacity-50">
                {runningId === subscription.id ? <LoaderCircle size={13} className="animate-spin" /> : <RefreshCw size={13} />}{runningId === subscription.id ? "查新中" : "立即查新"}
              </button>
              <button type="button" onClick={() => openSubscriptionEditor(subscription)} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:border-brand hover:text-brand"><Pencil size={13} />编辑计划</button>
              <button type="button" disabled={changingId === subscription.id} onClick={() => void toggleSubscription(subscription)} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-600 hover:border-slate-400 disabled:opacity-50">
                {subscription.enabled ? <Pause size={13} /> : <Play size={13} />}{subscription.enabled ? "暂停" : "恢复"}
              </button>
              <button type="button" disabled={changingId === subscription.id} aria-label={`删除${subscription.name}`} onClick={() => void deleteSubscription(subscription)} className="ml-auto rounded-lg border border-transparent px-2.5 py-2 text-slate-400 hover:border-rose-200 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-50"><Trash2 size={14} /></button>
            </div>
          </article>;
        })}
      </section>

      <section className="min-w-0 rounded-3xl border border-slate-200 bg-white p-5 shadow-[0_14px_40px_rgba(24,64,96,0.05)] sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4">
          <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-brand">查新结果</p><h2 className="mt-1 text-xl font-semibold text-ink">{selectedSubscription?.name ?? "选择一条查新条件"}</h2></div>
          {runDetail && <StatusPill run={runDetail} />}
        </div>
        {!selectedSubscription && <div className="grid min-h-64 place-items-center text-sm text-slate-400">创建或选择一条岗位查新，结果会显示在这里。</div>}
        {selectedSubscription && <>
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1.5"><Clock3 size={14} />{runDetail ? formatDateTime(runDetail.started_at) : "尚无运行记录"}</span>
            {runDetail && <span>{runDetail.total_count} 个匹配 · {runDetail.new_count} 个新发现</span>}
          </div>
          {runs.length > 0 && <div className="mt-4 flex flex-wrap gap-2" aria-label="最近查新记录">
            {runs.slice(0, 5).map((run) => <button key={run.id} type="button" onClick={() => void loadRunDetail(selectedSubscription.id, run.id)} className={`rounded-lg border px-2.5 py-1.5 text-xs transition ${runDetail?.id === run.id ? "border-ink bg-ink text-white" : "border-slate-200 text-slate-500 hover:border-brand hover:text-brand"}`}>
              {formatDateTime(run.started_at)} · +{run.new_count}
            </button>)}
          </div>}
          {runDetail?.provider_results?.length ? <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {runDetail.provider_results.map((provider) => <div key={provider.provider} className="rounded-xl bg-slate-50 px-3 py-2.5 text-xs">
              <div className="flex items-center justify-between gap-2"><span className="font-medium text-slate-700">{providerLabels[provider.provider] ?? provider.provider}</span><span className={provider.status === "success" ? "text-teal-700" : provider.status === "partial" ? "text-amber-700" : "text-rose-700"}>{provider.status === "success" ? "完成" : provider.status === "partial" ? "部分失败" : "失败"}</span></div>
              <p className="mt-1 text-slate-500">{provider.count} 个结果{provider.error ? ` · ${provider.error}` : ""}</p>
            </div>)}
          </div> : null}
          {runDetail?.error_message && <p className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">{runDetail.error_message}</p>}
          <div className="mt-5 space-y-3">
            {runDetail && runDetail.items.map((item) => <RunItemCard key={item.id} item={item} saving={savingItemId === item.id} onSave={() => void saveItem(item)} />)}
            {runDetail && runDetail.total_items === 0 && <div className="rounded-2xl border border-dashed border-slate-200 px-6 py-12 text-center">
              {runDetail.preview_expired ? <><Clock3 size={20} className="mx-auto text-slate-400" /><p className="mt-3 font-medium text-slate-700">岗位预览已过期</p><p className="mt-1 text-sm text-slate-500">预览保留 30 天；查新摘要和去重记录仍保留。重新查新可获取最新岗位。</p></> : runDetail.status === "no_new" ? <><ArrowDownRight size={20} className="mx-auto text-slate-400" /><p className="mt-3 font-medium text-slate-700">本次没有发现新岗位</p><p className="mt-1 text-sm text-slate-500">来源运行正常；已见过的岗位不会重复提示。</p></> : <><AlertCircle size={20} className="mx-auto text-amber-600" /><p className="mt-3 font-medium text-slate-700">暂无可展示的岗位结果</p><p className="mt-1 text-sm text-slate-500">请检查来源状态，或稍后再次查新。</p></>}
            </div>}
            {!runDetail && <div className="grid min-h-56 place-items-center rounded-2xl border border-dashed border-slate-200 px-6 text-center text-sm text-slate-400"><div><RefreshCw size={20} className="mx-auto mb-3" /><p>点击左侧“立即查新”读取当前来源。</p><p className="mt-1 text-xs">只会检查已选择的来源，不会自动保存结果。</p></div></div>}
          </div>
          {runDetail && runDetail.total_items > runDetail.limit && <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 text-xs text-slate-500">
            <span>第 {runDetail.page} / {totalPages} 页 · 预览保留 30 天</span>
            <div className="flex gap-2"><button type="button" disabled={page <= 1} onClick={() => void loadRunDetail(selectedSubscription.id, runDetail.id, page - 1)} className="rounded-lg border border-slate-200 px-3 py-2 disabled:opacity-40">上一页</button><button type="button" disabled={page >= totalPages} onClick={() => void loadRunDetail(selectedSubscription.id, runDetail.id, page + 1)} className="rounded-lg border border-slate-200 px-3 py-2 disabled:opacity-40">下一页</button></div>
          </div>}
        </>}
      </section>
    </div>

    {editingSubscription && <div className="fixed inset-0 z-50 grid place-items-center bg-ink/40 p-4" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !savingEdit) setEditingSubscription(null); }}>
      <form onSubmit={(event) => void saveSubscriptionSettings(event)} role="dialog" aria-modal="true" aria-labelledby="subscription-edit-title" className="max-h-[min(90vh,760px)] w-full max-w-xl space-y-5 overflow-y-auto rounded-3xl border border-slate-200 bg-white p-5 shadow-2xl sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">SUBSCRIPTION SETTINGS</p>
            <h2 id="subscription-edit-title" className="mt-1 text-xl font-semibold text-ink">编辑岗位查新</h2>
            <p className="mt-1 text-sm leading-5 text-slate-500">在这里直接调整查新频率和运行时间，无需跳转页面。</p>
          </div>
          <button type="button" aria-label="关闭" disabled={savingEdit} onClick={() => setEditingSubscription(null)} className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-ink disabled:opacity-40"><X size={18} /></button>
        </div>

        <label className="block text-sm font-medium text-slate-700">查新名称
          <input required maxLength={120} value={editName} onChange={(event) => setEditName(event.target.value)} className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-teal-600 focus:ring-4 focus:ring-teal-600/10" />
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-slate-700">查新频率
            <select value={editFrequency} onChange={(event) => setEditFrequency(event.target.value as SubscriptionFrequency)} className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-600">
              <option value="manual">仅手动</option><option value="daily">每天</option><option value="weekdays">每个工作日</option><option value="weekly">每周</option><option value="interval">间隔 N 天</option><option value="monthly">每月</option>
            </select>
          </label>
          {editFrequency !== "manual" && <label className="block text-sm font-medium text-slate-700">运行时间（北京时间）
            <input type="time" step={60} required value={editTime} onChange={(event) => setEditTime(event.target.value)} className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-teal-600" />
            <span className="mt-1 block text-xs font-normal text-slate-400">24 小时制，精确到分钟。</span>
          </label>}
          {editFrequency === "weekly" && <label className="block text-sm font-medium text-slate-700">每周几
            <select value={editWeekday} onChange={(event) => setEditWeekday(Number(event.target.value))} className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-600">
              {[[1, "周一"], [2, "周二"], [3, "周三"], [4, "周四"], [5, "周五"], [6, "周六"], [7, "周日"]].map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>}
          {editFrequency === "interval" && <label className="block text-sm font-medium text-slate-700">间隔天数
            <input type="number" min={2} max={30} step={1} value={editIntervalDays} onChange={(event) => setEditIntervalDays(Math.min(30, Math.max(2, Number(event.target.value) || 2)))} className="mt-2 h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none focus:border-teal-600" />
            <span className="mt-1 block text-xs font-normal text-slate-400">可设置每 2–30 天查新一次。</span>
          </label>}
          {editFrequency === "monthly" && <label className="block text-sm font-medium text-slate-700">每月几号
            <select value={editMonthDay} onChange={(event) => setEditMonthDay(Number(event.target.value))} className="mt-2 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm outline-none focus:border-teal-600">
              {Array.from({ length: 31 }, (_, index) => index + 1).map((day) => <option key={day} value={day}>{day} 日</option>)}
            </select>
            <span className="mt-1 block text-xs font-normal text-slate-400">短月没有该日期时，按当月最后一天执行。</span>
          </label>}
        </div>

        <div className="rounded-xl bg-[#f1fbf8] px-3.5 py-3">
          <p className="text-sm font-semibold text-teal-800">计划预览：{schedulePreview(editFrequency, editTime, editWeekday, editIntervalDays, editMonthDay)}</p>
          <p className="mt-1 text-xs leading-5 text-slate-500">按北京时间执行；只在本地后端运行时查新，不发送外部通知。</p>
        </div>

        <div className="rounded-xl border border-slate-200 px-3.5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium text-slate-700">当前搜索条件</p>
            <Link to={`/jobs/search?editSubscription=${editingSubscription.id}`} className="text-xs font-semibold text-brand hover:underline">修改岗位筛选</Link>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">{filterSummary(editingSubscription).map((value) => <span key={value} className="rounded-full bg-slate-50 px-2.5 py-1 text-[11px] text-slate-500">{value}</span>)}</div>
        </div>

        {editError && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{editError}</p>}
        <div className="flex justify-end gap-3 border-t border-slate-100 pt-4">
          <button type="button" disabled={savingEdit} onClick={() => setEditingSubscription(null)} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-600 disabled:opacity-50">取消</button>
          <button type="submit" disabled={savingEdit || !editName.trim()} className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{savingEdit && <LoaderCircle size={15} className="animate-spin" />}{savingEdit ? "保存中…" : "保存修改"}</button>
        </div>
      </form>
    </div>}

    <footer className="flex items-start gap-3 rounded-2xl border border-slate-200 bg-[#f8faf9] px-4 py-4 text-xs leading-5 text-slate-500">
      <CalendarClock size={16} className="mt-0.5 shrink-0 text-teal-700" />
      <p>定时计划按北京时间执行。电脑休眠、后端关闭期间不会查新；重新启动后会检查已到期任务，每条订阅最多补跑一次，不会重放所有错过的周期。未查到新岗位不代表岗位已关闭。</p>
      <ArrowUpRight size={14} className="hidden shrink-0 text-slate-400 sm:block" />
    </footer>
  </section>;
}
