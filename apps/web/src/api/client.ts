import axios from "axios";
import { fetchEventSource } from "@microsoft/fetch-event-source";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8100/api/v1";
export const LLM_REQUEST_TIMEOUT_MS = 130_000;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
});

export type PublishedRange = "all" | "1d" | "3d" | "7d" | "30d";
export type SalaryMode = "any" | "disclosed_only" | "minimum";

export interface JobSearchRequest {
  keyword?: string;
  company?: string;
  city?: string;
  cities?: string[];
  published_range: PublishedRange;
  salary_mode: SalaryMode;
  salary_min?: number;
  internship_type?: string;
  education?: string;
  internship_months?: number;
  days_per_week?: number;
  conversion_chance?: string;
  sort_by?: "recommended" | "newest";
  page: number;
  limit: number;
  providers?: string[];
}

export interface SalaryInfo {
  min: number | null;
  max: number | null;
  unit: string | null;
  status: string;
  display: string;
}

export interface JobSource {
  name: string;
  provider: string;
  quality_status: string;
  source_type: string;
  authorization_mode: string;
  terms_url: string | null;
}

export interface MatchSummary {
  id: number;
  summary: string;
  match_score: number;
  recommendation: string;
  matched_points: string[];
  missing_points: string[];
  risk_points: string[];
  next_actions: string[];
  analysis_mode: string;
  created_at: string;
}

export interface JobSummary {
  id: number | null;
  result_token: string | null;
  title: string;
  company_name: string;
  city: string;
  district: string | null;
  job_type: string;
  published_date: string | null;
  salary: SalaryInfo;
  education: string | null;
  internship_months: number | null;
  days_per_week: number | null;
  conversion_chance: string | null;
  detail_url: string;
  source: JobSource;
  extraction_method: string;
  is_saved: boolean;
  application: null;
  latest_match: MatchSummary | null;
  recommendation: JobRecommendation | null;
}

export interface JobRecommendation {
  score: number | null;
  label: string;
  matched_points: string[];
  missing_points: string[];
  unknown_points: string[];
  feedback: "interested" | "not_interested" | null;
}

export interface JobDetail extends JobSummary {
  description: string | null;
  requirements: string | null;
  responsibilities: string | null;
  snapshot_fetched_at: string | null;
}

export interface ProviderQuality {
  provider: string;
  status: string;
  count: number;
  error: string | null;
}

export interface OfferXianshengStatus {
  provider: "offer_xiansheng";
  configured: boolean;
  status: "configured" | "not_configured" | "unavailable";
  message: string;
}

export interface CampusRecruitSearchRequest {
  keyword?: string;
  company?: string;
  position_name?: string;
  function_name?: string;
  industry?: string;
  cities?: string[];
  graduation_year?: number;
  education_level?: string;
  company_nature?: string;
  recruitment_batch?: string;
  start_time?: string;
  end_time?: string;
  cursor?: string;
  limit: number;
}

export interface CampusRecruitNotice {
  id: string;
  recruit_info_name: string | null;
  company_name: string | null;
  graduation_year: number | null;
  recruitment_batch: string | null;
  industry: string | null;
  company_nature: string | null;
  application_start_date: string | null;
  application_end_date: string | null;
  test_time: string | null;
  publicity_time: string | null;
  interview_start_time: string | null;
  interview_end_time: string | null;
  domestic_graduation_date: string | null;
  domestic_graduation_time: string | null;
  overseas_graduation_date: string | null;
  overseas_graduation_time: string | null;
  domestic_education: string | null;
  overseas_education: string | null;
  position_categories: string[];
  cities: string[];
  content: string | null;
  application_url: string | null;
  announcement_url: string | null;
  release_source: string | null;
  updated_at: string | null;
}

export interface CampusRecruitSearchResponse {
  items: CampusRecruitNotice[];
  count: number;
  limit: number;
  next_cursor: string | null;
  has_more: boolean;
  source: { provider: "offer_xiansheng"; name: string; data_type: "campus_recruit_notice" };
}

export interface SearchQuality {
  undisclosed_salary_count: number;
  missing_published_date_count: number;
  providers: ProviderQuality[];
}

export interface JobSearchResponse {
  items: JobSummary[];
  total: number;
  page: number;
  limit: number;
  quality: SearchQuality;
  recommendation_context: {
    sort_by: "recommended" | "newest";
    personalized: boolean;
    profile_used: boolean;
    resume_used: boolean;
    message: string;
  };
}

export interface RecommendationFeedbackResponse {
  result_token: string;
  feedback: "interested" | "not_interested" | null;
  message: string;
}

export type SubscriptionFrequency = "manual" | "daily" | "weekdays" | "weekly" | "interval" | "monthly";
export type SubscriptionRunStatus = "running" | "succeeded" | "no_new" | "partial_failed" | "failed" | "interrupted";

export interface SubscriptionProviderResult {
  provider: string;
  status: string;
  count: number;
  error: string | null;
}

