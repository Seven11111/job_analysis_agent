import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  BookmarkPlus,
  Bot,
  BriefcaseBusiness,
  CalendarDays,
  Check,
  ChevronDown,
  CircleAlert,
  ExternalLink,
  FileText,
  LoaderCircle,
  MapPin,
  MessageSquarePlus,
  Pencil,
  Search,
  Send,
  Square,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  createAgentSession,
  cancelAgentRun,
  getAgentSession,
  listAgentSessions,
  renameAgentSession,
  resolveAgentAction,
  streamAgentChat,
  type AgentMessage,
  type AgentRunEvent,
  type AgentSession,
  type AgentStreamEvent,
} from "../api/client";
import {
  formatJobSearchProviders,
  JOB_SEARCH_PROVIDERS_STORAGE_KEY,
  readJobSearchProviders,
  type JobSearchProvider,
} from "../stores/jobSearchPreferences";

interface ChatLine extends AgentMessage {
  localId?: string;
  streaming?: boolean;
  incomplete?: boolean;
  linkPreviews?: JobLinkPreview[];
}

interface JobLinkPreview {
  preview_token: string;
  warnings: string[];
  job: {
    title: string;
    company_name: string;
    city: string;
    job_type?: string;
    published_date: string | null;
    salary?: { min: number | null; max: number | null; unit: string | null; status: string; display?: string };
    detail_url: string;
    source?: { name?: string };
    extraction_method?: string;
    description?: string | null;
    requirements?: string | null;
    responsibilities?: string | null;
  };
}

const suggestions = [
  { icon: Search, label: "帮我找上海的后端实习", prompt: "帮我搜索上海的后端开发实习，优先最近一周发布的岗位。" },
  { icon: BriefcaseBusiness, label: "搜索校招公告", prompt: "帮我搜索杭州的人工智能相关校招公告，筛选 2027 届。" },
  { icon: BriefcaseBusiness, label: "看看我的岗位进度", prompt: "查询我保存了哪些岗位，以及目前各自的状态和进度。" },
  { icon: CalendarDays, label: "查看待办和面试", prompt: "查询我当前未完成的求职待办，以及接下来一周的面试安排。" },
  { icon: UserRound, label: "查看我的求职画像", prompt: "请读取我的求职画像，告诉我目前设定了哪些意向。" },
  { icon: FileText, label: "查看当前简历", prompt: "请查看我的当前在线简历，并指出内容覆盖了什么。" },
];

const activityLabels: Record<string, string> = {
  get_provider_status: "检查岗位来源与模型状态",
  start_boss_login: "启动 BOSS 官方登录",
  cancel_boss_login: "停止 BOSS 登录",
  preview_job_link: "读取岗位链接",
  search_jobs: "搜索实习岗位",
  list_saved_jobs: "查询已保存岗位",
  get_saved_job_detail: "读取岗位详情与状态历史",
  compare_saved_jobs: "对比已保存岗位",
  get_application_status: "汇总投递进度",
  get_candidate_profile: "读取个人画像",
  get_current_resume: "读取当前简历",
  propose_save_job: "准备收藏岗位",
  propose_application_update: "准备修改岗位记录",
  propose_remove_saved_job: "准备移除岗位记录",
  propose_profile_update: "准备修改个人画像",
  propose_resume_update: "准备更新在线简历",
  analyze_saved_job: "分析岗位匹配度",
  search_campus_recruit: "搜索校招资讯",
  set_job_recommendation_feedback: "记录推荐反馈",
  get_workbench_overview: "读取工作台统计",
  list_todos: "查询求职待办",
  list_interviews: "查询面试安排",
  list_job_subscriptions: "查询岗位订阅",
  get_job_subscription: "读取岗位订阅详情",
  list_job_subscription_runs: "查询查新运行历史",
  get_job_subscription_run: "读取查新结果预览",
  run_job_subscription: "立即执行岗位查新",
  propose_job_subscription_create: "准备创建岗位订阅",
  propose_job_subscription_update: "准备修改岗位订阅",
  propose_job_subscription_delete: "准备删除岗位订阅",
  list_profile_facts: "查询画像记忆",
  list_resume_attachments: "查询附件简历",
  list_resume_versions: "查询在线简历版本",
  propose_todo_create: "准备新增待办",
  propose_todo_update: "准备修改待办",
  propose_todo_delete: "准备删除待办",
  propose_interview_create: "准备新增面试安排",
  propose_interview_update: "准备修改面试安排",
  propose_interview_delete: "准备删除面试安排",
  propose_status_create: "准备新增投递状态",
  propose_status_update: "准备修改投递状态",
  propose_profile_fact_create: "准备新增画像记忆",
  propose_profile_fact_update: "准备修改画像记忆",
  propose_confirm_profile_facts: "准备确认画像记忆",
  propose_confirm_resume_attachment: "准备确认附件简历",
  propose_select_resume: "准备切换当前简历",
  propose_delete_resume_attachment: "准备删除附件简历",
};

function localMessage(role: ChatLine["role"], content: string, localId: string): ChatLine {
  return {
    id: -Date.now(),
    role,
    content,
    structured_content: null,
    created_at: new Date().toISOString(),
    localId,
  };
}

function hydrateMessage(message: AgentMessage): ChatLine {
  const structured = message.structured_content;
  return {
    ...message,
    incomplete: structured?.interrupted === true || structured?.incomplete === true,
    linkPreviews: getLinkPreviews(structured),
  };
}

