import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  AlarmClock,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  BriefcaseBusiness,
  CalendarDays,
  CalendarPlus,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Circle,
  Clock3,
  FileUser,
  MapPin,
  Pencil,
  Phone,
  Plus,
  Search,
  Trash2,
  Video,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";

import {
  apiClient,
  type ApplicationListResponse,
  type ApplicationSummary,
  type InterviewFormat,
  type StatusDefinition,
  type WorkbenchInterview,
  type WorkbenchInterviewListResponse,
  type WorkbenchOverview,
  type WorkbenchTodo,
  type WorkbenchTodoListResponse,
} from "../api/client";

type TodoTab = "open" | "completed";
type CalendarView = "month" | "week";
type TodoFormState = {
  title: string;
  application_id: string;
  due_at: string;
  priority: "high" | "normal" | "low";
  note: string;
};
type InterviewFormState = {
  title: string;
  application_id: string;
  company_name: string;
  position_title: string;
  starts_at: string;
  ends_at: string;
  interview_format: InterviewFormat;
  location: string;
  meeting_url: string;
  note: string;
};

const blankTodo: TodoFormState = { title: "", application_id: "", due_at: "", priority: "normal", note: "" };
const blankInterview: InterviewFormState = {
  title: "", application_id: "", company_name: "", position_title: "", starts_at: "", ends_at: "",
  interview_format: "unknown", location: "", meeting_url: "", note: "",
};

function parseBackendDate(value: string) {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
}

function beijingParts(date: Date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
}

function beijingTodayKey() {
  const parts = beijingParts(new Date());
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function toBeijingInput(value?: string | null) {
  const date = value ? parseBackendDate(value) : new Date();
  const parts = beijingParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

function toApiDateTime(value: string) {
  return `${value}:00+08:00`;
}

function formatDateTime(value: string | null) {
  if (!value) return "未设置时间";
  const date = parseBackendDate(value);
  if (Number.isNaN(date.getTime())) return "时间无效";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(date);
}

function formatDayLabel(day: string, options: Intl.DateTimeFormatOptions = { month: "long", day: "numeric", weekday: "short" }) {
  return new Intl.DateTimeFormat("zh-CN", { ...options, timeZone: "UTC" }).format(new Date(`${day}T00:00:00Z`));
}

function monthLabel(month: string) {
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "UTC", year: "numeric", month: "long" })
    .format(new Date(`${month}-01T00:00:00Z`));
}

function getCalendarDays(month: string, view: CalendarView, selectedDay: string) {
  const anchor = view === "week" ? new Date(`${selectedDay}T00:00:00Z`) : new Date(`${month}-01T00:00:00Z`);
  const mondayOffset = (anchor.getUTCDay() + 6) % 7;
  const length = view === "week" ? 7 : 42;
  const monthNumber = Number(month.slice(5, 7)) - 1;
  return Array.from({ length }, (_, index) => {
    const date = new Date(anchor);
    date.setUTCDate(anchor.getUTCDate() - mondayOffset + index);
    return { key: date.toISOString().slice(0, 10), inMonth: date.getUTCMonth() === monthNumber };
  });
}