export interface SubscriptionRunSummary {
  id: number;
  subscription_id: number;
  trigger: "manual" | "scheduled";
  status: SubscriptionRunStatus;
  total_count: number;
  new_count: number;
  provider_results: SubscriptionProviderResult[];
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface JobSubscription {
  id: number;
  name: string;
  filters: Partial<JobSearchRequest>;
  frequency: SubscriptionFrequency;
  schedule_time: string;
  weekday: number | null;
  interval_days: number | null;
  month_day: number | null;
  timezone: string;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  created_at: string;
  updated_at: string;
  latest_run: SubscriptionRunSummary | null;
}

export interface SubscriptionJobPreview {
  source_job_id: string;
  title: string;
  company_name: string;
  city: string;
  district: string | null;
  job_type: string;
  published_date: string | null;
  salary: SalaryInfo;
  education: string | null;
  internship_months: number | null;
  days_per_week: number | null;
  conversion_chance: string | null;
  detail_url: string;
  description: string | null;
  requirements: string | null;
  responsibilities: string | null;
  extraction_method: string;
  source: JobSource;
}

export interface SubscriptionRunItem {
  id: number;
  provider: string;
  is_new: boolean;
  job: SubscriptionJobPreview;
  saved_job_id: number | null;
}

export interface SubscriptionRunDetail extends SubscriptionRunSummary {
  items: SubscriptionRunItem[];
  total_items: number;
  page: number;
  limit: number;
  preview_expired: boolean;
}

export interface SubscriptionSaveResponse {
  item_id: number;
  job_id: number;
  application_id: number;
  already_saved: boolean;
}

export interface BossProviderStatus {
  provider: "boss_agent_cli";
  installed: boolean;
  authenticated: boolean;
  status: "available" | "login_required" | "browser_session_missing" | "not_installed" | "incompatible" | "waiting_user" | "starting" | "failed" | "succeeded" | "canceled";
  message: string;
  active_login_id: string | null;
  can_start: boolean;
}

export interface BossLoginStartResponse {
  run_id: string;
  status: string;
  message: string;
  started_at: string;
  ended_at: string | null;
  reused: boolean;
}

export interface BossLoginEvent {
  sequence: number;
  type: "started" | "progress" | "succeeded" | "failed" | "canceled";
  status: string;
  message: string;
  timestamp: string;
}

export interface StatusDefinition {
  id: number;
  name: string;
  color: string | null;
  sort_order: number;
  is_success: boolean;
  is_terminal: boolean;
  enabled: boolean;
}

export interface ApplicationSummary {
  id: number;
  job: {
    id: number;
    title: string;
    company_name: string;
    city: string;
    published_date: string | null;
    detail_url: string;
  };
  current_status: StatusDefinition;
  saved_at: string;
  last_status_changed_at: string | null;
  note: string | null;
  latest_match: MatchSummary | null;
}

export interface StatusEvent {
  id: number;
  from_status: StatusDefinition | null;
  to_status: StatusDefinition;
  effective_at: string;
  note: string | null;
  created_at: string;
}

export interface ApplicationDetail extends ApplicationSummary {
  timeline: StatusEvent[];
}

export interface ApplicationListResponse {
  items: ApplicationSummary[];
  total: number;
  page: number;
  limit: number;
}

export interface WorkbenchApplicationRef {
  id: number;
  job_id: number;
  title: string;
  company_name: string;
  city: string;
}

export type TodoPriority = "high" | "normal" | "low";
export type InterviewFormat = "online" | "in_person" | "phone" | "unknown";

export interface WorkbenchTodo {
  id: number;
  title: string;
  application: WorkbenchApplicationRef | null;
  due_at: string | null;
  priority: TodoPriority;
  completed: boolean;
  completed_at: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkbenchTodoListResponse {
  items: WorkbenchTodo[];
  total: number;
  page: number;
  limit: number;
}

export interface WorkbenchInterview {
  id: number;
  title: string;
  application: WorkbenchApplicationRef | null;
  company_name: string | null;
  position_title: string | null;
  starts_at: string;
  ends_at: string | null;
  timezone: string;
  interview_format: InterviewFormat;
  location: string | null;
  meeting_url: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkbenchInterviewListResponse {
  items: WorkbenchInterview[];
  total: number;
}

export interface WorkbenchOverview {
  generated_at: string;
  application_count: number;
  todo_open_count: number;
  todo_overdue_count: number;
  todo_completed_count: number;
  interview_upcoming_count: number;
  interview_next_7_days_count: number;
  status_counts: Array<StatusDefinition & { count: number }>;
  weekly_status_events: Array<{ week_start: string; count: number }>;
}

export interface ProfileFact {
  id: number;
  fact_type: string;
  fact_key: string;
  fact_value: string;
  status: "active" | "superseded" | "temporary" | "deleted";
  source: string;
  confidence: number | null;
  confirmed_at: string | null;
  valid_from: string | null;
  valid_to: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResumeVersion {
  id: number;
  title: string;
  is_current: boolean;
  created_at: string;
  updated_at: string;
  text_preview: string;
  has_content: boolean;
  source_attachment_id: number | null;
}

export interface ResumeBasics {
  full_name: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
  school: string | null;
  major: string | null;
  education: string | null;
  graduation_year: number | null;
}

export interface ResumeJobIntent {
  target_positions: string[];
  target_cities: string[];
  internship_type: string | null;
  availability: string | null;
  days_per_week: number | null;
  expected_salary: string | null;
}

export interface ResumeEducationEntry {
  school: string | null;
  degree: string | null;
  major: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
}

export interface ResumeExperienceEntry {
  organization: string | null;
  role: string | null;
  experience_type: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
  achievements: string[];
  skills: string[];
}

export interface ResumeProjectEntry {
  name: string | null;
  role: string | null;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
  highlights: string[];
  technologies: string[];
}

export interface ResumeStructuredContent {
  basics: ResumeBasics;
  job_intent: ResumeJobIntent;
  education: ResumeEducationEntry[];
  campus_experiences: ResumeExperienceEntry[];
  experience: ResumeExperienceEntry[];
  projects: ResumeProjectEntry[];
  skills: string[];
  certificates: string[];
  summary: string | null;
}

export interface ResumeDetail extends ResumeVersion {
  raw_text: string;
  structured_content: ResumeStructuredContent | null;
}

export interface ResumeAttachment {
  id: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  parse_status: "pending_review" | "confirmed";
  created_at: string;
  linked_resume_version_id: number | null;
  draft_content: ResumeStructuredContent | null;
}

export interface CandidateProfile {
  id: number;
  school: string | null;
  major: string | null;
  education: string | null;
  graduation_year: number | null;
  target_directions: string[];
  target_cities: string[];
  available_period: string | null;
  days_per_week: number | null;
  internship_months: number | null;
  desired_industries: string[];
  resumes: ResumeVersion[];
  active_facts: ProfileFact[];
}

export interface AgentMessage {
  id: number;
  role: "user" | "assistant";
  content: string | null;
  structured_content: Record<string, unknown> | null;
  created_at: string;
}

export interface AgentSession {
  id: number;
  title: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface AgentRunEvent {
  id: number;
  run_id: string;
  sequence: number;
  event_type: string;
  name: string | null;
  status: string;
  payload: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentSessionDetail extends AgentSession {
  messages: AgentMessage[];
  events: AgentRunEvent[];
}

export interface AgentStreamEvent {
  id?: number;
  run_id?: string;
  sequence?: number;
  type: string;
  name?: string | null;
  status?: string;
  payload?: Record<string, unknown> | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export async function listAgentSessions() {
  return (await apiClient.get<AgentSession[]>("/agent/sessions")).data;
}

export async function createAgentSession(title?: string) {
  return (await apiClient.post<AgentSession>("/agent/sessions", { title })).data;
}

export async function getAgentSession(sessionId: number) {
  return (await apiClient.get<AgentSessionDetail>(`/agent/sessions/${sessionId}`)).data;
}

export async function renameAgentSession(sessionId: number, title: string) {
  return (await apiClient.patch<AgentSession>(`/agent/sessions/${sessionId}`, { title })).data;
}

export async function resolveAgentAction(eventId: number, confirm: boolean) {
  return (await apiClient.post<{ proposal_id: number; status: string; message: string }>(
    `/agent/actions/${eventId}/resolve`,
    { confirm },
  )).data;
}

export async function cancelAgentRun(sessionId: number, runId: string) {
  return (await apiClient.post<{ status: string; message: string }>(
    `/agent/sessions/${sessionId}/runs/${runId}/cancel`,
  )).data;
}

export function streamAgentChat(
  body: { message: string; session_id: number; search_providers?: string[] },
  signal: AbortSignal,
  onEvent: (event: AgentStreamEvent) => void,
) {
  return fetchEventSource(`${API_BASE_URL}/agent/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
    openWhenHidden: true,
    async onopen(response) {
      if (!response.ok) {
        let message = `Agent 请求失败（${response.status}）`;
        try {
          const body = await response.json() as { detail?: { message?: unknown } };
          if (typeof body.detail?.message === "string") message = body.detail.message;
        } catch {
          // Keep the status-based message when the server did not return JSON.
        }
        throw new Error(message);
      }
      if (!response.headers.get("content-type")?.includes("text/event-stream")) {
        throw new Error("服务端没有返回 SSE 流");
      }
    },
    onmessage(message) {
      try {
        const parsed = JSON.parse(message.data) as AgentStreamEvent;
        onEvent({ ...parsed, type: message.event || parsed.type });
      } catch {
        onEvent({ type: "stream_error", error_message: "收到无法解析的服务端事件。" });
      }
    },
    onerror(error) {
      throw error;
    },
  });
}