function getLinkPreviews(structured: Record<string, unknown> | null): JobLinkPreview[] {
  const evidence = structured?.verified_evidence;
  if (!Array.isArray(evidence)) return [];
  return evidence
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .filter((item) => item.tool === "preview_job_link")
    .map((item) => normalizeJobLinkPreview(item.result))
    .filter((item): item is JobLinkPreview => item !== null);
}

function normalizeJobLinkPreview(value: unknown): JobLinkPreview | null {
  if (!value || typeof value !== "object") return null;
  const result = value as Record<string, unknown>;
  const jobValue = result.job;
  if (!jobValue || typeof jobValue !== "object") return null;
  const job = jobValue as Record<string, unknown>;
  if (typeof result.preview_token !== "string" || typeof job.detail_url !== "string" || typeof job.title !== "string") return null;
  const salary = job.salary && typeof job.salary === "object" ? job.salary as Record<string, unknown> : undefined;
  const source = job.source && typeof job.source === "object" ? job.source as Record<string, unknown> : undefined;
  return {
    preview_token: result.preview_token,
    warnings: Array.isArray(result.warnings) ? result.warnings.filter((item): item is string => typeof item === "string") : [],
    job: {
      title: job.title,
      company_name: typeof job.company_name === "string" ? job.company_name : "公司待确认",
      city: typeof job.city === "string" ? job.city : "地点待确认",
      job_type: typeof job.job_type === "string" ? job.job_type : undefined,
      published_date: typeof job.published_date === "string" ? job.published_date : null,
      salary: salary ? {
        min: typeof salary.min === "number" ? salary.min : null,
        max: typeof salary.max === "number" ? salary.max : null,
        unit: typeof salary.unit === "string" ? salary.unit : null,
        status: typeof salary.status === "string" ? salary.status : "unknown",
        display: typeof salary.display === "string" ? salary.display : undefined,
      } : undefined,
      detail_url: job.detail_url,
      source: source ? { name: typeof source.name === "string" ? source.name : undefined } : undefined,
      extraction_method: typeof job.extraction_method === "string" ? job.extraction_method : undefined,
      description: typeof job.description === "string" ? job.description : null,
      requirements: typeof job.requirements === "string" ? job.requirements : null,
      responsibilities: typeof job.responsibilities === "string" ? job.responsibilities : null,
    },
  };
}

interface OperationStep {
  id: number;
  name: string;
  status: string;
  summary: string | null;
  parameterSummary: string | null;
  durationMs: number | null;
  eventType: string;
}

function buildOperationSteps(events: AgentRunEvent[]): OperationStep[] {
  const steps: OperationStep[] = [];
  for (const event of events) {
    if (event.event_type === "tool_started") {
      const parameterSummary = typeof event.payload?.parameter_summary === "string" ? event.payload.parameter_summary : null;
      steps.push({ id: event.id, name: event.name ?? event.event_type, status: "running", summary: null, parameterSummary, durationMs: null, eventType: event.event_type });
    } else if (event.event_type === "tool_completed") {
      let pendingIndex = -1;
      for (let index = steps.length - 1; index >= 0; index -= 1) {
        if (steps[index].name === (event.name ?? event.event_type) && steps[index].status === "running") {
          pendingIndex = index;
          break;
        }
      }
      const summary = typeof event.payload?.summary === "string" ? event.payload.summary : null;
      const durationMs = typeof event.payload?.duration_ms === "number" ? event.payload.duration_ms : null;
      if (pendingIndex >= 0) {
        steps[pendingIndex] = { ...steps[pendingIndex], status: event.status, summary, durationMs };
      } else {
        steps.push({ id: event.id, name: event.name ?? event.event_type, status: event.status, summary, parameterSummary: null, durationMs, eventType: event.event_type });
      }
    } else if (event.event_type === "action_proposed") {
      const actionSummary = event.status === "pending"
        ? "等待确认后才会修改数据"
        : event.status === "rejected"
          ? "已取消，没有修改数据"
          : event.status === "failed"
            ? "确认后执行失败"
            : "操作已确认并处理";
      steps.push({
        id: event.id,
        name: event.name ?? event.event_type,
        status: event.status,
        summary: actionSummary,
        parameterSummary: null,
        durationMs: null,
        eventType: event.event_type,
      });
    }
  }
  return steps;
}