function shiftMonth(month: string, amount: number) {
  const [year, monthNumber] = month.split("-").map(Number);
  const date = new Date(Date.UTC(year, monthNumber - 1 + amount, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

function getMonthRange(month: string) {
  const [year, monthNumber] = month.split("-").map(Number);
  const next = new Date(Date.UTC(year, monthNumber, 1));
  const endMonth = `${next.getUTCFullYear()}-${String(next.getUTCMonth() + 1).padStart(2, "0")}-01`;
  return {
    start_at: `${month}-01T00:00:00+08:00`,
    end_at: `${endMonth}T00:00:00+08:00`,
  };
}

function getCalendarRange(month: string, view: CalendarView, selectedDay: string) {
  if (view === "month") return getMonthRange(month);
  const days = getCalendarDays(month, view, selectedDay);
  const nextWeek = new Date(`${days[6].key}T00:00:00Z`);
  nextWeek.setUTCDate(nextWeek.getUTCDate() + 1);
  return {
    start_at: `${days[0].key}T00:00:00+08:00`,
    end_at: `${nextWeek.toISOString().slice(0, 10)}T00:00:00+08:00`,
  };
}

function weekLabel(days: { key: string }[]) {
  const start = days[0]?.key;
  const end = days[days.length - 1]?.key;
  if (!start || !end) return "本周";
  const format = (value: string, includeYear = false) => new Intl.DateTimeFormat("zh-CN", {
    timeZone: "UTC", month: "numeric", day: "numeric", ...(includeYear ? { year: "numeric" } : {}),
  }).format(new Date(`${value}T00:00:00Z`));
  return `${format(start, true)} – ${format(end)}`;
}

function interviewDay(value: string) {
  const parts = beijingParts(parseBackendDate(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

const statusColorClasses: Record<string, string> = {
  blue: "bg-blue-50 text-blue-700 border-blue-100",
  amber: "bg-amber-50 text-amber-800 border-amber-100",
  orange: "bg-orange-50 text-orange-800 border-orange-100",
  indigo: "bg-indigo-50 text-indigo-700 border-indigo-100",
  violet: "bg-violet-50 text-violet-700 border-violet-100",
  purple: "bg-purple-50 text-purple-700 border-purple-100",
  green: "bg-emerald-50 text-emerald-700 border-emerald-100",
  teal: "bg-teal-50 text-teal-700 border-teal-100",
  rose: "bg-rose-50 text-rose-700 border-rose-100",
  slate: "bg-slate-100 text-slate-700 border-slate-200",
};

function statusClass(color: string | null) {
  return statusColorClasses[color ?? "slate"] ?? statusColorClasses.slate;
}

function priorityLabel(priority: WorkbenchTodo["priority"]) {
  return priority === "high" ? "优先" : priority === "low" ? "低优先" : "普通";
}

function formatLabel(format: InterviewFormat) {
  return format === "online" ? "线上" : format === "in_person" ? "线下" : format === "phone" ? "电话" : "未设置形式";
}

export function WorkbenchPage() {
  const today = beijingTodayKey();
  const [overview, setOverview] = useState<WorkbenchOverview | null>(null);
  const [applications, setApplications] = useState<ApplicationSummary[]>([]);
  const [statuses, setStatuses] = useState<StatusDefinition[]>([]);
  const [todos, setTodos] = useState<WorkbenchTodo[]>([]);
  const [todoTotal, setTodoTotal] = useState(0);
  const [todoTab, setTodoTab] = useState<TodoTab>("open");
  const [todoPage, setTodoPage] = useState(1);
  const [interviews, setInterviews] = useState<WorkbenchInterview[]>([]);
  const [month, setMonth] = useState(today.slice(0, 7));
  const [selectedDay, setSelectedDay] = useState(today);
  const [calendarView, setCalendarView] = useState<CalendarView>("month");
  const [applicationSearch, setApplicationSearch] = useState("");
  const [applicationCity, setApplicationCity] = useState("all");
  const [applicationTimeRange, setApplicationTimeRange] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [todoModalOpen, setTodoModalOpen] = useState(false);
  const [interviewModalOpen, setInterviewModalOpen] = useState(false);
  const [editingTodo, setEditingTodo] = useState<WorkbenchTodo | null>(null);
  const [editingInterview, setEditingInterview] = useState<WorkbenchInterview | null>(null);
  const [todoForm, setTodoForm] = useState<TodoFormState>(blankTodo);
  const [interviewForm, setInterviewForm] = useState<InterviewFormState>(blankInterview);
  const [formError, setFormError] = useState<string | null>(null);
  const hasLoaded = useRef(false);

  const loadDashboard = useCallback(async () => {
    if (!hasLoaded.current) setLoading(true);
    setError(null);
    const range = getCalendarRange(month, calendarView, selectedDay);
    try {
      const [overviewResponse, statusesResponse, applicationsResponse, todosResponse, interviewsResponse] = await Promise.all([
        apiClient.get<WorkbenchOverview>("/workbench/overview"),
        apiClient.get<StatusDefinition[]>("/applications/status-definitions"),
        apiClient.get<ApplicationListResponse>("/applications", { params: { tab: "all", page: 1, limit: 100 } }),
        apiClient.get<WorkbenchTodoListResponse>("/workbench/todos", {
          params: { status: todoTab, page: todoPage, limit: 100 },
        }),
        apiClient.get<WorkbenchInterviewListResponse>("/workbench/interviews", { params: range }),
      ]);

      let allApplications = applicationsResponse.data.items;
      const pages = Math.ceil(applicationsResponse.data.total / applicationsResponse.data.limit);
      if (pages > 1) {
        const remaining = await Promise.all(
          Array.from({ length: pages - 1 }, (_, index) => apiClient.get<ApplicationListResponse>("/applications", {
            params: { tab: "all", page: index + 2, limit: 100 },
          })),
        );
        allApplications = [...allApplications, ...remaining.flatMap((response) => response.data.items)];
      }

      setOverview(overviewResponse.data);
      setStatuses(statusesResponse.data);
      setApplications(allApplications);
      setTodos(todosResponse.data.items);
      setTodoTotal(todosResponse.data.total);
      setInterviews(interviewsResponse.data.items);
    } catch {
      setError("工作台数据加载失败，请确认后端服务正在运行，然后重试。");
    } finally {
      hasLoaded.current = true;
      setLoading(false);
    }
  }, [calendarView, month, selectedDay, todoPage, todoTab]);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);

  useEffect(() => {
    if (selectedDay.slice(0, 7) !== month) setSelectedDay(`${month}-01`);
  }, [month, selectedDay]);

  const visibleApplications = useMemo(() => {
    const query = applicationSearch.trim().toLocaleLowerCase();
    const days = applicationTimeRange === "all" ? null : Number(applicationTimeRange);
    const cutoff = days === null ? null : Date.now() - days * 24 * 60 * 60 * 1000;
    return applications.filter((item) => {
      const matchesQuery = !query || `${item.job.title} ${item.job.company_name} ${item.job.city}`.toLocaleLowerCase().includes(query);
      const matchesCity = applicationCity === "all" || item.job.city === applicationCity;
      const matchesDate = cutoff === null || parseBackendDate(item.saved_at).getTime() >= cutoff;
      return matchesQuery && matchesCity && matchesDate;
    });
  }, [applications, applicationCity, applicationSearch, applicationTimeRange]);

  const boardStatuses = useMemo(() => {
    const observed = new Set(applications.map((application) => application.current_status.id));
    return overview?.status_counts.filter((item) => item.enabled || observed.has(item.id)) ?? [];
  }, [applications, overview]);

  const calendarDays = useMemo(() => getCalendarDays(month, calendarView, selectedDay), [calendarView, month, selectedDay]);
  const eventsByDay = useMemo(() => {
    const events = new Map<string, WorkbenchInterview[]>();
    for (const interview of interviews) {
      const key = interviewDay(interview.starts_at);
      events.set(key, [...(events.get(key) ?? []), interview]);
    }
    return events;
  }, [interviews]);
  const selectedDayInterviews = eventsByDay.get(selectedDay) ?? [];
  const todoPageCount = Math.max(1, Math.ceil(todoTotal / 100));
  const applicationById = useMemo(() => new Map(applications.map((item) => [item.id, item])), [applications]);
  const applicationCities = useMemo(() => [...new Set(applications.map((item) => item.job.city).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN")), [applications]);
  const hasBoardFilter = Boolean(applicationSearch.trim()) || applicationCity !== "all" || applicationTimeRange !== "all";

  function navigateCalendar(amount: number) {
    if (calendarView === "month") {
      const nextMonth = shiftMonth(month, amount);
      setMonth(nextMonth);
      setSelectedDay(`${nextMonth}-01`);
      return;
    }
    const nextDay = new Date(`${selectedDay}T12:00:00Z`);
    nextDay.setUTCDate(nextDay.getUTCDate() + amount * 7);
    const nextKey = nextDay.toISOString().slice(0, 10);
    setSelectedDay(nextKey);
    setMonth(nextKey.slice(0, 7));
  }

  async function changeApplicationStatus(application: ApplicationSummary, statusId: number) {
    setSaving(true);
    setActionError(null);
    try {
      await apiClient.post(`/applications/${application.id}/status`, {
        to_status_id: statusId,
        effective_at: new Date().toISOString(),
        note: null,
      });
      await loadDashboard();
    } catch {
      setActionError("岗位状态更新失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  function openTodo(todo?: WorkbenchTodo, defaults: Partial<TodoFormState> = {}) {
    setEditingTodo(todo ?? null);
    setTodoForm(todo ? {
      title: todo.title,
      application_id: todo.application ? String(todo.application.id) : "",
      due_at: todo.due_at ? toBeijingInput(todo.due_at) : "",
      priority: todo.priority,
      note: todo.note ?? "",
    } : { ...blankTodo, ...defaults });
    setFormError(null);
    setTodoModalOpen(true);
  }

  function openInterview(interview?: WorkbenchInterview) {
    setEditingInterview(interview ?? null);
    setInterviewForm(interview ? {
      title: interview.title,
      application_id: interview.application ? String(interview.application.id) : "",
      company_name: interview.company_name ?? "",
      position_title: interview.position_title ?? "",
      starts_at: toBeijingInput(interview.starts_at),
      ends_at: interview.ends_at ? toBeijingInput(interview.ends_at) : "",
      interview_format: interview.interview_format,
      location: interview.location ?? "",
      meeting_url: interview.meeting_url ?? "",
      note: interview.note ?? "",
    } : {
      ...blankInterview,
      starts_at: `${selectedDay}T10:00`,
    });
    setFormError(null);
    setInterviewModalOpen(true);
  }

  async function saveTodo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!todoForm.title.trim()) {
      setFormError("请填写待办内容。");
      return;
    }
    setSaving(true);
    setFormError(null);
    const payload = {
      title: todoForm.title.trim(),
      application_id: todoForm.application_id ? Number(todoForm.application_id) : null,
      due_at: todoForm.due_at ? toApiDateTime(todoForm.due_at) : null,
      priority: todoForm.priority,
      note: todoForm.note.trim() || null,
    };
    try {
      if (editingTodo) await apiClient.patch(`/workbench/todos/${editingTodo.id}`, payload);
      else await apiClient.post("/workbench/todos", payload);
      setTodoModalOpen(false);
      setEditingTodo(null);
      await loadDashboard();
    } catch {
      setFormError("待办保存失败，请检查关联岗位或稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function toggleTodo(todo: WorkbenchTodo) {
    setSaving(true);
    setActionError(null);
    try {
      await apiClient.patch(`/workbench/todos/${todo.id}`, { completed: !todo.completed });
      await loadDashboard();
    } catch {
      setActionError("待办状态更新失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function deleteTodo(todo: WorkbenchTodo) {
    if (!window.confirm(`确定删除待办“${todo.title}”吗？`)) return;
    setSaving(true);
    setActionError(null);
    try {
      await apiClient.delete(`/workbench/todos/${todo.id}`);
      await loadDashboard();
    } catch {
      setActionError("待办删除失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function saveInterview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!interviewForm.title.trim() || !interviewForm.starts_at) {
      setFormError("请填写面试主题和开始时间。");
      return;
    }
    if (interviewForm.ends_at && interviewForm.ends_at <= interviewForm.starts_at) {
      setFormError("结束时间必须晚于开始时间。");
      return;
    }
    setSaving(true);
    setFormError(null);
    const payload = {
      title: interviewForm.title.trim(),
      application_id: interviewForm.application_id ? Number(interviewForm.application_id) : null,
      company_name: interviewForm.company_name.trim() || null,
      position_title: interviewForm.position_title.trim() || null,
      starts_at: toApiDateTime(interviewForm.starts_at),
      ends_at: interviewForm.ends_at ? toApiDateTime(interviewForm.ends_at) : null,
      timezone: "Asia/Shanghai",
      interview_format: interviewForm.interview_format,
      location: interviewForm.location.trim() || null,
      meeting_url: interviewForm.meeting_url.trim() || null,
      note: interviewForm.note.trim() || null,
    };
    try {
      if (editingInterview) await apiClient.patch(`/workbench/interviews/${editingInterview.id}`, payload);
      else await apiClient.post("/workbench/interviews", payload);
      setInterviewModalOpen(false);
      setEditingInterview(null);
      const interviewMonth = interviewForm.starts_at.slice(0, 7);
      setSelectedDay(interviewForm.starts_at.slice(0, 10));
      if (interviewMonth !== month) setMonth(interviewMonth);
      else await loadDashboard();
    } catch {
      setFormError("面试安排保存失败，请检查时间和关联岗位后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function deleteInterview(interview: WorkbenchInterview) {
    if (!window.confirm(`确定删除“${interview.title}”这条面试安排吗？`)) return;
    setSaving(true);
    setActionError(null);
    try {
      await apiClient.delete(`/workbench/interviews/${interview.id}`);
      await loadDashboard();
    } catch {
      setActionError("面试安排删除失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  const metricCards = [
    { label: "跟踪岗位", value: overview?.application_count, helper: "用户已保存", icon: BriefcaseBusiness, accent: "text-[#16645d] bg-[#e8f4ef]", to: "/jobs/manage" },
    { label: "待处理任务", value: overview?.todo_open_count, helper: overview?.todo_overdue_count ? `${overview.todo_overdue_count} 项已逾期` : "没有逾期任务", icon: CheckCircle2, accent: "text-[#a45728] bg-[#fbefe4]", to: "#todos" },
    { label: "未来 7 天面试", value: overview?.interview_next_7_days_count, helper: `共 ${overview?.interview_upcoming_count ?? 0} 场未来安排`, icon: CalendarDays, accent: "text-[#355e9a] bg-[#eaf0fa]", to: "#calendar" },
    { label: "已完成待办", value: overview?.todo_completed_count, helper: "来自你的完成记录", icon: BarChart3, accent: "text-[#5d6580] bg-[#eef0f4]", to: "#todos" },
  ];

  if (loading && !overview) {
    return <div className="mx-auto max-w-[1500px] animate-pulse space-y-6">
      <div className="h-20 rounded-2xl bg-white" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((item) => <div key={item} className="h-28 rounded-2xl bg-white" />)}</div>
      <div className="h-80 rounded-2xl bg-white" />
    </div>;
  }

  return <section className="mx-auto max-w-[1500px] space-y-7 pb-10">
    <header className="flex flex-wrap items-end justify-between gap-5">
      <div>
        <p className="text-[11px] font-bold uppercase tracking-[0.24em] text-[#527d72]">JOB SEARCH / DESK</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.035em] text-[#182b3b] sm:text-4xl">求职工作台</h1>
        <p className="mt-2 text-sm text-slate-500">把岗位进度、待办和面试安排放在一处管理。</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button onClick={() => openTodo()} className="inline-flex items-center gap-2 rounded-xl border border-[#d8e2df] bg-white px-4 py-2.5 text-sm font-semibold text-[#315d55] shadow-sm transition hover:border-[#9cb9b1] hover:bg-[#f8fbf9]"><Plus size={16} />新增待办</button>
        <button onClick={() => openInterview()} className="inline-flex items-center gap-2 rounded-xl bg-[#193c3a] px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#245653]"><CalendarPlus size={16} />安排面试</button>
      </div>
    </header>

    {error && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-800"><span>{error}</span><button onClick={() => void loadDashboard()} className="font-semibold underline underline-offset-4">重试</button></div>}
    {actionError && <div role="alert" className="flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"><span>{actionError}</span><button onClick={() => setActionError(null)} aria-label="关闭提示"><X size={16} /></button></div>}

    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {metricCards.map(({ label, value, helper, icon: Icon, accent, to }, index) => <a key={label} href={to} className="group relative overflow-hidden rounded-2xl border border-[#e3e9e7] bg-white p-5 shadow-[0_8px_24px_rgba(23,45,56,0.035)] transition hover:-translate-y-0.5 hover:border-[#bfd1cb] hover:shadow-[0_12px_30px_rgba(23,45,56,0.08)]">
        <div className="absolute right-0 top-0 h-24 w-24 rounded-bl-[3rem] bg-[#f6f8f7] transition group-hover:bg-[#f0f5f2]" />
        <div className="relative flex items-start justify-between"><span className={`grid h-10 w-10 place-items-center rounded-xl ${accent}`}><Icon size={19} strokeWidth={1.8} /></span><span className="rounded-full bg-[#f6f8f7] px-2 py-1 text-[10px] font-semibold tracking-wide text-[#7b8a86]">{String(index + 1).padStart(2, "0")}</span></div>
        <p className="relative mt-4 text-sm font-medium text-slate-500">{label}</p><p className="relative mt-1 text-3xl font-semibold tabular-nums tracking-tight text-[#1c3442]">{value ?? 0}</p><p className="relative mt-2 text-xs text-slate-400">{helper}</p>
      </a>)}
    </div>

    <section className="overflow-hidden rounded-3xl border border-[#dfe7e4] bg-white shadow-[0_12px_36px_rgba(23,45,56,0.045)]">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#edf1ef] px-5 py-5 sm:px-7">
        <div><div className="flex items-center gap-3"><h2 className="text-xl font-semibold text-[#1c3442]">投递进度</h2><span className="rounded-full bg-[#f1f5f3] px-2.5 py-1 text-xs font-semibold text-[#526b64]">{overview?.application_count ?? 0} 个岗位</span></div><p className="mt-1.5 text-sm text-slate-500">状态和顺序来自你的状态设置；在岗位卡片上可直接调整。</p></div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="relative"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><input value={applicationSearch} onChange={(event) => setApplicationSearch(event.target.value)} placeholder="搜索岗位方向或公司" aria-label="搜索岗位方向或公司" className="w-52 rounded-xl border border-[#e1e8e5] bg-[#fbfcfb] py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-[#8eaaa0] focus:ring-2 focus:ring-[#dce9e4]" /></label>
          <select value={applicationCity} onChange={(event) => setApplicationCity(event.target.value)} aria-label="按城市筛选岗位" className="rounded-xl border border-[#e1e8e5] bg-white px-3 py-2.5 text-sm text-[#52645f] outline-none focus:border-[#8eaaa0]"><option value="all">全部城市</option>{applicationCities.map((city) => <option key={city} value={city}>{city}</option>)}</select>
          <select value={applicationTimeRange} onChange={(event) => setApplicationTimeRange(event.target.value)} aria-label="按收藏时间筛选岗位" className="rounded-xl border border-[#e1e8e5] bg-white px-3 py-2.5 text-sm text-[#52645f] outline-none focus:border-[#8eaaa0]"><option value="all">全部时间</option><option value="7">最近 7 天收藏</option><option value="30">最近 30 天收藏</option><option value="90">最近 90 天收藏</option></select>
          <Link to="/jobs/manage" className="inline-flex items-center gap-1 rounded-xl px-3 py-2.5 text-sm font-semibold text-[#3b6e64] hover:bg-[#f4f8f6]">岗位管理<ArrowUpRight size={15} /></Link>
        </div>
      </div>
      {boardStatuses.length ? <div className="flex gap-3 overflow-x-auto px-5 py-5 [scrollbar-color:#cbd6d2_transparent] sm:px-7">
        {boardStatuses.map((status) => {
          const cards = visibleApplications.filter((application) => application.current_status.id === status.id);
          return <div key={status.id} className="w-[min(82vw,300px)] shrink-0 rounded-2xl bg-[#f7f9f8] p-3.5 sm:w-[286px]">
            <div className="mb-3 flex items-center justify-between gap-2 px-1">
              <div className="flex min-w-0 items-center gap-2"><span className={`max-w-48 truncate rounded-full border px-2.5 py-1 text-xs font-semibold ${statusClass(status.color)}`}>{status.name}</span>{!status.enabled && <span className="text-[10px] text-slate-400">已停用</span>}</div>
              <span className="grid h-6 min-w-6 place-items-center rounded-full bg-white px-1.5 text-xs font-semibold tabular-nums text-slate-500">{cards.length}</span>
            </div>
            <div className="space-y-2.5">
              {cards.map((application) => <article key={application.id} className="rounded-xl border border-[#e5ebe8] bg-white p-3.5 shadow-[0_2px_7px_rgba(24,43,59,0.025)]">
                <Link to={`/jobs/manage?application=${application.id}`} className="group block"><h3 className="line-clamp-2 text-sm font-semibold leading-5 text-[#213746] group-hover:text-[#2b7065]">{application.job.title}</h3><p className="mt-1.5 truncate text-xs text-slate-500">{application.job.company_name}</p></Link>
                <div className="mt-3 flex items-center justify-between gap-2 text-[11px] text-slate-400"><span className="inline-flex min-w-0 items-center gap-1 truncate"><MapPin size={12} />{application.job.city}</span><span className="shrink-0">更新 {formatDateTime(application.last_status_changed_at)}</span></div>
                <label className="mt-3 flex items-center gap-2 border-t border-[#f0f3f1] pt-2.5 text-[11px] font-medium text-slate-500"><span className="shrink-0">移至</span><select disabled={saving} value={application.current_status.id} onChange={(event) => void changeApplicationStatus(application, Number(event.target.value))} className="min-w-0 flex-1 cursor-pointer truncate border-0 bg-transparent py-0.5 text-xs font-semibold text-[#445b55] outline-none disabled:opacity-50">
                  {!statuses.some((item) => item.id === application.current_status.id) && <option value={application.current_status.id}>{application.current_status.name}（已停用）</option>}
                  {statuses.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                </select></label>
              </article>)}
              {!cards.length && <div className="grid min-h-28 place-items-center rounded-xl border border-dashed border-[#dce4e1] bg-white/70 px-3 text-center text-xs text-slate-400">{hasBoardFilter ? "没有符合筛选条件的岗位" : "还没有岗位"}</div>}
            </div>
          </div>;
        })}
      </div> : <EmptyState title="状态看板暂不可用" detail="请先在岗位管理中创建或启用投递状态。" action={<Link to="/jobs/manage" className="font-semibold text-[#2f7165]">前往岗位管理<ArrowRight size={14} className="ml-1 inline" /></Link>} />}
      {!applications.length && !loading && <div className="mx-5 mb-5 rounded-xl border border-dashed border-[#dce4e1] bg-[#fbfcfb] px-5 py-4 text-sm text-slate-500 sm:mx-7"><span className="font-semibold text-[#28423b]">暂无跟踪岗位。</span>从岗位搜索中保存岗位后，会在这里按你的状态展示。 <Link className="ml-1 font-semibold text-[#2f7165] hover:underline" to="/jobs/search">搜索岗位</Link></div>}
    </section>

    <div className="grid items-start gap-5 xl:grid-cols-[minmax(19rem,.84fr)_minmax(0,1.16fr)]">
      <section id="todos" className="scroll-mt-8 rounded-3xl border border-[#dfe7e4] bg-white p-5 shadow-[0_12px_36px_rgba(23,45,56,0.04)] sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><div className="flex items-center gap-2"><h2 className="text-xl font-semibold text-[#1c3442]">求职待办</h2><span className="rounded-full bg-[#fbefe4] px-2 py-0.5 text-xs font-semibold text-[#9a572e]">{overview?.todo_overdue_count ?? 0} 逾期</span></div><p className="mt-1.5 text-sm text-slate-500">记录你自己安排的下一步行动。</p></div>
          <button onClick={() => openTodo()} aria-label="新增待办" className="grid h-9 w-9 place-items-center rounded-xl border border-[#dce6e2] text-[#32675d] transition hover:bg-[#f3f8f5]"><Plus size={17} /></button>
        </div>
        <div className="mt-5 flex items-center gap-1 border-b border-[#edf1ef]">
          {(["open", "completed"] as const).map((tab) => <button key={tab} onClick={() => { setTodoTab(tab); setTodoPage(1); }} className={`relative px-3 pb-2.5 text-sm font-semibold transition ${todoTab === tab ? "text-[#235e53]" : "text-slate-400 hover:text-slate-600"}`}>
            {tab === "open" ? "待处理" : "已完成"}{todoTab === tab && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-[#3f8b79]" />}
          </button>)}
          <span className="ml-auto pb-2.5 text-xs tabular-nums text-slate-400">{todoTotal} 项</span>
        </div>
        <div className="mt-2 divide-y divide-[#f0f3f1]">
          {todos.map((todo) => {
            const overdue = !todo.completed && todo.due_at && parseBackendDate(todo.due_at).getTime() < Date.now();
            return <div key={todo.id} className="group flex gap-3 py-3.5">
              <button onClick={() => void toggleTodo(todo)} aria-label={todo.completed ? "标记为待处理" : "完成待办"} disabled={saving} className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border transition ${todo.completed ? "border-[#4a8a78] bg-[#4a8a78] text-white" : "border-[#c4d0cb] text-transparent hover:border-[#4a8a78] hover:text-[#4a8a78]"}`}>
                {todo.completed ? <Check size={12} strokeWidth={3} /> : <Check size={12} strokeWidth={3} />}
              </button>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2"><p className={`min-w-0 flex-1 text-sm font-semibold ${todo.completed ? "text-slate-400 line-through" : "text-[#293d49]"}`}>{todo.title}</p><span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${todo.priority === "high" ? "bg-rose-50 text-rose-700" : todo.priority === "low" ? "bg-slate-100 text-slate-500" : "bg-[#f1f4f2] text-slate-500"}`}>{priorityLabel(todo.priority)}</span></div>
                {todo.application && <Link to={`/jobs/manage?application=${todo.application.id}`} className="mt-1 block truncate text-xs text-[#54736a] hover:underline">{todo.application.company_name} · {todo.application.title}</Link>}
                <div className={`mt-1.5 flex items-center gap-1 text-xs ${overdue ? "font-medium text-rose-600" : "text-slate-400"}`}><Clock3 size={12} />{todo.completed ? `完成于 ${formatDateTime(todo.completed_at)}` : todo.due_at ? `${overdue ? "已逾期 · " : "截止 "}${formatDateTime(todo.due_at)}` : "未设置截止时间"}</div>
                {todo.note && <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{todo.note}</p>}
              </div>
              <div className="flex shrink-0 items-start opacity-100 transition sm:opacity-0 sm:group-hover:opacity-100"><button onClick={() => openTodo(todo)} aria-label="编辑待办" className="rounded-lg p-1.5 text-slate-400 hover:bg-[#f1f5f3] hover:text-[#315f55]"><Pencil size={14} /></button><button onClick={() => void deleteTodo(todo)} aria-label="删除待办" className="rounded-lg p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"><Trash2 size={14} /></button></div>
            </div>;
          })}
          {!todos.length && <div className="py-10 text-center"><span className="mx-auto grid h-10 w-10 place-items-center rounded-xl bg-[#f3f6f4] text-[#719087]"><CheckCircle2 size={19} /></span><p className="mt-3 text-sm font-semibold text-[#344943]">{todoTab === "open" ? "暂时没有待办" : "还没有完成记录"}</p><p className="mt-1 text-xs text-slate-400">{todoTab === "open" ? "把准备简历、复习面试等行动记在这里。" : "完成的求职行动会留在这里，方便回顾。"}</p>{todoTab === "open" && <button onClick={() => openTodo()} className="mt-3 text-xs font-semibold text-[#317264] hover:underline">创建第一条待办</button>}</div>}
        </div>
        {todoPageCount > 1 && <div className="mt-3 flex items-center justify-between border-t border-[#edf1ef] pt-3 text-xs text-slate-500"><span>第 {todoPage} / {todoPageCount} 页</span><div className="flex gap-1"><button disabled={todoPage <= 1} onClick={() => setTodoPage((page) => page - 1)} className="rounded-lg px-2.5 py-1.5 hover:bg-[#f1f5f3] disabled:opacity-40">上一页</button><button disabled={todoPage >= todoPageCount} onClick={() => setTodoPage((page) => page + 1)} className="rounded-lg px-2.5 py-1.5 hover:bg-[#f1f5f3] disabled:opacity-40">下一页</button></div></div>}
      </section>

      <section id="calendar" className="scroll-mt-8 rounded-3xl border border-[#dfe7e4] bg-white p-5 shadow-[0_12px_36px_rgba(23,45,56,0.04)] sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><div className="flex items-center gap-2"><h2 className="text-xl font-semibold text-[#1c3442]">面试日历</h2><span className="rounded-full bg-[#eaf0fa] px-2 py-0.5 text-xs font-semibold text-[#426390]">当前{calendarView === "month" ? "月份" : "周"} {interviews.length} 场</span></div><p className="mt-1.5 text-sm text-slate-500">仅展示你手动记录的面试，时间按北京时间。</p></div>
          <button onClick={() => openInterview()} className="inline-flex items-center gap-1.5 rounded-xl border border-[#dce6e2] px-3 py-2 text-xs font-semibold text-[#32675d] transition hover:bg-[#f3f8f5]"><Plus size={14} />新增面试</button>
        </div>
        <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(18rem,.95fr)_minmax(15rem,1.05fr)]">
          <div>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><div><p className="text-lg font-semibold text-[#2b3f4b]">{calendarView === "month" ? monthLabel(month) : weekLabel(calendarDays)}</p><p className="mt-0.5 text-xs text-slate-400">周一 · 周日</p></div><div className="flex items-center gap-1"><div className="mr-1 flex rounded-lg bg-[#f2f5f3] p-0.5"><button onClick={() => setCalendarView("month")} className={`rounded-md px-2 py-1.5 text-[11px] font-semibold ${calendarView === "month" ? "bg-white text-[#315d55] shadow-sm" : "text-slate-500"}`}>月</button><button onClick={() => setCalendarView("week")} className={`rounded-md px-2 py-1.5 text-[11px] font-semibold ${calendarView === "week" ? "bg-white text-[#315d55] shadow-sm" : "text-slate-500"}`}>周</button></div><button onClick={() => navigateCalendar(-1)} aria-label={calendarView === "month" ? "上个月" : "上一周"} className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-[#f2f5f3]"><ChevronLeft size={17} /></button><button onClick={() => { setMonth(today.slice(0, 7)); setSelectedDay(today); }} className="rounded-lg px-2.5 py-1.5 text-xs font-semibold text-[#47766c] hover:bg-[#f2f6f4]">今天</button><button onClick={() => navigateCalendar(1)} aria-label={calendarView === "month" ? "下个月" : "下一周"} className="grid h-8 w-8 place-items-center rounded-lg text-slate-500 hover:bg-[#f2f5f3]"><ChevronRight size={17} /></button></div></div>
            <div className="grid grid-cols-7 text-center text-[10px] font-semibold text-slate-400">{["一", "二", "三", "四", "五", "六", "日"].map((day) => <span key={day} className="py-2">{day}</span>)}</div>
            <div className="grid grid-cols-7 gap-y-1">
              {calendarDays.map(({ key, inMonth }) => {
                const count = eventsByDay.get(key)?.length ?? 0;
                const selected = key === selectedDay;
                return <button key={key} onClick={() => { setSelectedDay(key); if (key.slice(0, 7) !== month) setMonth(key.slice(0, 7)); }} aria-label={`${formatDayLabel(key)}${count ? `，${count}场面试` : ""}`} className={`relative mx-auto grid h-9 w-9 place-items-center rounded-xl text-xs transition ${selected ? "bg-[#1f4943] font-semibold text-white shadow-sm" : inMonth ? "text-[#394e58] hover:bg-[#edf4f0]" : "text-slate-300 hover:bg-slate-50"}`}>
                  {Number(key.slice(-2))}<span className={`absolute bottom-1 h-1 w-1 rounded-full ${count ? (selected ? "bg-[#bfe9d9]" : "bg-[#5b9c86]") : "bg-transparent"}`} />
                </button>;
              })}
            </div>
          </div>
          <div className="rounded-2xl bg-[#f7f9f8] p-4 sm:p-5">
            <div className="flex items-start justify-between gap-2"><div><p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#688078]">SELECTED DAY</p><h3 className="mt-1 text-lg font-semibold text-[#273d47]">{formatDayLabel(selectedDay)}</h3></div><button onClick={() => openInterview()} aria-label="为所选日期新增面试" className="grid h-8 w-8 place-items-center rounded-lg bg-white text-[#46766a] shadow-sm hover:bg-[#edf4f0]"><Plus size={16} /></button></div>
            <div className="mt-4 space-y-2.5">
              {selectedDayInterviews.map((interview) => <article key={interview.id} className="group rounded-xl border border-[#e3eae7] bg-white p-3.5">
                <div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="text-xs font-semibold tabular-nums text-[#518071]">{formatDateTime(interview.starts_at)}{interview.ends_at ? ` – ${formatDateTime(interview.ends_at).slice(-5)}` : ""}</p><h4 className="mt-1 truncate text-sm font-semibold text-[#263b46]">{interview.title}</h4></div><div className="flex shrink-0 opacity-100 sm:opacity-0 sm:group-hover:opacity-100"><button onClick={() => openTodo(undefined, { title: `准备${interview.title}`, application_id: interview.application ? String(interview.application.id) : "" })} aria-label="创建面试准备待办" title="创建准备待办" className="rounded-md p-1.5 text-slate-400 hover:bg-[#f1f5f3] hover:text-[#315f55]"><CheckCircle2 size={13} /></button><button onClick={() => openInterview(interview)} aria-label="编辑面试" className="rounded-md p-1.5 text-slate-400 hover:bg-[#f1f5f3] hover:text-[#315f55]"><Pencil size={13} /></button><button onClick={() => void deleteInterview(interview)} aria-label="删除面试" className="rounded-md p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600"><Trash2 size={13} /></button></div></div>
                {(interview.company_name || interview.position_title) && <p className="mt-1 truncate text-xs text-slate-500">{[interview.company_name, interview.position_title].filter(Boolean).join(" · ")}</p>}
                <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-400"><span className="inline-flex items-center gap-1">{interview.interview_format === "online" ? <Video size={12} /> : interview.interview_format === "phone" ? <Phone size={12} /> : interview.interview_format === "in_person" ? <MapPin size={12} /> : <CalendarDays size={12} />}{formatLabel(interview.interview_format)}</span>{interview.application && <Link to={`/jobs/manage?application=${interview.application.id}`} className="truncate text-[#47766c] hover:underline">查看关联岗位</Link>}</div>
                {interview.meeting_url && <a href={interview.meeting_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-[#3e7669] hover:underline">打开会议链接<ArrowUpRight size={12} /></a>}
                {interview.note && <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-400">{interview.note}</p>}
              </article>)}
              {!selectedDayInterviews.length && <div className="grid min-h-32 place-items-center rounded-xl border border-dashed border-[#d9e2de] px-4 text-center"><div><p className="text-sm font-medium text-[#49615a]">这一天没有面试安排</p><button onClick={() => openInterview()} className="mt-2 text-xs font-semibold text-[#317264] hover:underline">添加一场面试</button></div></div>}
            </div>
          </div>
        </div>
      </section>
    </div>

    <section className="grid gap-5 lg:grid-cols-[minmax(0,.9fr)_minmax(0,1.1fr)]">
      <div className="rounded-3xl border border-[#dfe7e4] bg-white p-5 shadow-[0_12px_36px_rgba(23,45,56,0.04)] sm:p-6">
        <div className="flex items-center gap-2"><span className="grid h-9 w-9 place-items-center rounded-xl bg-[#e9f3ef] text-[#3b7668]"><BarChart3 size={18} /></span><div><h2 className="font-semibold text-[#1c3442]">岗位状态分布</h2><p className="text-xs text-slate-400">按当前状态统计 · {overview?.application_count ?? 0} 个已跟踪岗位</p></div></div>
        {overview?.application_count ? <div className="mt-5 space-y-3">{overview.status_counts.filter((status) => status.count > 0).map((status) => <div key={status.id}>
          <div className="mb-1.5 flex items-center justify-between gap-3 text-xs"><span className="truncate font-medium text-[#53645f]">{status.name}</span><span className="shrink-0 tabular-nums text-slate-500">{status.count}</span></div><div className="h-2 overflow-hidden rounded-full bg-[#f0f3f1]"><div className="h-full rounded-full bg-[#669785] transition-all" style={{ width: `${Math.max(4, (status.count / overview.application_count) * 100)}%` }} /></div>
        </div>)}</div> : <div className="mt-5 rounded-2xl bg-[#f8faf9] px-4 py-7 text-center text-sm text-slate-400">保存岗位后，这里会展示真实状态分布。</div>}
      </div>
      <div className="rounded-3xl border border-[#dfe7e4] bg-white p-5 shadow-[0_12px_36px_rgba(23,45,56,0.04)] sm:p-6">
        <div className="flex items-center gap-2"><span className="grid h-9 w-9 place-items-center rounded-xl bg-[#f8efe5] text-[#a3683f]"><AlarmClock size={18} /></span><div><h2 className="font-semibold text-[#1c3442]">近期进度记录</h2><p className="text-xs text-slate-400">根据岗位状态事件汇总 · 最近 6 周</p></div></div>
        {overview?.weekly_status_events.some((week) => week.count > 0) ? <div className="mt-5 flex h-28 items-end gap-2 sm:gap-3">{overview.weekly_status_events.map((week) => {
          const max = Math.max(...overview.weekly_status_events.map((item) => item.count), 1);
          const height = Math.max(8, (week.count / max) * 72);
          return <div key={week.week_start} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1.5"><span className="text-[10px] tabular-nums text-slate-400">{week.count || ""}</span><div className="w-full max-w-12 rounded-t-md bg-[#9db9ad] transition-all" style={{ height }} /><span className="text-[9px] text-slate-400">{week.week_start.slice(5).replace("-", "/")}</span></div>;
        })}</div> : <div className="mt-5 grid h-28 place-items-center rounded-2xl bg-[#f8faf9] px-4 text-center text-sm text-slate-400">还没有状态变更记录；后续调整岗位状态后会从真实事件生成趋势。</div>}
      </div>
    </section>

    <section className="grid gap-3 sm:grid-cols-3">
      <Shortcut to="/jobs/search" icon={<Search size={17} />} title="搜索岗位" detail="发现并筛选新的机会" />
      <Shortcut to="/profile" icon={<FileUser size={17} />} title="完善个人画像" detail="更新求职方向与简历" />
      <Shortcut to="/agent" icon={<Circle size={17} />} title="求职 Agent" detail="查询岗位并讨论下一步" />
    </section>

    {todoModalOpen && <Modal title={editingTodo ? "编辑待办" : "新增待办"} description="记下一项要完成的行动；截止时间和其他设置都可以稍后补充。" onClose={() => { setTodoModalOpen(false); setEditingTodo(null); }}>
      <form onSubmit={saveTodo} className="space-y-4">
        <Field label="要做什么？"><input autoFocus required maxLength={200} value={todoForm.title} onChange={(event) => setTodoForm({ ...todoForm, title: event.target.value })} placeholder="例如：整理项目经历、准备技术面试" className={inputClass} /></Field>
        <Field label="截止时间（可选，北京时间）"><input type="datetime-local" value={todoForm.due_at} onChange={(event) => setTodoForm({ ...todoForm, due_at: event.target.value })} className={inputClass} /></Field>
        <details className="group rounded-2xl border border-[#e7ece9] bg-[#fafcfb]">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-[#40574f]"><span>更多设置</span><span className="flex items-center gap-2 text-xs font-normal text-slate-400">关联岗位 · 优先级 · 备注<ChevronDown size={15} className="shrink-0 transition group-open:rotate-180" /></span></summary>
          <div className="space-y-4 border-t border-[#e7ece9] px-4 py-4">
            <Field label="关联岗位（可选）"><select value={todoForm.application_id} onChange={(event) => setTodoForm({ ...todoForm, application_id: event.target.value })} className={inputClass}><option value="">不关联岗位</option>{applications.map((item) => <option key={item.id} value={item.id}>{item.job.company_name} · {item.job.title}</option>)}</select></Field>
            <Field label="优先级"><div className="flex flex-wrap gap-2">{(["high", "normal", "low"] as const).map((priority) => <button type="button" key={priority} onClick={() => setTodoForm({ ...todoForm, priority })} className={`rounded-xl border px-3 py-2 text-xs font-semibold transition ${todoForm.priority === priority ? "border-[#8fb0a5] bg-[#eff6f2] text-[#2d685b]" : "border-[#e3e9e6] text-slate-500 hover:bg-[#f8faf9]"}`}>{priorityLabel(priority)}</button>)}</div></Field>
            <Field label="备注（可选）"><textarea maxLength={4000} rows={2} value={todoForm.note} onChange={(event) => setTodoForm({ ...todoForm, note: event.target.value })} placeholder="补充需要记住的内容" className={`${inputClass} resize-y`} /></Field>
          </div>
        </details>
        {formError && <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{formError}</p>}
        <ModalActions saving={saving} onCancel={() => setTodoModalOpen(false)} submitLabel={editingTodo ? "保存修改" : "创建待办"} />
      </form>
    </Modal>}

    {interviewModalOpen && <Modal title={editingInterview ? "编辑面试" : "安排面试"} description="记录已经约定的面试时间；此操作不会自动更改岗位状态。" onClose={() => { setInterviewModalOpen(false); setEditingInterview(null); }}>
      <form onSubmit={saveInterview} className="space-y-4">
        <Field label="面试轮次"><input autoFocus required maxLength={200} value={interviewForm.title} onChange={(event) => setInterviewForm({ ...interviewForm, title: event.target.value })} placeholder="例如：技术一面" className={inputClass} /></Field>
        <Field label="开始时间（北京时间）"><input required type="datetime-local" value={interviewForm.starts_at} onChange={(event) => setInterviewForm({ ...interviewForm, starts_at: event.target.value })} className={inputClass} /></Field>
        <Field label="关联已跟踪岗位（可选）"><select value={interviewForm.application_id} onChange={(event) => {
          const applicationId = event.target.value;
          const application = applicationById.get(Number(applicationId));
          setInterviewForm({ ...interviewForm, application_id: applicationId, company_name: application?.job.company_name ?? interviewForm.company_name, position_title: application?.job.title ?? interviewForm.position_title });
        }} className={inputClass}><option value="">不关联岗位</option>{applications.map((item) => <option key={item.id} value={item.id}>{item.job.company_name} · {item.job.title}</option>)}</select></Field>
        <details className="group rounded-2xl border border-[#e7ece9] bg-[#fafcfb]">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-[#40574f]"><span>补充信息</span><span className="flex items-center gap-2 text-right text-xs font-normal text-slate-400">结束时间 · 形式 · 地点 / 链接 · 备注<ChevronDown size={15} className="shrink-0 transition group-open:rotate-180" /></span></summary>
          <div className="space-y-4 border-t border-[#e7ece9] px-4 py-4">
            {!interviewForm.application_id && <div className="grid gap-4 sm:grid-cols-2"><Field label="公司（可选）"><input maxLength={200} value={interviewForm.company_name} onChange={(event) => setInterviewForm({ ...interviewForm, company_name: event.target.value })} placeholder="公司名称" className={inputClass} /></Field><Field label="岗位（可选）"><input maxLength={300} value={interviewForm.position_title} onChange={(event) => setInterviewForm({ ...interviewForm, position_title: event.target.value })} placeholder="岗位名称" className={inputClass} /></Field></div>}
            <div className="grid gap-4 sm:grid-cols-2"><Field label="结束时间（可选）"><input type="datetime-local" value={interviewForm.ends_at} onChange={(event) => setInterviewForm({ ...interviewForm, ends_at: event.target.value })} className={inputClass} /></Field><Field label="面试形式"><select value={interviewForm.interview_format} onChange={(event) => setInterviewForm({ ...interviewForm, interview_format: event.target.value as InterviewFormat })} className={inputClass}><option value="unknown">未设置</option><option value="online">线上</option><option value="in_person">线下</option><option value="phone">电话</option></select></Field></div>
            <div className="grid gap-4 sm:grid-cols-2"><Field label="地点（可选）"><input maxLength={500} value={interviewForm.location} onChange={(event) => setInterviewForm({ ...interviewForm, location: event.target.value })} placeholder="线下面试地址或会议平台" className={inputClass} /></Field><Field label="会议链接（可选）"><input type="url" maxLength={1000} value={interviewForm.meeting_url} onChange={(event) => setInterviewForm({ ...interviewForm, meeting_url: event.target.value })} placeholder="https://…" className={inputClass} /></Field></div>
            <Field label="备注（可选）"><textarea maxLength={4000} rows={2} value={interviewForm.note} onChange={(event) => setInterviewForm({ ...interviewForm, note: event.target.value })} placeholder="联系人或准备重点" className={`${inputClass} resize-y`} /></Field>
          </div>
        </details>
        {formError && <p role="alert" className="rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{formError}</p>}
        <ModalActions saving={saving} onCancel={() => setInterviewModalOpen(false)} submitLabel={editingInterview ? "保存修改" : "保存面试"} />
      </form>
    </Modal>}
  </section>;
}

const inputClass = "w-full rounded-xl border border-[#dfe7e3] bg-white px-3.5 py-2.5 text-sm text-[#263b46] outline-none transition placeholder:text-slate-400 focus:border-[#8ca99e] focus:ring-2 focus:ring-[#e1ede7]";

function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return <div className="grid min-h-52 place-items-center px-5 py-8 text-center"><div><p className="font-semibold text-[#344943]">{title}</p><p className="mt-1 text-sm text-slate-400">{detail}</p>{action && <div className="mt-3 text-sm">{action}</div>}</div></div>;
}

function Shortcut({ to, icon, title, detail }: { to: string; icon: ReactNode; title: string; detail: string }) {
  return <Link to={to} className="group flex items-center gap-3 rounded-2xl border border-[#e1e8e5] bg-white px-4 py-4 transition hover:border-[#b7cbc3] hover:bg-[#fbfcfb]"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-[#eff5f1] text-[#47796d]">{icon}</span><span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-[#2a414b]">{title}</span><span className="mt-0.5 block truncate text-xs text-slate-400">{detail}</span></span><ArrowRight size={15} className="shrink-0 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-[#47796d]" /></Link>;
}

function Modal({ title, description, onClose, children }: { title: string; description: string; onClose: () => void; children: ReactNode }) {
  return <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-[#152934]/45 p-4 backdrop-blur-[3px]" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section role="dialog" aria-modal="true" aria-label={title} className="my-auto max-h-[min(90vh,860px)] w-full max-w-2xl overflow-y-auto rounded-3xl border border-white/70 bg-[#fdfefd] p-5 shadow-[0_24px_90px_rgba(12,31,40,0.24)] sm:p-7">
      <div className="mb-5 flex items-start justify-between gap-3"><div><h2 className="text-xl font-semibold text-[#213744]">{title}</h2><p className="mt-1.5 text-sm leading-5 text-slate-500">{description}</p></div><button onClick={onClose} aria-label="关闭" className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-slate-400 hover:bg-[#f0f4f2] hover:text-slate-700"><X size={18} /></button></div>
      {children}
    </section>
  </div>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="block min-w-0"><span className="mb-1.5 block text-xs font-semibold text-[#52645f]">{label}</span>{children}</label>;
}

function ModalActions({ saving, onCancel, submitLabel }: { saving: boolean; onCancel: () => void; submitLabel: string }) {
  return <div className="flex justify-end gap-2 border-t border-[#edf1ef] pt-4"><button type="button" onClick={onCancel} className="rounded-xl border border-[#dfe7e3] px-4 py-2.5 text-sm font-semibold text-slate-600 hover:bg-[#f6f8f7]">取消</button><button type="submit" disabled={saving} className="rounded-xl bg-[#1f4943] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#285b53] disabled:cursor-wait disabled:opacity-60">{saving ? "保存中…" : submitLabel}</button></div>;
}
