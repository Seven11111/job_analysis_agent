import { useCallback, useEffect, useId, useRef, useState, type ChangeEvent, type ClipboardEvent, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import {
  Download,
  Pencil,
  FileText,
  Plus,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";

import {
  API_BASE_URL,
  LLM_REQUEST_TIMEOUT_MS,
  apiClient,
  type CandidateProfile,
  type ProfileFact,
  type ResumeAttachment,
  type ResumeDetail,
  type ResumeEducationEntry,
  type ResumeExperienceEntry,
  type ResumeProjectEntry,
  type ResumeStructuredContent,
  type ResumeVersion,
} from "../api/client";
import { cityGroups, quickCityOptions } from "../data/job-search-cities";

const emptyProfile: CandidateProfile = {
  id: 0,
  school: null,
  major: null,
  education: null,
  graduation_year: null,
  target_directions: [],
  target_cities: [],
  available_period: null,
  days_per_week: null,
  internship_months: null,
  desired_industries: [],
  resumes: [],
  active_facts: [],
};

const emptyResume: ResumeStructuredContent = {
  basics: { full_name: null, phone: null, email: null, city: null, school: null, major: null, education: null, graduation_year: null },
  job_intent: { target_positions: [], target_cities: [], internship_type: null, availability: null, days_per_week: null, expected_salary: null },
  education: [],
  campus_experiences: [],
  experience: [],
  projects: [],
  skills: [],
  certificates: [],
  summary: null,
};

const targetPositionSuggestions = ["后端开发", "前端开发", "AI 应用", "算法工程师", "数据分析", "数据开发", "测试开发", "客户端开发", "运维开发", "产品技术"];
const targetCitySuggestions = [...new Set([...quickCityOptions, ...cityGroups.flatMap((group) => group.cities)])];

interface ResumeEditorState {
  mode: "attachment" | "version";
  sectionKey: ResumeSectionKey | null;
  attachmentId: number | null;
  sourceAttachmentId: number | null;
  title: string;
  rawText: string;
  structuredContent: ResumeStructuredContent;
  setCurrent: boolean;
}

type ResumeSectionKey = "basics" | "job_intent" | "education" | "campus_experiences" | "experience" | "projects" | "skills" | "summary";

export function ProfilePage() {
  const [profile, setProfile] = useState<CandidateProfile>(emptyProfile);
  const [currentResume, setCurrentResume] = useState<ResumeDetail | null>(null);
  const [facts, setFacts] = useState<ProfileFact[]>([]);
  const [attachments, setAttachments] = useState<ResumeAttachment[]>([]);
  const [factValue, setFactValue] = useState("");
  const [manualResumeTitle, setManualResumeTitle] = useState("");
  const [manualResumeText, setManualResumeText] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [consentToModel, setConsentToModel] = useState(false);
  const [editor, setEditor] = useState<ResumeEditorState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [profileResponse, factsResponse, attachmentsResponse] = await Promise.all([
        apiClient.get<CandidateProfile>("/profile"),
        apiClient.get<ProfileFact[]>("/profile/facts", { params: { status: "active" } }),
        apiClient.get<ResumeAttachment[]>("/profile/resume-attachments"),
      ]);
      const profileData = profileResponse.data;
      const currentVersion = profileData.resumes.find((resume) => resume.is_current) ?? profileData.resumes[0];
      let currentDetail: ResumeDetail | null = null;
      if (currentVersion) {
        try {
          const detailResponse = await apiClient.get<ResumeDetail>(`/profile/resumes/${currentVersion.id}`);
          currentDetail = detailResponse.data;
        } catch {
          currentDetail = null;
        }
      }
      setProfile(profileData);
      setCurrentResume(currentDetail ? {
        ...currentDetail,
        structured_content: normalizeResumeContent(currentDetail.structured_content),
      } : null);
      setFacts(factsResponse.data);
      setAttachments(attachmentsResponse.data);
    } catch {
      setError("个人画像加载失败，请确认后端服务正在运行。" );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const response = await apiClient.put<CandidateProfile>("/profile", profile);
      setProfile(response.data);
      setMessage("求职偏好已保存。简历内容与搜索偏好分开管理。");
    } catch {
      setError("画像保存失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function addFact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!factValue.trim()) return;
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await apiClient.post("/profile/facts", {
        fact_type: "skill",
        fact_key: `skill-${Date.now()}`,
        fact_value: factValue,
        confirmed: true,
      });
      setFactValue("");
      await load();
      setMessage("已添加一条已确认画像事实。");
    } catch {
      setError("画像事实保存失败。");
    } finally {
      setSaving(false);
    }
  }

  async function deleteFact(factId: number) {
    setSaving(true);
    setError(null);
    try {
      await apiClient.delete(`/profile/facts/${factId}`);
      setFacts((current) => current.filter((fact) => fact.id !== factId));
      setProfile((current) => ({ ...current, active_facts: current.active_facts.filter((fact) => fact.id !== factId) }));
    } catch {
      setError("画像事实删除失败。");
    } finally {
      setSaving(false);
    }
  }

  async function uploadAndParse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile || !consentToModel) return;
    setParsing(true);
    setMessage(null);
    setError(null);
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("consent_to_model", "true");
    try {
      const response = await apiClient.post<ResumeAttachment>("/profile/resume-attachments/parse", form, {
        timeout: LLM_REQUEST_TIMEOUT_MS,
      });
      setAttachments((current) => [response.data, ...current]);
      openAttachmentDraft(response.data);
      setSelectedFile(null);
      setConsentToModel(false);
      if (fileInput.current) fileInput.current.value = "";
      setMessage("解析完成。请检查并修改草稿，确认后才会保存为在线简历。");
    } catch (requestError) {
      setError(readApiError(requestError, "简历解析失败，请检查模型配置或更换文件后重试。"));
    } finally {
      setParsing(false);
    }
  }

  function openAttachmentDraft(attachment: ResumeAttachment) {
    if (!attachment.draft_content) {
      setError("这份附件没有待确认的解析草稿，请重新上传解析。");
      return;
    }
    setEditor({
      mode: "attachment",
      sectionKey: null,
      attachmentId: attachment.id,
      sourceAttachmentId: attachment.id,
      title: attachment.original_filename.replace(/\.(pdf|docx)$/i, ""),
      rawText: "",
      structuredContent: structuredClone(attachment.draft_content),
      setCurrent: true,
    });
  }

  function startNewOnlineResume() {
    setError(null);
    setEditor({
      mode: "version",
      sectionKey: null,
      attachmentId: null,
      sourceAttachmentId: null,
      title: "我的实习简历",
      rawText: "",
      structuredContent: structuredClone(emptyResume),
      setCurrent: true,
    });
  }

  async function editResumeAsNewVersion(resume: ResumeVersion) {
    setSaving(true);
    setError(null);
    try {
      const response = await apiClient.get<ResumeDetail>(`/profile/resumes/${resume.id}`);
      const detail = response.data;
      setEditor({
        mode: "version",
        sectionKey: null,
        attachmentId: null,
        sourceAttachmentId: detail.source_attachment_id,
        title: detail.title,
        rawText: detail.raw_text,
        structuredContent: normalizeResumeContent(detail.structured_content),
        setCurrent: true,
      });
    } catch {
      setError("在线简历读取失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  async function saveOnlineResume(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || !editor.title.trim()) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      if (editor.mode === "attachment" && editor.attachmentId !== null) {
        await apiClient.post(`/profile/resume-attachments/${editor.attachmentId}/confirm`, {
          title: editor.title,
          structured_content: editor.structuredContent,
          set_current: editor.setCurrent,
        });
      } else {
        await apiClient.post("/profile/resumes", {
          title: editor.title,
          raw_text: editor.sectionKey ? buildResumeText(editor.structuredContent) : editor.rawText.trim() || buildResumeText(editor.structuredContent),
          structured_content: editor.structuredContent,
          set_current: editor.setCurrent,
          source_attachment_id: editor.sourceAttachmentId,
        });
      }
      setEditor(null);
      await load();
      setMessage("简历已保存。已有岗位分析仍保留生成时使用的简历依据。");
    } catch (requestError) {
      setError(readApiError(requestError, "简历保存失败，请检查必填信息后重试。"));
    } finally {
      setSaving(false);
    }
  }

  function editResumeSection(sectionKey: ResumeSectionKey) {
    if (!currentResume) return;
    setError(null);
    setEditor({
      mode: "version",
      sectionKey,
      attachmentId: null,
      sourceAttachmentId: currentResume.source_attachment_id,
      title: currentResume.title,
      rawText: currentResume.raw_text,
      structuredContent: structuredClone(normalizeResumeContent(currentResume.structured_content)),
      setCurrent: true,
    });
  }

  async function addManualResume(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!manualResumeTitle.trim() || !manualResumeText.trim()) return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.post("/profile/resumes", {
        title: manualResumeTitle,
        raw_text: manualResumeText,
        set_current: true,
      });
      setManualResumeTitle("");
      setManualResumeText("");
      await load();
      setMessage("在线简历已保存。");
    } catch {
      setError("简历保存失败。");
    } finally {
      setSaving(false);
    }
  }

  async function selectResume(resumeId: number) {
    setSaving(true);
    setError(null);
    try {
      await apiClient.post(`/profile/resumes/${resumeId}/select`);
      await load();
      setMessage("当前简历已切换。");
    } catch {
      setError("简历切换失败。");
    } finally {
      setSaving(false);
    }
  }

  async function deleteAttachment(attachment: ResumeAttachment) {
    if (!window.confirm(`删除附件“${attachment.original_filename}”？已确认的在线简历不会受影响。`)) return;
    setSaving(true);
    setError(null);
    try {
      await apiClient.delete(`/profile/resume-attachments/${attachment.id}`);
      setAttachments((current) => current.filter((item) => item.id !== attachment.id));
      if (editor?.attachmentId === attachment.id) setEditor(null);
      setMessage("附件已从本地删除；已确认的在线简历不受影响。");
    } catch {
      setError("附件删除失败，请稍后重试。");
    } finally {
      setSaving(false);
    }
  }

  function update<K extends keyof CandidateProfile>(key: K, value: CandidateProfile[K]) {
    setProfile((current) => ({ ...current, [key]: value }));
  }

  function updateEditor(patch: Partial<ResumeEditorState>) {
    setEditor((current) => current ? { ...current, ...patch } : current);
  }

  if (loading) return <div className="rounded-3xl border border-slate-200 bg-white p-12 text-center text-sm text-slate-500">正在读取个人画像…</div>;

  return (
    <section className="space-y-7 pb-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.28em] text-brand">PROFILE / 03</p>
          <h1 className="mt-2 text-4xl font-semibold tracking-[-0.04em] text-ink">个人画像</h1>
          <p className="mt-2 text-sm text-slate-500">求职偏好、在线简历与原始附件分开管理；解析结果由你确认后才生效。</p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full border border-teal-100 bg-teal-50/70 px-4 py-2 text-xs font-medium text-teal-800">
          <ShieldCheck size={15} /> 简历文件仅保存在本机
        </div>
      </header>

      {error && <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm text-rose-700">{error}</div>}
      {message && <div role="status" className="rounded-2xl border border-teal-200 bg-teal-50 px-5 py-4 text-sm text-teal-800">{message}</div>}

      <form onSubmit={saveProfile} className="rounded-3xl border border-slate-200/90 bg-white p-7 shadow-[0_14px_40px_rgba(24,64,96,0.06)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand">SEARCH PREFERENCES</p><h2 className="mt-2 text-2xl font-semibold text-ink">求职偏好</h2><p className="mt-1 text-sm text-slate-500">用于搜索与推荐；不会因为简历解析而自动改变。</p></div>
          <button disabled={saving} className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-700 disabled:opacity-50"><Save size={16} />保存偏好</button>
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Field label="学校" value={profile.school ?? ""} onChange={(value) => update("school", value)} placeholder="例如：某大学" />
          <Field label="专业" value={profile.major ?? ""} onChange={(value) => update("major", value)} placeholder="例如：计算机科学" />
          <Field label="目标岗位方向" value={profile.target_directions.join("、")} onChange={(value) => update("target_directions", splitValues(value))} placeholder="后端、AI 应用" />
          <Field label="目标城市" value={profile.target_cities.join("、")} onChange={(value) => update("target_cities", splitValues(value))} placeholder="上海、杭州" />
          <Field label="可实习时间" value={profile.available_period ?? ""} onChange={(value) => update("available_period", value)} placeholder="例如：2026 年暑期" />
          <Field label="每周出勤天数" type="number" value={profile.days_per_week?.toString() ?? ""} onChange={(value) => update("days_per_week", value ? Number(value) : null)} placeholder="4" />
          <Field label="实习时长（月）" type="number" value={profile.internship_months?.toString() ?? ""} onChange={(value) => update("internship_months", value ? Number(value) : null)} placeholder="3" />
          <Field label="关注行业" value={profile.desired_industries.join("、")} onChange={(value) => update("desired_industries", splitValues(value))} placeholder="互联网、AI" />
        </div>
      </form>

      <section className="rounded-3xl border border-slate-200/90 bg-white p-7 shadow-[0_14px_40px_rgba(24,64,96,0.05)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand">RESUME WORKSPACE</p><h2 className="mt-2 text-2xl font-semibold text-ink">简历中心</h2><p className="mt-1 text-sm text-slate-500">附件是原始文件，在线简历是可编辑、供岗位分析使用的版本。</p></div>
          <div className="rounded-xl bg-[#f5f8fb] px-4 py-2 text-sm text-slate-600">{attachments.length} 个附件简历</div>
        </div>

        <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.6fr)]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 xl:order-1">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
              <div><h3 className="font-semibold text-ink">在线简历</h3><p className="mt-1 text-xs text-slate-500">按区块维护简历；岗位分析会使用当前保存的内容。</p></div>
              {!currentResume && <button type="button" onClick={startNewOnlineResume} disabled={saving || Boolean(editor)} className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3 py-2 text-xs font-semibold text-white hover:bg-blue-600 disabled:opacity-50"><Plus size={14} />新建在线简历</button>}
            </div>
            {currentResume ? (
              <>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[#f6f9fc] px-4 py-3">
                  <div className="min-w-0"><p className="text-[11px] font-medium text-slate-500">当前在线简历</p><p className="mt-0.5 truncate text-sm font-semibold text-ink">{currentResume.title}</p></div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-500">更新于 {formatTimestamp(currentResume.updated_at)}</span>
                    {!currentResume.is_current && <button type="button" disabled={saving || Boolean(editor)} onClick={() => void selectResume(currentResume.id)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-brand hover:border-brand disabled:opacity-50">设为当前简历</button>}
                  </div>
                </div>
                <ResumePreview resume={currentResume} onEditSection={editResumeSection} onEditFull={() => { const resume = profile.resumes.find((item) => item.id === currentResume.id); if (resume) void editResumeAsNewVersion(resume); }} disabled={saving || Boolean(editor)} />
              </>
            ) : (
              <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-[#fbfcfe] px-6 py-10 text-center">
                <div className="mx-auto grid h-12 w-12 place-items-center rounded-2xl bg-blue-50 text-brand"><FileText size={22} /></div>
                <h4 className="mt-4 font-semibold text-ink">建立你的在线简历</h4>
                <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">可以从空白简历填写，也可以上传附件并检查解析草稿。</p>
                <button type="button" onClick={startNewOnlineResume} disabled={saving || Boolean(editor)} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"><Plus size={16} />从空白简历开始</button>
              </div>
            )}
            {editor?.sectionKey === null && <ResumeEditor editor={editor} onChange={updateEditor} onSubmit={saveOnlineResume} onCancel={() => setEditor(null)} saving={saving} />}
            <details className="mt-5 border-t border-slate-100 pt-4">
              <summary className="cursor-pointer text-sm font-semibold text-brand">从文本整理在线简历</summary>
              <form onSubmit={addManualResume} className="mt-4 space-y-3">
                <input value={manualResumeTitle} onChange={(event) => setManualResumeTitle(event.target.value)} placeholder="简历名称，例如：后端实习简历" className="h-11 w-full rounded-xl border border-slate-200 px-4 text-sm outline-none focus:border-brand" />
                <textarea value={manualResumeText} onChange={(event) => setManualResumeText(event.target.value)} rows={5} placeholder="粘贴简历文本；敏感联系方式仅本地保存，进入岗位分析上下文前会脱敏。" className="w-full resize-y rounded-xl border border-slate-200 p-4 text-sm outline-none focus:border-brand" />
                <button disabled={saving || !manualResumeTitle.trim() || !manualResumeText.trim()} className="inline-flex items-center gap-2 rounded-xl border border-brand px-4 py-2.5 text-sm font-semibold text-brand disabled:opacity-50"><Plus size={15} />保存为在线简历</button>
              </form>
            </details>
          </section>

          <section className="rounded-2xl border border-blue-100 bg-[#f8fbff] p-5 xl:order-2">
            <div className="flex items-center gap-3"><div className="grid h-10 w-10 place-items-center rounded-xl bg-white text-brand shadow-sm"><UploadCloud size={19} /></div><div><h3 className="font-semibold text-ink">附件简历</h3><p className="text-xs text-slate-500">PDF / DOCX · 最大 10 MB</p></div></div>
            <form onSubmit={uploadAndParse} className="mt-5 space-y-4">
              <input ref={fileInput} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)} className="block w-full cursor-pointer rounded-xl border border-dashed border-slate-300 bg-white px-4 py-4 text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-blue-50 file:px-3 file:py-2 file:text-xs file:font-semibold file:text-brand hover:border-brand" />
              {selectedFile && <p className="truncate rounded-lg bg-white px-3 py-2 text-xs text-slate-600">待解析：{selectedFile.name} · {formatBytes(selectedFile.size)}</p>}
              <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50/70 p-3 text-xs leading-5 text-amber-900">
                <input type="checkbox" checked={consentToModel} onChange={(event) => setConsentToModel(event.target.checked)} className="mt-1 accent-amber-600" />
                <span>我同意将脱敏后的简历文字发送给当前配置的模型服务，用于提取教育、经历和技能。未脱敏的原始文件保存在本机。</span>
              </label>
              <button disabled={!selectedFile || !consentToModel || parsing} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-45">
                <Sparkles size={16} />{parsing ? "正在提取并解析…" : "上传并自动解析"}
              </button>
              <p className="text-[11px] leading-5 text-slate-500">扫描版 PDF 暂不支持。解析结果仅作为草稿，不会自动覆盖当前简历或求职偏好。</p>
            </form>

            <div className="mt-6 border-t border-blue-100 pt-5">
              <h4 className="text-sm font-semibold text-ink">本地附件</h4>
              <div className="mt-3 space-y-2">
                {attachments.length === 0 && <p className="rounded-xl bg-white px-4 py-5 text-center text-xs text-slate-500">尚未上传附件简历</p>}
                {attachments.map((attachment) => <AttachmentRow key={attachment.id} attachment={attachment} onOpen={() => openAttachmentDraft(attachment)} onDelete={() => void deleteAttachment(attachment)} />)}
              </div>
            </div>
          </section>

        </div>
      </section>

      {editor?.sectionKey !== null && editor && (
        <div role="presentation" className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[2px]" onMouseDown={(event) => { if (event.target === event.currentTarget) setEditor(null); }}>
          <ResumeEditor editor={editor} onChange={updateEditor} onSubmit={saveOnlineResume} onCancel={() => setEditor(null)} saving={saving} />
        </div>
      )}

      <section className="rounded-3xl border border-slate-200/90 bg-white p-7 shadow-[0_14px_40px_rgba(24,64,96,0.05)]">
        <div className="flex items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand">CONFIRMED FACTS</p><h2 className="mt-2 text-xl font-semibold text-ink">已确认的画像事实</h2><p className="mt-1 text-sm text-slate-500">这些长期事实可单独修改或删除，不会把临时解析结果自动当成偏好。</p></div><ShieldCheck className="text-teal-500" /></div>
        <form onSubmit={addFact} className="mt-5 flex flex-wrap gap-2"><input value={factValue} onChange={(event) => setFactValue(event.target.value)} placeholder="例如：熟悉 Python 和 FastAPI" className="min-w-0 flex-1 rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-brand" /><button disabled={saving || !factValue.trim()} className="inline-flex items-center gap-1 rounded-xl bg-brand px-4 py-3 text-sm font-semibold text-white disabled:opacity-50"><Plus size={16} />确认添加</button></form>
        <div className="mt-5 grid gap-3 md:grid-cols-2">{facts.length === 0 && <p className="rounded-xl bg-[#f7f9fb] p-4 text-sm text-slate-500 md:col-span-2">还没有已确认的画像事实。</p>}{facts.map((fact) => <div className="flex items-start justify-between gap-3 rounded-xl bg-[#f7f9fb] p-4" key={fact.id}><div><p className="text-sm font-medium text-ink">{fact.fact_value}</p><p className="mt-1 text-xs text-slate-500">{fact.fact_key} · 已确认 {fact.confirmed_at?.slice(0, 10) ?? ""}</p></div><button type="button" onClick={() => void deleteFact(fact.id)} aria-label="删除画像事实" className="rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600"><Trash2 size={16} /></button></div>)}</div>
      </section>
    </section>
  );
}

const resumeSectionLabels: Record<ResumeSectionKey, string> = {
  basics: "基本信息",
  job_intent: "求职意向",
  education: "教育经历",
  campus_experiences: "校园经历",
  experience: "实习 / 工作经历",
  projects: "项目经历",
  skills: "技能与证书",
  summary: "个人简介",
};

function calculateResumeCompletion(content: ResumeStructuredContent) {
  const basics = content.basics;
  const checks = [
    Boolean(basics.full_name || basics.school || basics.major),
    content.job_intent.target_positions.length > 0 || content.job_intent.target_cities.length > 0,
    content.education.length > 0,
    content.campus_experiences.length > 0,
    content.experience.length > 0,
    content.projects.length > 0,
    content.skills.length > 0 || content.certificates.length > 0,
    Boolean(content.summary?.trim()),
  ];
  return Math.round(checks.filter(Boolean).length / checks.length * 100);
}

function ResumePreview({ resume, onEditSection, onEditFull, disabled }: {
  resume: ResumeDetail;
  onEditSection: (section: ResumeSectionKey) => void;
  onEditFull: () => void;
  disabled: boolean;
}) {
  const content = normalizeResumeContent(resume.structured_content);
  const basics = content.basics;
  const completion = calculateResumeCompletion(content);
  const subtitle = [basics.school, basics.major, basics.education, basics.graduation_year ? `${basics.graduation_year} 届` : null].filter(Boolean).join(" · ");
  const editButton = (section: ResumeSectionKey, hasContent: boolean) => (
    <button type="button" disabled={disabled} onClick={() => onEditSection(section)} className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-brand hover:bg-blue-50 disabled:opacity-50">
      {hasContent ? <Pencil size={13} /> : <Plus size={14} />}{hasContent ? "编辑" : "添加"}
    </button>
  );

  return (
    <div className="mt-5 overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 bg-gradient-to-r from-[#f4f9ff] to-white px-5 py-5 sm:px-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-brand">ONLINE RESUME</p>
            <h4 className="mt-2 text-2xl font-semibold tracking-tight text-ink">{basics.full_name || "未填写姓名"}</h4>
            <p className="mt-1 min-h-5 text-sm text-slate-500">{subtitle || "补充学校、专业和学历，让简历信息更完整"}</p>
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
              {basics.city && <span>{basics.city}</span>}
              {basics.phone && <span>{basics.phone}</span>}
              {basics.email && <span>{basics.email}</span>}
              {content.job_intent.target_positions.length > 0 && <span>意向：{content.job_intent.target_positions.join("、")}</span>}
            </div>
          </div>
          <div className="w-full rounded-xl border border-slate-200/80 bg-white/90 p-3 sm:w-52">
            <div className="flex items-center justify-between text-xs"><span className="font-medium text-slate-600">简历完整度</span><strong className="text-brand">{completion}%</strong></div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full bg-brand transition-all" style={{ width: `${completion}%` }} /></div>
            <p className="mt-2 text-[10px] leading-4 text-slate-400">按主要内容区块估算，不代表岗位匹配度</p>
          </div>
        </div>
      </div>

      <div className="divide-y divide-slate-100 px-5 sm:px-7">
        <ResumePreviewSection title="基本信息" onEdit={editButton("basics", Boolean(basics.full_name || basics.school || basics.phone || basics.email))}>
          <div className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
            <PreviewField label="姓名" value={basics.full_name} />
            <PreviewField label="所在地" value={basics.city} />
            <PreviewField label="手机号" value={basics.phone} />
            <PreviewField label="邮箱" value={basics.email} />
            <PreviewField label="学校 / 专业" value={[basics.school, basics.major].filter(Boolean).join(" · ")} />
            <PreviewField label="学历 / 毕业年份" value={[basics.education, basics.graduation_year].filter(Boolean).join(" · ")} />
          </div>
        </ResumePreviewSection>

        <ResumePreviewSection title="求职意向" onEdit={editButton("job_intent", Boolean(content.job_intent.target_positions.length || content.job_intent.target_cities.length || content.job_intent.internship_type))}>
          <div className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
            <PreviewField label="意向岗位" value={content.job_intent.target_positions.join("、")} />
            <PreviewField label="意向城市" value={content.job_intent.target_cities.join("、")} />
            <PreviewField label="实习类型" value={content.job_intent.internship_type} />
            <PreviewField label="到岗 / 出勤" value={[content.job_intent.availability, content.job_intent.days_per_week ? `每周 ${content.job_intent.days_per_week} 天` : null].filter(Boolean).join(" · ")} />
            <PreviewField label="期望薪资" value={content.job_intent.expected_salary} />
          </div>
        </ResumePreviewSection>

        <ResumePreviewSection title="教育经历" onEdit={editButton("education", content.education.length > 0)}>
          {content.education.length ? <div className="space-y-4">{content.education.map((item, index) => <div key={index} className="grid gap-1 sm:grid-cols-[minmax(0,1fr)_auto]"><div><p className="text-sm font-semibold text-ink">{item.school || "学校待补充"}{item.degree ? ` · ${item.degree}` : ""}</p><p className="mt-1 text-xs text-slate-500">{[item.major, item.description].filter(Boolean).join(" · ")}</p></div><span className="text-xs text-slate-400">{formatPeriod(item.start_date, item.end_date)}</span></div>)}</div> : <EmptyResumeSection />}
        </ResumePreviewSection>

        <ResumePreviewSection title="校园经历" onEdit={editButton("campus_experiences", content.campus_experiences.length > 0)}>
          {content.campus_experiences.length ? <ExperiencePreview items={content.campus_experiences} /> : <EmptyResumeSection />}
        </ResumePreviewSection>

        <ResumePreviewSection title="实习 / 工作经历" onEdit={editButton("experience", content.experience.length > 0)}>
          {content.experience.length ? <ExperiencePreview items={content.experience} /> : <EmptyResumeSection />}
        </ResumePreviewSection>

        <ResumePreviewSection title="项目经历" onEdit={editButton("projects", content.projects.length > 0)}>
          {content.projects.length ? <div className="space-y-4">{content.projects.map((item, index) => <div key={index}><div className="flex flex-wrap justify-between gap-2"><p className="text-sm font-semibold text-ink">{item.name || "项目名称待补充"}{item.role ? ` · ${item.role}` : ""}</p><span className="text-xs text-slate-400">{formatPeriod(item.start_date, item.end_date)}</span></div>{item.description && <p className="mt-1 text-sm leading-6 text-slate-600">{item.description}</p>}{(item.technologies.length > 0 || item.highlights.length > 0) && <p className="mt-1 text-xs leading-5 text-slate-500">{[item.technologies.join("、"), item.highlights.join("；")].filter(Boolean).join(" · ")}</p>}</div>)}</div> : <EmptyResumeSection />}
        </ResumePreviewSection>

        <ResumePreviewSection title="技能与证书" onEdit={editButton("skills", Boolean(content.skills.length || content.certificates.length))}>
          {content.skills.length || content.certificates.length ? <div className="space-y-3">{content.skills.length > 0 && <div><p className="text-xs font-medium text-slate-500">技能</p><div className="mt-2 flex flex-wrap gap-2">{content.skills.map((skill, index) => <span key={`${skill}-${index}`} className="rounded-full bg-blue-50 px-3 py-1 text-xs text-blue-700">{skill}</span>)}</div></div>}{content.certificates.length > 0 && <div><p className="text-xs font-medium text-slate-500">证书 / 奖项</p><p className="mt-1 text-sm leading-6 text-slate-700">{content.certificates.join("、")}</p></div>}</div> : <EmptyResumeSection />}
        </ResumePreviewSection>

        <ResumePreviewSection title="个人简介" onEdit={editButton("summary", Boolean(content.summary?.trim()))}>
          {content.summary ? <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700">{content.summary}</p> : <EmptyResumeSection />}
        </ResumePreviewSection>
        {completion === 0 && resume.raw_text.trim() && <section className="py-5"><div className="mb-3 flex items-center justify-between gap-3"><h5 className="border-l-[3px] border-slate-300 pl-3 text-sm font-semibold text-ink">原始简历内容</h5><button type="button" disabled={disabled} onClick={onEditFull} className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-brand hover:bg-blue-50 disabled:opacity-50"><Pencil size={13} />整理为结构化简历</button></div><p className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-xl bg-[#f7f9fb] p-4 text-sm leading-6 text-slate-600">{resume.raw_text}</p></section>}
      </div>
    </div>
  );
}

function ResumePreviewSection({ title, onEdit, children }: { title: string; onEdit: ReactNode; children: ReactNode }) {
  return <section className="py-5"><div className="mb-3 flex items-center justify-between gap-3"><h5 className="border-l-[3px] border-brand pl-3 text-sm font-semibold text-ink">{title}</h5>{onEdit}</div>{children}</section>;
}

function PreviewField({ label, value }: { label: string; value: string | number | null | undefined }) {
  return <p className="min-w-0"><span className="mr-2 text-xs text-slate-400">{label}</span><span className="break-words text-slate-700">{value || "—"}</span></p>;
}

function ExperiencePreview({ items }: { items: ResumeExperienceEntry[] }) {
  return <div className="space-y-4">{items.map((item, index) => <div key={index}><div className="flex flex-wrap justify-between gap-2"><p className="text-sm font-semibold text-ink">{item.organization || "组织待补充"}{item.role ? ` · ${item.role}` : ""}</p><span className="text-xs text-slate-400">{formatPeriod(item.start_date, item.end_date)}</span></div>{item.description && <p className="mt-1 text-sm leading-6 text-slate-600">{item.description}</p>}{item.achievements.length > 0 && <ul className="mt-1 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-500">{item.achievements.map((achievement, achievementIndex) => <li key={achievementIndex}>{achievement}</li>)}</ul>}{item.skills.length > 0 && <p className="mt-1 text-xs text-slate-500">技能：{item.skills.join("、")}</p>}</div>)}</div>;
}

function EmptyResumeSection() { return <p className="text-sm text-slate-400">尚未填写，点击“添加”补充这一部分。</p>; }
function formatPeriod(start: string | null, end: string | null) { return [start, end].filter(Boolean).join(" — ") || "时间待补充"; }
function formatTimestamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
  return date.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
}

function ResumeEditor({ editor, onChange, onSubmit, onCancel, saving }: {
  editor: ResumeEditorState;
  onChange: (patch: Partial<ResumeEditorState>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const content = editor.structuredContent;
  const sectionKey = editor.sectionKey;
  const isSectionEdit = sectionKey !== null;
  const showSection = (key: ResumeSectionKey) => sectionKey === null || sectionKey === key;
  const setContent = (next: ResumeStructuredContent) => onChange({ structuredContent: next });

  function updateEducation(index: number, patch: Partial<ResumeEducationEntry>) {
    setContent({ ...content, education: content.education.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) });
  }
  function updateExperience(index: number, patch: Partial<ResumeExperienceEntry>) {
    setContent({ ...content, experience: content.experience.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) });
  }
  function updateCampusExperience(index: number, patch: Partial<ResumeExperienceEntry>) {
    setContent({ ...content, campus_experiences: content.campus_experiences.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) });
  }
  function updateProject(index: number, patch: Partial<ResumeProjectEntry>) {
    setContent({ ...content, projects: content.projects.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item) });
  }

  return (
    <form role={isSectionEdit ? "dialog" : undefined} aria-modal={isSectionEdit ? true : undefined} aria-label={isSectionEdit && sectionKey ? `编辑${resumeSectionLabels[sectionKey]}` : undefined} onSubmit={onSubmit} className={isSectionEdit ? "max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl sm:p-7" : "mt-5 rounded-2xl border border-blue-200 bg-[#f8fbff] p-5"}>
      <div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-brand">{isSectionEdit ? "EDIT RESUME SECTION" : "REVIEW BEFORE SAVING"}</p><h4 className="mt-1 font-semibold text-ink">{isSectionEdit && sectionKey ? `编辑${resumeSectionLabels[sectionKey]}` : "检查并编辑在线简历草稿"}</h4><p className="mt-1 text-xs leading-5 text-slate-500">{isSectionEdit ? "保存后更新当前简历；已生成的岗位分析保留各自生成时的内容依据。" : "模型可能遗漏或误读信息，请核对后再保存。"}</p></div><button type="button" onClick={onCancel} aria-label="关闭简历编辑器" className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-ink"><X size={17} /></button></div>
      {!isSectionEdit && <label className="mt-4 block"><span className="text-xs font-medium text-slate-600">在线简历名称</span><input value={editor.title} onChange={(event) => onChange({ title: event.target.value })} maxLength={200} required className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-brand" /></label>}

      {showSection("basics") && <div className="mt-5 rounded-xl border border-slate-200 bg-white p-4">
        <SectionTitle title="基础信息" />
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Field label="姓名" value={content.basics.full_name ?? ""} onChange={(value) => setContent({ ...content, basics: { ...content.basics, full_name: nullable(value) } })} placeholder="" />
          <Field label="手机号" value={content.basics.phone ?? ""} onChange={(value) => setContent({ ...content, basics: { ...content.basics, phone: nullable(value) } })} placeholder="" />
          <Field label="邮箱" type="email" value={content.basics.email ?? ""} onChange={(value) => setContent({ ...content, basics: { ...content.basics, email: nullable(value) } })} placeholder="" />
          <Field label="所在城市" value={content.basics.city ?? ""} onChange={(value) => setContent({ ...content, basics: { ...content.basics, city: nullable(value) } })} placeholder="例如：上海" />
          <Field label="学校" value={content.basics.school ?? ""} onChange={(value) => setContent({ ...content, basics: { ...content.basics, school: nullable(value) } })} placeholder="" />
          <Field label="专业" value={content.basics.major ?? ""} onChange={(value) => setContent({ ...content, basics: { ...content.basics, major: nullable(value) } })} placeholder="" />
          <Field label="学历" value={content.basics.education ?? ""} onChange={(value) => setContent({ ...content, basics: { ...content.basics, education: nullable(value) } })} placeholder="" />
          <Field label="毕业年份" type="number" value={content.basics.graduation_year?.toString() ?? ""} onChange={(value) => setContent({ ...content, basics: { ...content.basics, graduation_year: value ? Number(value) : null } })} placeholder="" />
        </div>
        <p className="mt-3 rounded-lg bg-[#f7f9fb] px-3 py-2 text-[11px] leading-5 text-slate-500">姓名和联系方式由你确认维护，仅保存在本机；简历解析时不会发送给模型。</p>
      </div>}

      {showSection("education") && <EntrySection title="教育经历" count={content.education.length} onAdd={() => setContent({ ...content, education: [...content.education, { school: null, degree: null, major: null, start_date: null, end_date: null, description: null }] })}>
        {content.education.map((item, index) => <div key={index} className="rounded-xl border border-slate-200 bg-white p-4"><div className="grid gap-3 sm:grid-cols-2"><Field label="学校" value={item.school ?? ""} onChange={(value) => updateEducation(index, { school: nullable(value) })} placeholder="" /><Field label="专业" value={item.major ?? ""} onChange={(value) => updateEducation(index, { major: nullable(value) })} placeholder="" /><Field label="学历/学位" value={item.degree ?? ""} onChange={(value) => updateEducation(index, { degree: nullable(value) })} placeholder="" /><PeriodFields start={item.start_date ?? ""} end={item.end_date ?? ""} onStart={(value) => updateEducation(index, { start_date: nullable(value) })} onEnd={(value) => updateEducation(index, { end_date: nullable(value) })} /></div><TextAreaField label="课程、荣誉或补充" value={item.description ?? ""} onChange={(value) => updateEducation(index, { description: nullable(value) })} rows={2} /><RemoveButton onClick={() => setContent({ ...content, education: content.education.filter((_, itemIndex) => itemIndex !== index) })} /></div>)}
      </EntrySection>}

      {showSection("job_intent") && <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
        <SectionTitle title="求职意向" />
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <TagAutocompleteField label="意向岗位" value={content.job_intent.target_positions} onChange={(value) => setContent({ ...content, job_intent: { ...content.job_intent, target_positions: value } })} suggestions={targetPositionSuggestions} placeholder="输入岗位名称" helperText="回车添加；可选建议，也可输入自定义岗位。" />
          <TagAutocompleteField label="意向城市" value={content.job_intent.target_cities} onChange={(value) => setContent({ ...content, job_intent: { ...content.job_intent, target_cities: value } })} suggestions={targetCitySuggestions} placeholder="搜索或输入城市" helperText="回车添加城市；支持多选，也可以自定义输入。" />
          <Field label="求职阶段 / 实习类型" value={content.job_intent.internship_type ?? ""} onChange={(value) => setContent({ ...content, job_intent: { ...content.job_intent, internship_type: nullable(value) } })} placeholder="例如：日常实习" />
          <Field label="到岗时间 / 可实习时间" value={content.job_intent.availability ?? ""} onChange={(value) => setContent({ ...content, job_intent: { ...content.job_intent, availability: nullable(value) } })} placeholder="例如：两周内 / 2027 年暑期" />
          <Field label="每周可出勤天数" type="number" value={content.job_intent.days_per_week?.toString() ?? ""} onChange={(value) => setContent({ ...content, job_intent: { ...content.job_intent, days_per_week: value ? Number(value) : null } })} placeholder="例如：4" />
          <Field label="期望薪资（选填）" value={content.job_intent.expected_salary ?? ""} onChange={(value) => setContent({ ...content, job_intent: { ...content.job_intent, expected_salary: nullable(value) } })} placeholder="例如：面议 / 200 元/天" />
        </div>
      </div>}

      {showSection("campus_experiences") && <EntrySection title="校园经历" count={content.campus_experiences.length} onAdd={() => setContent({ ...content, campus_experiences: [...content.campus_experiences, { organization: null, role: null, experience_type: "校园经历", start_date: null, end_date: null, description: null, achievements: [], skills: [] }] })}>
        {content.campus_experiences.map((item, index) => <div key={index} className="rounded-xl border border-slate-200 bg-white p-4"><div className="grid gap-3 sm:grid-cols-2"><Field label="组织 / 活动" value={item.organization ?? ""} onChange={(value) => updateCampusExperience(index, { organization: nullable(value) })} placeholder="例如：学生会、志愿活动" /><Field label="担任角色" value={item.role ?? ""} onChange={(value) => updateCampusExperience(index, { role: nullable(value) })} placeholder="" /><PeriodFields start={item.start_date ?? ""} end={item.end_date ?? ""} onStart={(value) => updateCampusExperience(index, { start_date: nullable(value) })} onEnd={(value) => updateCampusExperience(index, { end_date: nullable(value) })} /></div><TextAreaField label="工作内容" value={item.description ?? ""} onChange={(value) => updateCampusExperience(index, { description: nullable(value) })} rows={3} /><ListTextField label="成果要点（每行一条）" value={item.achievements} onChange={(value) => updateCampusExperience(index, { achievements: value })} delimiter="lines" /><RemoveButton onClick={() => setContent({ ...content, campus_experiences: content.campus_experiences.filter((_, itemIndex) => itemIndex !== index) })} /></div>)}
      </EntrySection>}

      {showSection("experience") && <EntrySection title="实习 / 工作经历" count={content.experience.length} onAdd={() => setContent({ ...content, experience: [...content.experience, { organization: null, role: null, experience_type: "实习", start_date: null, end_date: null, description: null, achievements: [], skills: [] }] })}>
        {content.experience.map((item, index) => <div key={index} className="rounded-xl border border-slate-200 bg-white p-4"><div className="grid gap-3 sm:grid-cols-2"><Field label="公司 / 组织" value={item.organization ?? ""} onChange={(value) => updateExperience(index, { organization: nullable(value) })} placeholder="" /><Field label="岗位" value={item.role ?? ""} onChange={(value) => updateExperience(index, { role: nullable(value) })} placeholder="" /><Field label="经历类型" value={item.experience_type ?? ""} onChange={(value) => updateExperience(index, { experience_type: nullable(value) })} placeholder="实习 / 工作 / 校园" /><PeriodFields start={item.start_date ?? ""} end={item.end_date ?? ""} onStart={(value) => updateExperience(index, { start_date: nullable(value) })} onEnd={(value) => updateExperience(index, { end_date: nullable(value) })} /></div><TextAreaField label="工作内容" value={item.description ?? ""} onChange={(value) => updateExperience(index, { description: nullable(value) })} rows={3} /><ListTextField label="成果要点（每行一条）" value={item.achievements} onChange={(value) => updateExperience(index, { achievements: value })} delimiter="lines" /><ListTextField label="相关技能（逗号分隔）" value={item.skills} onChange={(value) => updateExperience(index, { skills: value })} /><RemoveButton onClick={() => setContent({ ...content, experience: content.experience.filter((_, itemIndex) => itemIndex !== index) })} /></div>)}
      </EntrySection>}

      {showSection("projects") && <EntrySection title="项目经历" count={content.projects.length} onAdd={() => setContent({ ...content, projects: [...content.projects, { name: null, role: null, start_date: null, end_date: null, description: null, highlights: [], technologies: [] }] })}>
        {content.projects.map((item, index) => <div key={index} className="rounded-xl border border-slate-200 bg-white p-4"><div className="grid gap-3 sm:grid-cols-2"><Field label="项目名称" value={item.name ?? ""} onChange={(value) => updateProject(index, { name: nullable(value) })} placeholder="" /><Field label="担任角色" value={item.role ?? ""} onChange={(value) => updateProject(index, { role: nullable(value) })} placeholder="" /><PeriodFields start={item.start_date ?? ""} end={item.end_date ?? ""} onStart={(value) => updateProject(index, { start_date: nullable(value) })} onEnd={(value) => updateProject(index, { end_date: nullable(value) })} /></div><TextAreaField label="项目说明" value={item.description ?? ""} onChange={(value) => updateProject(index, { description: nullable(value) })} rows={3} /><ListTextField label="项目亮点（每行一条）" value={item.highlights} onChange={(value) => updateProject(index, { highlights: value })} delimiter="lines" /><ListTextField label="技术栈（逗号分隔）" value={item.technologies} onChange={(value) => updateProject(index, { technologies: value })} /><RemoveButton onClick={() => setContent({ ...content, projects: content.projects.filter((_, itemIndex) => itemIndex !== index) })} /></div>)}
      </EntrySection>}

      {showSection("skills") && <div className="mt-4 grid gap-4 sm:grid-cols-2"><ListTextField label="技能（逗号分隔）" value={content.skills} onChange={(value) => setContent({ ...content, skills: value })} /><ListTextField label="证书 / 奖项（每行一条）" value={content.certificates} onChange={(value) => setContent({ ...content, certificates: value })} delimiter="lines" /></div>}
      {showSection("summary") && <TextAreaField label="个人简介" value={content.summary ?? ""} onChange={(value) => setContent({ ...content, summary: nullable(value) })} rows={3} />}
      {editor.mode === "version" && !isSectionEdit && <TextAreaField label="原始简历文本 / 补充内容（选填）" value={editor.rawText} onChange={(value) => onChange({ rawText: value })} rows={5} />}

      {!isSectionEdit && <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm text-slate-700"><input type="checkbox" checked={editor.setCurrent} onChange={(event) => onChange({ setCurrent: event.target.checked })} className="accent-brand" />保存后设为当前简历</label>}
      <div className="mt-5 flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4"><button type="button" onClick={onCancel} className="rounded-xl px-4 py-2.5 text-sm font-medium text-slate-500 hover:bg-slate-100">取消</button><button disabled={saving || !editor.title.trim()} className="inline-flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"><Save size={15} />{saving ? "保存中…" : isSectionEdit ? "保存修改" : "确认并保存在线简历"}</button></div>
    </form>
  );
}

function EntrySection({ title, count, onAdd, children }: { title: string; count: number; onAdd: () => void; children: ReactNode }) {
  return <section className="mt-4 rounded-xl border border-slate-200 bg-[#fbfcfe] p-4"><div className="flex items-center justify-between"><div className="text-sm font-semibold text-ink">{title}<span className="ml-2 text-xs font-normal text-slate-400">{count}</span></div><button type="button" onClick={onAdd} className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs font-semibold text-brand hover:bg-blue-50"><Plus size={14} />添加</button></div><div className="mt-3 space-y-3">{children}{count === 0 && <p className="rounded-lg bg-white px-3 py-3 text-xs text-slate-400">未识别到内容，可手动添加。</p>}</div></section>;
}

function AttachmentRow({ attachment, onOpen, onDelete }: { attachment: ResumeAttachment; onOpen: () => void; onDelete: () => void }) {
  const pending = attachment.parse_status === "pending_review";
  return <div className="flex items-center gap-3 rounded-xl border border-slate-100 bg-white p-3"><div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[#f2f6fa] text-slate-500"><FileText size={17} /></div><div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold text-ink" title={attachment.original_filename}>{attachment.original_filename}</p><p className="mt-1 text-[11px] text-slate-500">{formatBytes(attachment.size_bytes)} · {pending ? "等待确认" : "已确认"}</p></div>{pending ? <button type="button" onClick={onOpen} className="shrink-0 rounded-lg bg-blue-50 px-2.5 py-1.5 text-xs font-semibold text-brand hover:bg-blue-100">检查草稿</button> : <a href={`${API_BASE_URL}/profile/resume-attachments/${attachment.id}/file`} download={attachment.original_filename} aria-label="下载原始附件" className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-ink"><Download size={15} /></a>}<button type="button" onClick={onDelete} aria-label="删除附件简历" className="rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600"><Trash2 size={15} /></button></div>;
}

function SectionTitle({ title }: { title: string }) { return <h5 className="border-l-2 border-brand pl-2 text-xs font-bold text-ink">{title}</h5>; }
function PeriodFields({ start, end, onStart, onEnd }: { start: string; end: string; onStart: (value: string) => void; onEnd: (value: string) => void }) { return <div className="grid grid-cols-2 gap-2"><Field label="开始时间" value={start} onChange={onStart} placeholder="2025.06" /><Field label="结束时间" value={end} onChange={onEnd} placeholder="至今" /></div>; }
function RemoveButton({ onClick }: { onClick: () => void }) { return <button type="button" onClick={onClick} className="mt-3 inline-flex items-center gap-1 text-[11px] font-medium text-rose-600 hover:text-rose-700"><Trash2 size={13} />移除此条经历</button>; }
function TagAutocompleteField({ label, value, onChange, suggestions, placeholder, helperText }: {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  suggestions: string[];
  placeholder: string;
  helperText: string;
}) {
  const listId = useId();
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");
  const [focused, setFocused] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const valueSignature = value.join("\u0000");
  const normalizedQuery = draft.trim().toLocaleLowerCase();
  const visibleSuggestions = suggestions
    .filter((suggestion) => !value.some((selected) => selected.toLocaleLowerCase() === suggestion.toLocaleLowerCase()))
    .filter((suggestion) => !normalizedQuery || suggestion.toLocaleLowerCase().includes(normalizedQuery))
    .slice(0, 8);

  useEffect(() => {
    setDraft("");
    setActiveIndex(-1);
  }, [valueSignature]);

  function commit(raw = draft) {
    const nextValues = splitValues(raw);
    if (nextValues.length) onChange(appendUniqueValues(value, nextValues));
    setDraft("");
    setActiveIndex(-1);
  }

  function selectSuggestion(suggestion: string) {
    onChange(appendUniqueValues(value, [suggestion]));
    setDraft("");
    setActiveIndex(-1);
    inputRef.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.nativeEvent.isComposing) return;
    if (event.key === "ArrowDown" && visibleSuggestions.length) {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % visibleSuggestions.length);
    } else if (event.key === "ArrowUp" && visibleSuggestions.length) {
      event.preventDefault();
      setActiveIndex((current) => current <= 0 ? visibleSuggestions.length - 1 : current - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (activeIndex >= 0 && visibleSuggestions[activeIndex]) selectSuggestion(visibleSuggestions[activeIndex]);
      else commit();
    } else if ([",", "，", "、"].includes(event.key)) {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLInputElement>) {
    const pasted = event.clipboardData.getData("text");
    if (!/[,，、\n]/.test(pasted)) return;
    event.preventDefault();
    const pastedValues = splitValues(pasted);
    if (pastedValues.length) onChange(appendUniqueValues(value, pastedValues));
    setDraft("");
  }

  return (
    <div className="min-w-0">
      <label htmlFor={inputId} className="text-xs font-medium text-slate-600">{label}</label>
      <div className="relative mt-1.5">
        <div onClick={() => inputRef.current?.focus()} className={`flex min-h-11 flex-wrap items-center gap-1.5 rounded-xl border bg-white px-2.5 py-2 transition ${focused ? "border-brand ring-4 ring-brand/10" : "border-slate-200 hover:border-slate-300"}`}>
          {value.map((item) => <span key={item.toLocaleLowerCase()} className="inline-flex max-w-full items-center gap-1 rounded-lg border border-blue-100 bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-800">
            <span className="truncate">{item}</span>
            <button type="button" onMouseDown={(event) => event.preventDefault()} onClick={(event) => { event.stopPropagation(); onChange(value.filter((current) => current !== item)); }} aria-label={`移除${item}`} className="rounded p-0.5 text-blue-500 hover:bg-blue-100 hover:text-blue-800"><X size={12} /></button>
          </span>)}
          <input
            ref={inputRef}
            id={inputId}
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={focused && visibleSuggestions.length > 0}
            aria-controls={listId}
            aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
            value={draft}
            onChange={(event) => { setDraft(event.target.value); setActiveIndex(-1); }}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            onFocus={() => setFocused(true)}
            onBlur={() => { setFocused(false); setActiveIndex(-1); }}
            placeholder={value.length ? "继续添加…" : placeholder}
            className="h-7 min-w-28 flex-1 border-0 bg-transparent px-1 text-sm text-ink outline-none placeholder:text-slate-400 focus:ring-0"
          />
        </div>
        {focused && visibleSuggestions.length > 0 && <div className="absolute inset-x-0 top-[calc(100%+6px)] z-30 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-[0_16px_36px_rgba(22,46,76,0.16)]">
          <div className="border-b border-slate-100 px-3 py-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">{normalizedQuery ? "匹配建议" : "常用建议"}</div>
          <ul id={listId} role="listbox" className="max-h-56 overflow-y-auto p-1.5">
            {visibleSuggestions.map((suggestion, index) => <li key={suggestion}>
              <button id={`${listId}-${index}`} type="button" role="option" aria-selected={activeIndex === index} onMouseDown={(event) => event.preventDefault()} onClick={() => selectSuggestion(suggestion)} className={`w-full rounded-lg px-3 py-2 text-left text-sm transition ${activeIndex === index ? "bg-blue-50 text-brand" : "text-slate-700 hover:bg-slate-50"}`}>{suggestion}</button>
            </li>)}
          </ul>
        </div>}
      </div>
      <p className="mt-1.5 text-[11px] leading-4 text-slate-400">{helperText}</p>
    </div>
  );
}

function appendUniqueValues(current: string[], incoming: string[]) {
  const next = [...current];
  const known = new Set(current.map((item) => item.trim().toLocaleLowerCase()));
  for (const raw of incoming) {
    const item = raw.trim();
    const normalized = item.toLocaleLowerCase();
    if (item && !known.has(normalized)) {
      next.push(item);
      known.add(normalized);
    }
  }
  return next;
}

function ListTextField({ label, value, onChange, delimiter = "comma" }: { label: string; value: string[]; onChange: (value: string[]) => void; delimiter?: "comma" | "lines" }) { const separator = delimiter === "lines" ? "\n" : "、"; return delimiter === "lines" ? <TextAreaField label={label} value={value.join(separator)} onChange={(next) => onChange(next.split(/\r?\n/).map((item) => item.trim()).filter(Boolean))} rows={2} /> : <Field label={label} value={value.join(separator)} onChange={(next) => onChange(splitValues(next))} placeholder="" />; }
function TextAreaField({ label, value, onChange, rows }: { label: string; value: string; onChange: (value: string) => void; rows: number }) { return <label className="mt-3 block"><span className="text-xs font-medium text-slate-600">{label}</span><textarea value={value} onChange={(event) => onChange(event.target.value)} rows={rows} className="mt-1.5 w-full resize-y rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm leading-6 outline-none focus:border-brand" /></label>; }
function Field({ label, value, onChange, placeholder, type = "text" }: { label: string; value: string; onChange: (value: string) => void; placeholder: string; type?: string }) { return <label className="block"><span className="text-xs font-medium text-slate-600">{label}</span><input type={type} value={value} onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)} placeholder={placeholder} className="mt-1.5 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-brand/10" /></label>; }
function splitValues(value: string) { return value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean); }
function nullable(value: string) { return value.trim() ? value : null; }
function normalizeResumeContent(content: ResumeStructuredContent | null): ResumeStructuredContent {
  return {
    ...structuredClone(emptyResume),
    ...content,
    basics: { ...emptyResume.basics, ...content?.basics },
    job_intent: { ...emptyResume.job_intent, ...content?.job_intent },
    education: content?.education ?? [],
    campus_experiences: content?.campus_experiences ?? [],
    experience: content?.experience ?? [],
    projects: content?.projects ?? [],
    skills: content?.skills ?? [],
    certificates: content?.certificates ?? [],
    summary: content?.summary ?? null,
  };
}
function buildResumeText(content: ResumeStructuredContent) {
  const lines: string[] = [];
  const add = (heading: string, values: Array<string | null | undefined>) => {
    const present = values.map((value) => value?.trim()).filter((value): value is string => Boolean(value));
    if (present.length) lines.push(`${heading}\n${present.join("\n")}`);
  };
  const basics = content.basics;
  add("基本信息", [basics.full_name, basics.phone, basics.email, basics.city, basics.school, basics.major, basics.education, basics.graduation_year?.toString()]);
  const intent = content.job_intent;
  add("求职意向", [intent.target_positions.join("、"), intent.target_cities.join("、"), intent.internship_type, intent.availability, intent.days_per_week ? `每周${intent.days_per_week}天` : null, intent.expected_salary]);
  add("教育经历", content.education.map((item) => [item.school, item.degree, item.major, item.start_date, item.end_date, item.description].filter(Boolean).join(" · ")));
  add("校园经历", content.campus_experiences.map((item) => [item.organization, item.role, item.start_date, item.end_date, item.description, ...item.achievements].filter(Boolean).join(" · ")));
  add("实习 / 工作经历", content.experience.map((item) => [item.organization, item.role, item.start_date, item.end_date, item.description, ...item.achievements, ...item.skills].filter(Boolean).join(" · ")));
  add("项目经历", content.projects.map((item) => [item.name, item.role, item.start_date, item.end_date, item.description, ...item.highlights, ...item.technologies].filter(Boolean).join(" · ")));
  add("技能", content.skills);
  add("证书 / 奖项", content.certificates);
  add("个人简介", [content.summary]);
  return (lines.join("\n\n") || "在线简历").slice(0, 100_000);
}
function formatBytes(value: number) { return value >= 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(value / 1024))} KB`; }
function readApiError(error: unknown, fallback: string) { const message = (error as { response?: { data?: { detail?: { message?: string } | string } } })?.response?.data?.detail; return typeof message === "object" && message?.message ? message.message : typeof message === "string" ? message : fallback; }