function OperationTrace({ steps, running, failed, cancelled }: {
  steps: OperationStep[];
  running: boolean;
  failed: boolean;
  cancelled: boolean;
}) {
  const activeStep = [...steps].reverse().find((step) => step.status === "running");
  const pendingStep = [...steps].reverse().find((step) => step.status === "pending");
  const title = running
    ? pendingStep ? "等待操作确认" : activityLabels[activeStep?.name ?? ""] ?? (activeStep ? activeStep.name : "正在整理回复")
    : failed ? "本轮未完成" : cancelled ? "已停止" : `已完成 ${steps.length} 项操作`;

  return (
    <details open={running} className="group ml-11 max-w-2xl overflow-hidden rounded-xl border border-slate-200/80 bg-[#fbfdff]">
      <summary className="flex cursor-pointer list-none items-center gap-2.5 px-3.5 py-2.5 text-xs marker:hidden [&::-webkit-details-marker]:hidden">
        <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-lg ${running ? "bg-blue-50 text-brand" : failed ? "bg-rose-50 text-rose-600" : cancelled ? "bg-amber-50 text-amber-600" : "bg-emerald-50 text-emerald-600"}`}>
          {running ? <LoaderCircle size={13} className="animate-spin" /> : failed ? <CircleAlert size={13} /> : cancelled ? <Square size={11} /> : <Check size={13} />}
        </span>
        <span className="min-w-0 flex-1 truncate font-medium text-slate-700">执行过程 · {title}</span>
        <span className="shrink-0 text-[10px] text-slate-400">{steps.length} 步</span>
        <ChevronDown size={14} className="shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-2 border-t border-slate-100 px-3.5 py-3">
        {steps.map((step) => (
          <div key={step.id} className="flex min-w-0 items-center gap-2 text-xs">
            {step.status === "running" ? <LoaderCircle size={13} className="shrink-0 animate-spin text-brand" />
              : step.status === "failed" ? <CircleAlert size={13} className="shrink-0 text-rose-500" />
                : step.status === "rejected" ? <X size={13} className="shrink-0 text-slate-400" />
                : step.status === "pending" ? <Pencil size={13} className="shrink-0 text-amber-500" />
                  : <Check size={13} className="shrink-0 text-emerald-600" />}
            <div className="min-w-0 flex-1">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="shrink-0 font-medium text-slate-600">{activityLabels[step.name] ?? step.name}</span>
                {step.summary ? <span className="truncate text-slate-400">· {step.summary}</span> : null}
                {step.durationMs !== null ? <span className="ml-auto shrink-0 text-[10px] tabular-nums text-slate-400">{step.durationMs < 1000 ? `${step.durationMs} ms` : `${(step.durationMs / 1000).toFixed(1)} s`}</span> : null}
              </div>
              {step.parameterSummary ? <div className="mt-0.5 truncate text-[10px] text-slate-400">参数 · {step.parameterSummary}</div> : null}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

export function AgentPage() {
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [searchProviders, setSearchProviders] = useState<JobSearchProvider[]>(() => readJobSearchProviders());
  const [messages, setMessages] = useState<ChatLine[]>([]);
  const [events, setEvents] = useState<AgentRunEvent[]>([]);
  const [draft, setDraft] = useState("");
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [sending, setSending] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [resolvingAction, setResolvingAction] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [renamingSessionId, setRenamingSessionId] = useState<number | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const skipNextLoadRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    listAgentSessions()
      .then((items) => {
        if (cancelled) return;
        setSessions(items);
        if (items.length) setActiveSessionId(items[0].id);
      })
      .catch(() => {
        if (!cancelled) setError("无法读取历史对话，请确认后端服务正在运行。");
      })
      .finally(() => {
        if (!cancelled) setLoadingSessions(false);
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (activeSessionId === null) {
      setMessages([]);
      setEvents([]);
      setActiveRunId(null);
      return;
    }
    if (skipNextLoadRef.current === activeSessionId) {
      skipNextLoadRef.current = null;
      setMessages([]);
      setEvents([]);
      setActiveRunId(null);
      setLoadingConversation(false);
      return;
    }
    let cancelled = false;
    setLoadingConversation(true);
    getAgentSession(activeSessionId)
      .then((detail) => {
        if (cancelled) return;
        setMessages(detail.messages.map(hydrateMessage));
        setEvents(detail.events);
        setActiveRunId(detail.events.at(-1)?.run_id ?? null);
        setError(null);
      })
      .catch(() => {
        if (!cancelled) setError("读取这段对话失败，请重试。");
      })
      .finally(() => {
        if (!cancelled) setLoadingConversation(false);
      });
    return () => { cancelled = true; };
  }, [activeSessionId]);

  useEffect(() => {
    const syncSearchProviders = (event: StorageEvent) => {
      if (event.key === JOB_SEARCH_PROVIDERS_STORAGE_KEY || event.key === null) {
        setSearchProviders(readJobSearchProviders());
      }
    };
    window.addEventListener("storage", syncSearchProviders);
    return () => window.removeEventListener("storage", syncSearchProviders);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: sending ? "smooth" : "auto", block: "end" });
  }, [messages, events, sending]);

  const activeSession = sessions.find((item) => item.id === activeSessionId) ?? null;
  const pendingActions = useMemo(
    () => events.filter((event) => event.event_type === "action_proposed" && event.status === "pending"),
    [events],
  );
  const hasPendingActions = pendingActions.length > 0;
  const visibleEvents = useMemo(() => {
    const runId = activeRunId ?? events.at(-1)?.run_id;
    return runId ? events.filter((event) => event.run_id === runId) : [];
  }, [activeRunId, events]);
  const operationSteps = useMemo(() => buildOperationSteps(visibleEvents), [visibleEvents]);
  const latestAssistantIndex = messages.reduce(
    (latest, message, index) => message.role === "assistant" ? index : latest,
    -1,
  );
  const runFailed = visibleEvents.some((event) => event.event_type === "run_failed");
  const runCancelled = visibleEvents.some((event) => event.event_type === "run_cancelled");

  async function newConversation() {
    if (sending) return;
    try {
      const created = await createAgentSession();
      setSessions((current) => [created, ...current]);
      skipNextLoadRef.current = created.id;
      setActiveSessionId(created.id);
      setError(null);
    } catch {
      setError("新建对话失败，请稍后重试。");
    }
  }

  async function refreshConversation(sessionId: number) {
    const [detail, updatedSessions] = await Promise.all([getAgentSession(sessionId), listAgentSessions()]);
    setMessages(detail.messages.map(hydrateMessage));
    setEvents(detail.events);
    setActiveRunId(detail.events.at(-1)?.run_id ?? null);
    setSessions(updatedSessions);
  }

  async function sendMessage(text = draft) {
    const message = text.trim();
    if (!message || sending) return;
    if (hasPendingActions) {
      setError("请先确认或取消上方的待处理操作，再继续这段对话。");
      return;
    }
    setSending(true);
    setStopping(false);
    setActiveRunId(null);
    setError(null);
    setDraft("");

    let sessionId = activeSessionId;
    try {
      if (sessionId === null) {
        const created = await createAgentSession();
        sessionId = created.id;
        setSessions((current) => [created, ...current]);
        skipNextLoadRef.current = created.id;
        setActiveSessionId(created.id);
        setMessages([]);
        setEvents([]);
      }
      const userId = `user-${Date.now()}`;
      const assistantId = `assistant-${Date.now()}`;
      const providersForRequest = readJobSearchProviders();
      setSearchProviders(providersForRequest);
      setMessages((current) => [
        ...current,
        localMessage("user", message, userId),
        { ...localMessage("assistant", "", assistantId), streaming: true },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      await streamAgentChat({ message, session_id: sessionId, search_providers: providersForRequest }, controller.signal, (event) => {
        handleStreamEvent(event, assistantId, sessionId as number, controller);
      });
      await refreshConversation(sessionId);
    } catch (caught) {
      if (!abortRef.current?.signal.aborted) {
        const messageText = caught instanceof Error ? caught.message : "网络连接失败，请检查后端服务。";
        setError(messageText || "本轮对话失败，请稍后重试。");
        setDraft((current) => current || message);
        setMessages((current) => current.map((item) => item.streaming
          ? { ...item, content: item.content || "本轮没有完成，请检查服务后重试。", streaming: false, incomplete: true }
          : item));
        if (sessionId !== null) await refreshConversation(sessionId).catch(() => undefined);
      }
    } finally {
      abortRef.current = null;
      setSending(false);
      setStopping(false);
      textareaRef.current?.focus();
    }
  }

  async function requestStop() {
    if (!activeSessionId || !activeRunId || stopping) return;
    setStopping(true);
    setError(null);
    try {
      const result = await cancelAgentRun(activeSessionId, activeRunId);
      if (result.status !== "cancellation_requested") setStopping(false);
    } catch (caught) {
      setStopping(false);
      setError(caught instanceof Error ? caught.message : "停止请求未能发送，请稍后重试。");
    }
  }

  function handleStreamEvent(event: AgentStreamEvent, assistantId: string, sessionId: number, controller: AbortController) {
    if (event.type === "run_started") {
      setActiveRunId(event.run_id ?? null);
    }
    if (event.type === "assistant_delta") {
      const text = String(event.payload?.text ?? "");
      if (text) {
        setMessages((current) => current.map((item) => item.localId === assistantId
          ? { ...item, content: `${item.content ?? ""}${text}` }
          : item));
      }
    }
    if (event.type === "tool_completed" && event.name === "preview_job_link" && event.status === "succeeded") {
      const preview = normalizeJobLinkPreview(event.payload?.result);
      if (preview) {
        setMessages((current) => {
          let assistantIndex = -1;
          for (let index = current.length - 1; index >= 0; index -= 1) {
            if (current[index].localId === assistantId) {
              assistantIndex = index;
              break;
            }
          }
          if (assistantIndex < 0) return current;
          return current.map((item, index) => index === assistantIndex
            ? { ...item, linkPreviews: [...(item.linkPreviews ?? []), preview] }
            : item);
        });
      }
    }
    if (["tool_started", "tool_completed", "action_proposed", "action_resolved", "assistant_delta", "assistant_completed", "run_failed", "run_cancelled"].includes(event.type)) {
      const normalized: AgentRunEvent = {
        id: event.id ?? -Date.now() - Math.random(),
        run_id: event.run_id ?? activeRunId ?? "current",
        sequence: event.sequence ?? 0,
        event_type: event.type,
        name: event.name ?? null,
        status: event.status ?? "running",
        payload: event.payload ?? null,
        error_message: event.error_message ?? null,
        started_at: event.started_at ?? null,
        completed_at: event.completed_at ?? null,
      };
      setEvents((current) => [...current.filter((item) => item.id !== normalized.id), normalized]);
    }
    if (event.type === "assistant_completed") {
      const finalText = String(event.payload?.text ?? "");
      setMessages((current) => current.map((item) => item.localId === assistantId
        ? { ...item, content: finalText || item.content, streaming: false }
        : item));
      controller.abort();
    }
    if (event.type === "run_failed") {
      const failedMessage = String(event.payload?.message ?? "本轮处理失败，请稍后重试。");
      setError(failedMessage);
      setMessages((current) => current.map((item) => item.localId === assistantId
        ? { ...item, content: item.content || failedMessage, streaming: false, incomplete: true }
        : item));
      controller.abort();
    }
    if (event.type === "run_cancelled") {
      setStopping(false);
      setMessages((current) => current.map((item) => item.localId === assistantId
        ? { ...item, streaming: false, incomplete: true, structured_content: { interrupted: true } }
        : item));
    }
    if (event.type === "stream_error") {
      setError(event.error_message ?? "服务端事件解析失败。");
      controller.abort();
    }
    if (event.type === "assistant_completed" || event.type === "run_failed" || event.type === "run_cancelled") {
      window.setTimeout(() => { void refreshConversation(sessionId).catch(() => undefined); }, 0);
    }
  }

  async function resolveAction(event: AgentRunEvent, confirm: boolean) {
    setResolvingAction(event.id);
    setError(null);
    try {
      const result = await resolveAgentAction(event.id, confirm);
      if (sending) {
        setEvents((current) => current.map((item) => item.id === event.id ? { ...item, status: result.status } : item));
      } else if (activeSessionId !== null) await refreshConversation(activeSessionId);
      else setEvents((current) => current.map((item) => item.id === event.id ? { ...item, status: result.status } : item));
      if (result.status === "failed") setError(result.message);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "操作未能完成，请刷新后重试。");
    } finally {
      setResolvingAction(null);
    }
  }

  async function saveRename(sessionId: number) {
    const title = renameDraft.trim();
    if (!title) return;
    try {
      const updated = await renameAgentSession(sessionId, title);
      setSessions((current) => current.map((item) => item.id === sessionId ? updated : item));
      setRenamingSessionId(null);
      setRenameDraft("");
    } catch {
      setError("重命名失败，请重试。");
    }
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  return (
    <section className="mx-auto flex h-[calc(100vh-6rem)] min-h-[580px] max-w-[1500px] overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-[0_18px_60px_-36px_rgba(30,64,110,0.28)]">
      <aside className="flex w-[270px] shrink-0 flex-col border-r border-slate-200 bg-[#fbfdff]">
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-4">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-blue-50 text-brand"><Bot size={19} /></span>
            <div><p className="text-sm font-semibold text-ink">求职 Agent</p><p className="text-[11px] text-slate-400">本地对话记录</p></div>
          </div>
          <button onClick={() => void newConversation()} disabled={sending} title="新建对话" className="rounded-lg p-2 text-slate-500 transition hover:bg-blue-50 hover:text-brand disabled:opacity-40">
            <MessageSquarePlus size={18} />
          </button>
        </div>
        <div className="px-3 pt-4">
          <button onClick={() => void newConversation()} disabled={sending} className="flex w-full items-center justify-center gap-2 rounded-xl border border-blue-200 bg-white px-3 py-2.5 text-sm font-semibold text-brand transition hover:bg-blue-50 disabled:opacity-40">
            <MessageSquarePlus size={16} /> 新建对话
          </button>
          <p className="px-2 pb-2 pt-5 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">历史对话</p>
        </div>
        <div className="city-picker-scrollbar flex-1 space-y-1 overflow-y-auto px-2 pb-3">
          {loadingSessions ? <div className="px-3 py-5 text-xs text-slate-400">正在读取…</div> : null}
          {!loadingSessions && sessions.length === 0 ? <div className="px-3 py-5 text-xs leading-5 text-slate-400">还没有对话。开始提问后会自动保存在这里。</div> : null}
          {sessions.map((item) => (
            <div key={item.id} className={`group flex items-center gap-1 rounded-xl px-2 py-1 ${activeSessionId === item.id ? "bg-blue-50" : "hover:bg-slate-100/80"}`}>
              {renamingSessionId === item.id ? (
                <form className="flex min-w-0 flex-1 items-center gap-1" onSubmit={(e) => { e.preventDefault(); void saveRename(item.id); }}>
                  <input autoFocus value={renameDraft} onChange={(e) => setRenameDraft(e.target.value)} className="min-w-0 flex-1 rounded-md border border-blue-200 bg-white px-2 py-1.5 text-xs outline-none" />
                  <button type="submit" aria-label="保存名称" className="rounded p-1 text-emerald-600 hover:bg-emerald-50"><Check size={14} /></button>
                  <button type="button" aria-label="取消重命名" onClick={() => setRenamingSessionId(null)} className="rounded p-1 text-slate-400 hover:bg-slate-200"><X size={14} /></button>
                </form>
              ) : (
                <>
                  <button onClick={() => { if (!sending) setActiveSessionId(item.id); }} className="min-w-0 flex-1 px-2 py-2 text-left">
                    <span className={`block truncate text-xs font-medium ${activeSessionId === item.id ? "text-brand" : "text-slate-700"}`}>{item.title || "新对话"}</span>
                    <span className="mt-1 block text-[10px] text-slate-400">{item.message_count} 条消息 · {formatShortDate(item.updated_at)}</span>
                  </button>
                  <button
                    onClick={() => { setRenamingSessionId(item.id); setRenameDraft(item.title || ""); }}
                    aria-label={`重命名${item.title ?? "对话"}`}
                    className="rounded p-1.5 text-slate-300 opacity-0 transition hover:bg-white hover:text-slate-600 group-hover:opacity-100"
                  ><Pencil size={13} /></button>
                </>
              )}
            </div>
          ))}
        </div>
        <div className="border-t border-slate-100 px-4 py-3 text-[11px] leading-5 text-slate-400">
          工作台与个人数据的写入、修改和删除，都会先展示确认卡片。
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col bg-white">
        <header className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-ink">{activeSession?.title || "新对话"}</h1>
            <p className="mt-1 flex items-center gap-1.5 text-[11px] text-slate-400"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> 对话保存在本地，可随时切换继续</p>
          </div>
          {sending ? <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1.5 text-xs text-brand"><LoaderCircle size={14} className="animate-spin" /> {stopping ? "正在停止" : "正在处理"}</span> : <span className={`hidden items-center gap-1.5 rounded-full px-3 py-1.5 text-xs sm:inline-flex ${searchProviders.length ? "bg-slate-50 text-slate-500" : "bg-amber-50 text-amber-700"}`}><Sparkles size={14} /> 可用搜索来源：{formatJobSearchProviders(searchProviders)}</span>}
        </header>

        {error ? <div role="alert" className="mx-6 mt-4 flex items-start gap-2 rounded-xl border border-rose-100 bg-rose-50 px-3 py-2.5 text-xs leading-5 text-rose-700"><CircleAlert size={15} className="mt-0.5 shrink-0" /> <span className="flex-1">{error}</span><button onClick={() => setError(null)} aria-label="关闭错误提示"><X size={14} /></button></div> : null}

        <div className="city-picker-scrollbar flex-1 overflow-y-auto px-5 py-6 md:px-8">
          {loadingConversation ? <div className="mx-auto max-w-xl py-12 text-center text-sm text-slate-400"><LoaderCircle size={20} className="mx-auto mb-3 animate-spin" />正在加载对话…</div> : null}
          {!loadingConversation && messages.length === 0 ? (
            <div className="mx-auto flex min-h-full max-w-2xl flex-col justify-center pb-10">
              <div className="mb-7 text-center">
                <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-blue-50 to-cyan-50 text-brand"><Bot size={27} strokeWidth={1.7} /></span>
                <h2 className="mt-4 text-2xl font-semibold tracking-tight text-ink">今天想先处理什么？</h2>
                <p className="mt-2 text-sm text-slate-500">可以聊天，也可以搜索岗位/校招公告，管理投递、待办、面试、画像和简历。</p>
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {suggestions.map(({ icon: Icon, label, prompt }) => (
                  <button key={label} onClick={() => void sendMessage(prompt)} disabled={sending} className="group flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3.5 text-left transition hover:border-blue-200 hover:bg-blue-50/50 disabled:opacity-50">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-50 text-slate-500 transition group-hover:bg-white group-hover:text-brand"><Icon size={16} /></span>
                    <span className="text-sm font-medium text-slate-700">{label}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {!loadingConversation ? <div className="mx-auto max-w-3xl space-y-6">
            {messages.map((message, index) => (
              <div key={message.localId ?? message.id} className="space-y-3">
                {index === latestAssistantIndex && operationSteps.length > 0 ? (
                  <OperationTrace steps={operationSteps} running={sending} failed={runFailed} cancelled={runCancelled} />
                ) : null}
                <div className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}>
                  {message.role === "assistant" ? <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-blue-50 text-brand"><Bot size={17} /></span> : null}
                  <div className={`min-w-0 max-w-[88%] rounded-2xl px-4 py-3.5 ${message.role === "user" ? "rounded-br-md bg-[#edf5ff] text-slate-800" : "rounded-bl-md border border-slate-100 bg-white text-slate-700 shadow-[0_4px_16px_-12px_rgba(15,23,42,0.3)]"}`}>
                    {message.role === "assistant" ? (
                      <div className="agent-markdown text-[13px] leading-6">
                        {message.content ? <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" className="font-medium text-brand underline decoration-blue-200 underline-offset-2 hover:decoration-brand">{children}</a> }}>{message.content}</ReactMarkdown> : null}
                        {message.streaming && !message.content ? <span className="inline-flex items-center gap-2 text-slate-400"><LoaderCircle size={14} className="animate-spin" />正在整理信息…</span> : null}
                        {message.streaming && message.content ? <span className="ml-1 inline-block h-4 w-1 animate-pulse rounded-full bg-brand align-middle" /> : null}
                        {message.incomplete ? <p className="mt-2 border-t border-amber-100 pt-2 text-xs text-amber-700">{message.structured_content?.interrupted === true ? "已停止生成，当前内容已保留；可以修改输入后继续。" : "本轮回答未完整生成。"}</p> : null}
                        {(message.linkPreviews ?? getLinkPreviews(message.structured_content)).map((preview) => (
                          <JobLinkPreviewCard
                            key={preview.preview_token}
                            preview={preview}
                            disabled={sending || hasPendingActions}
                            onRequestSave={(overrides) => {
                              const correction = Object.keys(overrides).length ? `字段覆盖 JSON：${JSON.stringify(overrides)}` : "字段保持原提取结果";
                              setDraft(`请将刚才解析的「${preview.job.title} · ${preview.job.company_name}」加入岗位管理，并先展示待确认卡片，不要直接保存。${correction}`);
                              textareaRef.current?.focus();
                            }}
                          />
                        ))}
                      </div>
                    ) : <p className="whitespace-pre-wrap text-[13px] leading-6">{message.content}</p>}
                    <div className={`mt-2 text-[10px] ${message.role === "user" ? "text-slate-400" : "text-slate-300"}`}>{formatTime(message.created_at)}{index === messages.length - 1 && message.streaming ? " · 正在生成" : ""}</div>
                  </div>
                  {message.role === "user" ? <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-500"><UserRound size={16} /></span> : null}
                </div>
              </div>
            ))}

            {latestAssistantIndex < 0 && operationSteps.length > 0 ? (
              <OperationTrace steps={operationSteps} running={sending} failed={runFailed} cancelled={runCancelled} />
            ) : null}

            {pendingActions.map((event) => <ActionCard key={event.id} event={event} busy={resolvingAction === event.id} onResolve={(confirm) => void resolveAction(event, confirm)} />)}
            <div ref={bottomRef} />
          </div> : null}
        </div>

        <div className="border-t border-slate-100 bg-white px-4 py-4 md:px-7">
          {hasPendingActions ? (
            <div role="status" aria-live="polite" className="mx-auto mb-3 flex max-w-3xl items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50/80 px-3.5 py-3 text-xs leading-5 text-amber-900">
              <Pencil size={15} className="mt-0.5 shrink-0 text-amber-700" />
              <span><strong className="font-semibold">本轮已暂停，等待确认。</strong> 当前有 {pendingActions.length} 项操作待处理。请在上方确认或取消；处理结果会交还给 Agent，随后继续生成回答。</span>
            </div>
          ) : null}
          <div className="mx-auto max-w-3xl rounded-2xl border border-slate-200 bg-white shadow-[0_8px_28px_-20px_rgba(15,23,42,0.3)] transition focus-within:border-blue-300 focus-within:shadow-[0_8px_30px_-18px_rgba(37,99,235,0.25)]">
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onComposerKeyDown}
              rows={2}
              disabled={hasPendingActions}
              placeholder={hasPendingActions ? "请先处理上方待确认操作，再继续对话…" : sending ? "当前回答生成中，可以先编辑下一条问题…" : "问岗位、投递进度、求职画像，或直接聊聊…"}
              className="max-h-40 min-h-[58px] w-full resize-y bg-transparent px-4 pt-3.5 text-sm leading-6 text-slate-700 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:text-slate-400"
            />
            <div className="flex items-center justify-between px-3 pb-2.5">
              <span className="pl-1 text-[10px] text-slate-400">{hasPendingActions ? "确认或取消待处理操作后，输入框会重新启用" : sending ? "可先编辑下一条；停止后发送" : "Enter 发送 · Shift + Enter 换行"}</span>
              {sending ? (
                <button onClick={() => void requestStop()} disabled={!activeRunId || stopping} className="inline-flex items-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-xs font-semibold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50">
                  {stopping ? <LoaderCircle size={14} className="animate-spin" /> : <Square size={13} fill="currentColor" />} {stopping ? "正在停止…" : activeRunId ? "停止生成" : "准备中…"}
                </button>
              ) : (
                <button onClick={() => void sendMessage()} disabled={!draft.trim() || hasPendingActions} className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-slate-300">
                  {hasPendingActions ? <Pencil size={14} /> : <Send size={14} />} {hasPendingActions ? "等待确认" : "发送"}
                </button>
              )}
            </div>
          </div>
          <p className="mx-auto mt-2 max-w-3xl text-center text-[10px] text-slate-400">Agent 可能出错；岗位来源和关键信息请以原始招聘页面为准。</p>
        </div>
      </div>
    </section>
  );
}

function JobLinkPreviewCard({ preview, disabled, onRequestSave }: {
  preview: JobLinkPreview;
  disabled: boolean;
  onRequestSave: (overrides: Record<string, string | number | null>) => void;
}) {
  const { job } = preview;
  const [descriptionDraft, setDescriptionDraft] = useState(job.description ?? "");
  const description = descriptionDraft.trim();
  const requirementText = job.requirements?.trim();
  const [title, setTitle] = useState(job.title);
  const [companyName, setCompanyName] = useState(job.company_name);
  const [city, setCity] = useState(job.city);
  const [jobType, setJobType] = useState(job.job_type ?? "");
  const [publishedDate, setPublishedDate] = useState(job.published_date ?? "");
  const [salaryMin, setSalaryMin] = useState(job.salary?.min == null ? "" : String(job.salary.min));
  const [salaryMax, setSalaryMax] = useState(job.salary?.max == null ? "" : String(job.salary.max));
  const [salaryUnit, setSalaryUnit] = useState(job.salary?.unit ?? "");
  const originalSalaryMin = job.salary?.min == null ? "" : String(job.salary.min);
  const originalSalaryMax = job.salary?.max == null ? "" : String(job.salary.max);
  const salaryWasEdited = salaryMin !== originalSalaryMin || salaryMax !== originalSalaryMax || salaryUnit !== (job.salary?.unit ?? "");
  const salaryDisplay = salaryMin || salaryMax
    ? `${salaryMin || salaryMax}${salaryMin && salaryMax ? "–" : ""}${salaryMax}${salaryUnit ? ` ${salaryUnit}` : ""}`
    : salaryWasEdited ? "薪资未说明" : job.salary?.display || "薪资未说明";

  function submitWithCorrections() {
    const overrides: Record<string, string | number | null> = {};
    if (title.trim() !== job.title) overrides.title = title.trim();
    if (companyName.trim() !== job.company_name) overrides.company_name = companyName.trim();
    if (city.trim() !== job.city) overrides.city = city.trim();
    if (jobType.trim() && jobType.trim() !== (job.job_type ?? "")) overrides.job_type = jobType.trim();
    if (publishedDate !== (job.published_date ?? "")) overrides.published_date = publishedDate || null;
    if (salaryMin !== originalSalaryMin) overrides.salary_min = salaryMin ? Number(salaryMin) : null;
    if (salaryMax !== originalSalaryMax) overrides.salary_max = salaryMax ? Number(salaryMax) : null;
    if (salaryUnit !== (job.salary?.unit ?? "")) overrides.salary_unit = salaryUnit || null;
    if (salaryWasEdited) overrides.salary_status = salaryMin || salaryMax ? "disclosed" : "unknown";
    if (descriptionDraft !== (job.description ?? "")) overrides.description = descriptionDraft || null;
    onRequestSave(overrides);
  }

  const inputClass = "min-w-0 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs text-slate-700 outline-none transition focus:border-blue-300 focus:ring-2 focus:ring-blue-50";
  return (
    <section className="mt-3 overflow-hidden rounded-xl border border-blue-100 bg-[linear-gradient(135deg,#f7fbff_0%,#ffffff_72%)] text-left shadow-[0_8px_24px_-20px_rgba(37,99,235,0.45)]">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-blue-50 px-4 py-3">
        <div className="flex items-center gap-2 text-[11px] font-semibold text-brand">
          <FileText size={14} /> 岗位链接提取预览
        </div>
        <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-[10px] font-medium text-emerald-700">仅预览 · 尚未保存</span>
      </div>
      <div className="space-y-3 px-4 py-3.5">
        <div>
          <h3 className="text-sm font-semibold leading-5 text-ink">{title || "岗位名称待补充"}</h3>
          <p className="mt-1 text-xs text-slate-500">{companyName || "公司待补充"}</p>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-slate-600">
          <span className="inline-flex items-center gap-1.5"><MapPin size={13} className="text-slate-400" />{city || "地点待补充"}</span>
          <span className="inline-flex items-center gap-1.5"><CalendarDays size={13} className="text-slate-400" />{publishedDate || "发布日期未说明"}</span>
          <span>{salaryDisplay}</span>
          {jobType ? <span>{jobType}</span> : null}
        </div>
        {description ? <p className="max-h-16 overflow-hidden text-xs leading-5 text-slate-500">{description}</p> : null}
        {requirementText ? <p className="max-h-12 overflow-hidden text-xs leading-5 text-slate-500"><span className="font-medium text-slate-600">要求：</span>{requirementText}</p> : null}
        {preview.warnings.length ? (
          <div className="space-y-1 rounded-lg border border-amber-100 bg-amber-50/70 px-3 py-2 text-[10px] leading-4 text-amber-800">
            {preview.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </div>
        ) : null}
        <details className="rounded-lg border border-slate-100 bg-white/80">
          <summary className="cursor-pointer px-3 py-2 text-[11px] font-medium text-slate-600">校对或修改提取字段</summary>
          <div className="grid grid-cols-1 gap-2 border-t border-slate-100 p-3 sm:grid-cols-2">
            <label className="grid gap-1 text-[10px] text-slate-500">岗位名称<input className={inputClass} value={title} onChange={(event) => setTitle(event.target.value)} /></label>
            <label className="grid gap-1 text-[10px] text-slate-500">公司<input className={inputClass} value={companyName} onChange={(event) => setCompanyName(event.target.value)} /></label>
            <label className="grid gap-1 text-[10px] text-slate-500">城市<input className={inputClass} value={city} onChange={(event) => setCity(event.target.value)} /></label>
            <label className="grid gap-1 text-[10px] text-slate-500">实习类型<input className={inputClass} value={jobType} onChange={(event) => setJobType(event.target.value)} /></label>
            <label className="grid gap-1 text-[10px] text-slate-500">发布日期<input className={inputClass} type="date" value={publishedDate} onChange={(event) => setPublishedDate(event.target.value)} /></label>
            <div className="grid grid-cols-3 gap-2">
              <label className="grid gap-1 text-[10px] text-slate-500">薪资下限<input className={inputClass} type="number" min="0" value={salaryMin} onChange={(event) => setSalaryMin(event.target.value)} /></label>
              <label className="grid gap-1 text-[10px] text-slate-500">薪资上限<input className={inputClass} type="number" min="0" value={salaryMax} onChange={(event) => setSalaryMax(event.target.value)} /></label>
              <label className="grid gap-1 text-[10px] text-slate-500">单位<input className={inputClass} placeholder="元/天" value={salaryUnit} onChange={(event) => setSalaryUnit(event.target.value)} /></label>
            </div>
            <label className="grid gap-1 text-[10px] text-slate-500 sm:col-span-2">岗位描述<textarea className={`${inputClass} min-h-16 resize-y`} maxLength={10000} value={descriptionDraft} onChange={(event) => setDescriptionDraft(event.target.value)} /></label>
          </div>
        </details>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3">
          <a href={job.detail_url} target="_blank" rel="noreferrer" className="inline-flex min-w-0 items-center gap-1.5 text-[10px] font-medium text-brand hover:underline">
            <ExternalLink size={12} /> <span className="max-w-[300px] truncate">查看原始招聘页面</span>
          </a>
          <button type="button" onClick={submitWithCorrections} disabled={disabled || !title.trim() || !companyName.trim()} className="inline-flex items-center gap-1.5 rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-[11px] font-semibold text-brand transition hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50">
            <BookmarkPlus size={13} /> 继续申请收藏
          </button>
        </div>
        <p className="text-[10px] text-slate-400">岗位名称和公司为保存必填；城市未知时可留空。字段修正会带入对话，Agent 仍会先展示确认卡片。</p>
      </div>
    </section>
  );
}

function ActionCard({ event, busy, onResolve }: { event: AgentRunEvent; busy: boolean; onResolve: (confirm: boolean) => void }) {
  const payload = event.payload ?? {};
  const preview = payload.preview && typeof payload.preview === "object" ? payload.preview as Record<string, unknown> : {};
  return (
    <div className="ml-11 max-w-2xl rounded-2xl border border-amber-200 bg-[#fffdf7] p-4 shadow-[0_8px_26px_-20px_rgba(180,83,9,0.5)]">
      <div className="flex items-start gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-700"><Pencil size={15} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-800">操作确认</p>
          <p className="mt-1 text-xs leading-5 text-slate-600">{String(payload.summary ?? "Agent 请求修改本地数据")}</p>
          <dl className="mt-3 space-y-1.5">
            {Object.entries(preview).map(([label, value]) => (
              <div key={label} className="grid grid-cols-[72px_minmax(0,1fr)] gap-2 text-xs leading-5">
                <dt className="text-slate-400">{label}</dt>
                <dd className="break-words text-slate-700">{Array.isArray(value) ? value.join("、") : String(value ?? "—")}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-[11px] text-amber-700">确认后才会写入；取消不会修改数据。</p>
          <div className="mt-3 flex gap-2">
            <button onClick={() => onResolve(true)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-2 text-xs font-semibold text-white transition hover:bg-blue-600 disabled:opacity-50">{busy ? <LoaderCircle size={13} className="animate-spin" /> : <Check size={13} />} 确认操作</button>
            <button onClick={() => onResolve(false)} disabled={busy} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"><X size={13} /> 取消</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function formatShortDate(value: string) {
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit" }).format(date);
}

function formatTime(value: string) {
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date);
}
