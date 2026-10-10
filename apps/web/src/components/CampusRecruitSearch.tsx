import { useEffect, useRef, useState, type FormEvent } from "react";
import { AlertCircle, ArrowLeft, ArrowRight, Building2, CalendarDays, ExternalLink, MapPin, Search, ShieldCheck } from "lucide-react";

import { apiClient, type CampusRecruitNotice, type CampusRecruitSearchRequest, type CampusRecruitSearchResponse, type OfferXianshengStatus } from "../api/client";
import { CityPicker, MultiSelect } from "./JobSearchFilters";

type CampusFilters = {
  keyword: string;
  company: string;
  cities: string[];
  graduationYear: string;
  recruitmentBatches: string[];
  startTime: string;
  endTime: string;
};

const emptyFilters: CampusFilters = {
  keyword: "",
  company: "",
  cities: [],
  graduationYear: "",
  recruitmentBatches: [],
  startTime: "",
  endTime: "",
};

const recruitmentBatchOptions = [
  ["春招", "春招"],
  ["秋招", "秋招"],
  ["提前批", "提前批"],
  ["补录", "补录"],
  ["暑期实习", "暑期实习"],
  ["日常实习", "日常实习"],
] as const;

function dateLabel(value: string | null) {
  return value ? value.slice(0, 10).replaceAll("-", "/") : "未说明";
}

function requestErrorMessage(error: unknown) {
  const responseMessage = (error as { response?: { data?: { detail?: { message?: string } } } })
    .response?.data?.detail?.message;
  if (responseMessage) return responseMessage;
  if (error instanceof Error && error.message.includes("Network Error")) return "无法连接后端，请确认 API 服务正在运行。";
  return "校招资讯搜索失败，请稍后重试。";
}

function NoticeTable({ notices }: { notices: CampusRecruitNotice[] }) {
  return <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-[0_10px_32px_rgba(24,64,96,0.045)]">
    <table className="w-full min-w-[1120px] border-collapse text-left text-sm">
      <thead className="bg-[#f5f9fb] text-xs font-semibold uppercase tracking-wide text-slate-500">
        <tr>{["招聘信息 / 企业", "批次 / 届别", "岗位类别", "工作城市", "毕业与学历", "网申时间", "相关链接"].map((heading) => <th key={heading} scope="col" className="whitespace-nowrap border-b border-slate-200 px-4 py-3.5">{heading}</th>)}</tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {notices.map((notice) => <tr key={notice.id} className="align-top transition hover:bg-[#fbfdfd]">
          <td className="max-w-[300px] px-4 py-4">
            <p className="font-semibold leading-5 text-ink">{notice.recruit_info_name || "校招信息"}</p>
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-slate-500"><Building2 size={13} className="shrink-0" />{notice.company_name || "企业名称未说明"}</p>
            <p className="mt-1.5 text-[11px] text-slate-400">来源：{notice.release_source || "Offer 先生"}{notice.updated_at ? ` · 更新 ${dateLabel(notice.updated_at)}` : ""}</p>
            {notice.content && <details className="group mt-2 max-w-full">
              <summary className="cursor-pointer text-xs font-medium text-teal-700">查看公告内容</summary>
              <p className="mt-2 max-h-36 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-600">{notice.content}</p>
            </details>}
          </td>
          <td className="whitespace-nowrap px-4 py-4 text-slate-600">{notice.recruitment_batch || "未说明"}<p className="mt-1 text-xs text-slate-400">{notice.graduation_year ? `${notice.graduation_year} 届` : "届别未知"}</p></td>
          <td className="max-w-[200px] px-4 py-4">{notice.position_categories.length ? <div className="flex flex-wrap gap-1.5">{notice.position_categories.map((category) => <span key={category} className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-medium text-teal-800">{category}</span>)}</div> : <span className="text-slate-400">未说明</span>}</td>
          <td className="max-w-[180px] px-4 py-4 text-slate-600">{notice.cities.length ? <span className="inline-flex items-start gap-1.5"><MapPin size={14} className="mt-0.5 shrink-0 text-slate-400" />{notice.cities.join("、")}</span> : <span className="text-slate-400">未说明</span>}</td>
          <td className="max-w-[220px] px-4 py-4 text-xs leading-5 text-slate-600">{[notice.domestic_graduation_time || notice.domestic_graduation_date, notice.domestic_education && `国内 ${notice.domestic_education}`, notice.overseas_graduation_time || notice.overseas_graduation_date, notice.overseas_education && `留学 ${notice.overseas_education}`].filter(Boolean).join(" · ") || <span className="text-slate-400">未说明</span>}</td>
          <td className="whitespace-nowrap px-4 py-4 text-xs text-slate-600"><span className="inline-flex items-center gap-1.5"><CalendarDays size={13} className="text-slate-400" />{dateLabel(notice.application_start_date)}</span><p className="mt-1 pl-5 text-slate-400">至 {dateLabel(notice.application_end_date)}</p></td>
          <td className="px-4 py-4"><div className="flex min-w-[110px] flex-col items-start gap-2">{notice.announcement_url && <a href={notice.announcement_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-slate-600 transition hover:text-teal-800"><ExternalLink size={13} />公告原文</a>}{notice.application_url && <a href={notice.application_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-semibold text-brand transition hover:text-[#0d76c0]"><ExternalLink size={13} />网申入口</a>}{!notice.announcement_url && !notice.application_url && <span className="text-xs text-slate-400">暂无链接</span>}</div></td>
        </tr>)}
      </tbody>
    </table>
  </div>;
}

export function CampusRecruitSearch() {
  const [status, setStatus] = useState<OfferXianshengStatus | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [filters, setFilters] = useState(emptyFilters);
  const limit = 20;
  const [result, setResult] = useState<CampusRecruitSearchResponse | null>(null);
  const [pageResults, setPageResults] = useState<Record<number, CampusRecruitSearchResponse>>({});
  const [page, setPage] = useState(1);
  const [pageDraft, setPageDraft] = useState("1");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pageResultsRef = useRef<Record<number, CampusRecruitSearchResponse>>({});
  const cursorByPageRef = useRef<Record<number, string | undefined>>({ 1: undefined });
  const activeRequestRef = useRef<CampusRecruitSearchRequest | null>(null);

  useEffect(() => {
    let active = true;
    apiClient.get<OfferXianshengStatus>("/providers/offer-xiansheng/status")
      .then((response) => { if (active) setStatus(response.data); })
      .catch(() => { if (active) setStatus({ provider: "offer_xiansheng", configured: false, status: "unavailable", message: "无法读取来源配置状态，请确认后端服务正常。" }); })
      .finally(() => { if (active) setStatusLoading(false); });
    return () => { active = false; };
  }, []);

  function buildRequest(cursor?: string): CampusRecruitSearchRequest {
    const graduationYear = Number(filters.graduationYear);
    return {
      keyword: filters.keyword.trim() || undefined,
      company: filters.company.trim() || undefined,
      cities: filters.cities,
      graduation_year: filters.graduationYear ? graduationYear : undefined,
      recruitment_batch: filters.recruitmentBatches.length ? filters.recruitmentBatches.join(",") : undefined,
      start_time: filters.startTime || undefined,
      end_time: filters.endTime || undefined,
      limit,
      cursor,
    };
  }

  async function loadPage(targetPage: number) {
    if (loading || targetPage < 1) return;
    const cached = pageResultsRef.current[targetPage];
    if (cached) {
      setResult(cached);
      setPage(targetPage);
      setPageDraft(String(targetPage));
      setError(null);
      return;
    }
    const request = activeRequestRef.current;
    if (!request) return;

    setLoading(true);
    setError(null);
    try {
      const loadedPages = Object.keys(pageResultsRef.current).map(Number);
      let nextPage = loadedPages.length ? Math.max(...loadedPages) + 1 : 1;
      while (nextPage <= targetPage) {
        if (nextPage > 1) {
          const previous = pageResultsRef.current[nextPage - 1];
          if (!previous?.has_more || !cursorByPageRef.current[nextPage]) {
            setError(`目前只读取到 ${nextPage - 1} 页，已到最后一页。`);
            break;
          }
        }
        const response = await apiClient.post<CampusRecruitSearchResponse>("/campus-recruit/search", {
          ...request,
          cursor: cursorByPageRef.current[nextPage],
        });
        pageResultsRef.current = { ...pageResultsRef.current, [nextPage]: response.data };
        if (response.data.has_more && response.data.next_cursor) cursorByPageRef.current[nextPage + 1] = response.data.next_cursor;
        else delete cursorByPageRef.current[nextPage + 1];
        setPageResults(pageResultsRef.current);
        setResult(response.data);
        setPage(nextPage);
        setPageDraft(String(nextPage));
        if (!response.data.has_more && nextPage < targetPage) {
          setError(`目前只有 ${nextPage} 页结果，已显示最后一页。`);
          break;
        }
        nextPage += 1;
      }
    } catch (requestError) {
      setError(requestErrorMessage(requestError));
      if (!pageResultsRef.current[1]) setResult(null);
    } finally {
      setLoading(false);
    }
  }

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!filters.keyword.trim() && !filters.company.trim() && !filters.cities.length && !filters.graduationYear && !filters.recruitmentBatches.length && !filters.startTime && !filters.endTime) {
      setError("请至少填写一个条件，缩小校招资讯查询范围。");
      return;
    }
    const request = buildRequest();
    activeRequestRef.current = request;
    pageResultsRef.current = {};
    cursorByPageRef.current = { 1: undefined };
    setResult(null);
    setPageResults({});
    setPage(1);
    setPageDraft("1");
    void loadPage(1);
  }

  function reset() {
    setFilters(emptyFilters);
    activeRequestRef.current = null;
    pageResultsRef.current = {};
    cursorByPageRef.current = { 1: undefined };
    setResult(null);
    setPageResults({});
    setPage(1);
    setPageDraft("1");
    setError(null);
  }

  function jumpToPage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const targetPage = Number(pageDraft);
    if (!Number.isInteger(targetPage) || targetPage < 1) {
      setError("请输入大于 0 的整数页码。");
      return;
    }
    void loadPage(targetPage);
  }

  const inputClass = "h-11 w-full rounded-xl border border-slate-200 bg-white px-3.5 text-sm text-ink outline-none transition placeholder:text-slate-400 focus:border-teal-500 focus:ring-4 focus:ring-teal-500/10";
  const configured = status?.configured ?? false;
  const loadedPageNumbers = Object.keys(pageResults).map(Number).sort((left, right) => left - right);
  const latestLoadedPage = loadedPageNumbers.length ? pageResults[loadedPageNumbers[loadedPageNumbers.length - 1]] : null;
  const canGoNext = Boolean(pageResults[page + 1] || (result?.has_more && result.next_cursor));
  const visiblePageNumbers = loadedPageNumbers.length <= 5
    ? loadedPageNumbers
    : loadedPageNumbers.filter((value) => value === 1 || value === loadedPageNumbers[loadedPageNumbers.length - 1] || Math.abs(value - page) <= 1);

  return <div className="space-y-6">
    <div className="overflow-hidden rounded-[1.6rem] border border-teal-100 bg-[linear-gradient(120deg,#f1faf8_0%,#ffffff_62%,#f5f9fc_100%)] shadow-[0_14px_40px_rgba(24,64,96,0.055)]">
      <div className="flex flex-wrap items-start justify-between gap-5 px-6 py-6 sm:px-8 sm:py-7">
        <div className="max-w-3xl">
          <p className="text-xs font-semibold uppercase tracking-[0.23em] text-teal-700">CAMPUS RECRUIT / OFFER XIANSHENG</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink">校招资讯</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">按公司、方向、城市和届别查找官方校招公告，结果仅供浏览，不会写入实习岗位管理。</p>
        </div>
        <div className={`inline-flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-medium ${configured ? "border-teal-200 bg-white/80 text-teal-800" : "border-amber-200 bg-white/80 text-amber-800"}`}>
          <ShieldCheck size={15} />{statusLoading ? "正在检查配置" : status?.status === "unavailable" ? "来源状态不可用" : configured ? "API Key 已配置" : "API Key 未配置"}
        </div>
      </div>
      <div className="flex items-start gap-3 border-t border-teal-100/80 bg-white/65 px-6 py-4 text-sm leading-6 text-slate-600 sm:px-8">
        <AlertCircle size={17} className="mt-0.5 shrink-0 text-teal-700" />
        <p>来源数据是招聘公告而非单条实习职位。届别年份不等于发布日期；薪资等未提供字段不会推测。若公告内有具体实习职位，可把职位链接交给求职 Agent 提取后再确认保存。</p>
      </div>
    </div>

    <form onSubmit={search} className="rounded-[1.35rem] border border-slate-200/90 bg-white p-5 shadow-[0_12px_36px_rgba(24,64,96,0.045)] sm:p-6">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <label className="block xl:col-span-2"><span className="mb-1.5 block text-xs font-semibold text-slate-500">关键词 / 职位方向</span><input value={filters.keyword} onChange={(event) => setFilters({ ...filters, keyword: event.target.value })} placeholder="例如：AI 应用、算法、后端" className={inputClass} /></label>
        <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-500">企业名称</span><input value={filters.company} onChange={(event) => setFilters({ ...filters, company: event.target.value })} placeholder="例如：阿里巴巴" className={inputClass} /></label>
        <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-500">毕业届别</span><select value={filters.graduationYear} onChange={(event) => setFilters({ ...filters, graduationYear: event.target.value })} className={inputClass}><option value="">不限届别</option>{[2026, 2027, 2028, 2029, 2030].map((year) => <option value={year} key={year}>{year} 届</option>)}</select></label>
        <div className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-500">招聘批次（可多选）</span><MultiSelect label="招聘批次" values={filters.recruitmentBatches} options={recruitmentBatchOptions} onToggle={(batch) => setFilters({ ...filters, recruitmentBatches: filters.recruitmentBatches.includes(batch) ? filters.recruitmentBatches.filter((item) => item !== batch) : [...filters.recruitmentBatches, batch] })} /></div>
        <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-500">网申开始日期</span><input type="date" value={filters.startTime} onChange={(event) => setFilters({ ...filters, startTime: event.target.value })} className={inputClass} /></label>
        <label className="block"><span className="mb-1.5 block text-xs font-semibold text-slate-500">网申截止日期</span><input type="date" value={filters.endTime} onChange={(event) => setFilters({ ...filters, endTime: event.target.value })} className={inputClass} /></label>
        <div className="xl:col-span-4"><CityPicker values={filters.cities} onChange={(cities) => setFilters({ ...filters, cities })} /></div>
      </div>
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-4">
        <p className="text-xs text-slate-400">日期筛选对应网申起止日期，不是公告发布日期。</p>
        <div className="flex items-center gap-2">
          <button type="button" onClick={reset} className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50">重置</button>
          <button type="submit" disabled={loading || statusLoading || !configured} className="inline-flex items-center gap-2 rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#203c61] disabled:cursor-not-allowed disabled:opacity-50"><Search size={16} />{loading ? "搜索中…" : "搜索校招资讯"}</button>
        </div>
      </div>
      {!statusLoading && !configured && <p className="mt-3 text-right text-xs text-amber-700">{status?.status === "unavailable" ? status.message : "请在后端 `.env` 设置 `OFFER_XIANSHENG_API`，保存后重启后端。"}</p>}
    </form>

    {error && <div role="alert" className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4 text-sm leading-6 text-rose-700"><AlertCircle size={17} className="mt-0.5 shrink-0" />{error}</div>}
    {loading && !result && <div className="rounded-2xl border border-slate-200 bg-white px-5 py-8 text-center text-sm text-slate-500">正在读取 Offer 先生校招数据…</div>}
    {result && <>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 pb-3 text-sm">
        <p className="font-semibold text-ink">本页 {result.count} 条公告 <span className="ml-2 font-normal text-slate-400">第 {page} 页 · 已读取 {loadedPageNumbers.length} 页{latestLoadedPage?.has_more ? " · 还有后续结果" : " · 已到末页"}</span></p>
        <p className="text-xs text-slate-400">数据源：{result.source.name} · 官方游标分页，不提供总数</p>
      </div>
      {result.items.length ? <NoticeTable notices={result.items} /> : <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center"><p className="text-lg font-semibold text-ink">没有找到匹配的校招资讯</p><p className="mt-2 text-sm text-slate-500">可以调整关键词、城市或届别后重新查询。</p></div>}
      <div className="grid gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:p-5 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
        <nav aria-label="校招资讯分页" className="flex min-w-0 flex-wrap items-center justify-center gap-2 md:justify-start">
          <button type="button" onClick={() => void loadPage(page - 1)} disabled={page <= 1 || loading} className="inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 px-3 text-sm text-slate-600 transition hover:border-teal-300 hover:text-teal-800 disabled:cursor-not-allowed disabled:opacity-40"><ArrowLeft size={15} />上一页</button>
          {visiblePageNumbers.map((pageNumber, index) => <span key={pageNumber} className="inline-flex shrink-0 items-center gap-2">{index > 0 && pageNumber - visiblePageNumbers[index - 1] > 1 && <span className="px-0.5 text-slate-400">…</span>}<button type="button" onClick={() => void loadPage(pageNumber)} aria-current={pageNumber === page ? "page" : undefined} disabled={loading} className={`h-10 min-w-10 rounded-lg px-2 text-sm transition disabled:cursor-not-allowed disabled:opacity-50 ${pageNumber === page ? "bg-ink font-semibold text-white" : "border border-slate-200 text-slate-600 hover:border-teal-300 hover:text-teal-800"}`}>{pageNumber}</button></span>)}
          <button type="button" onClick={() => void loadPage(page + 1)} disabled={!canGoNext || loading} className="inline-flex h-10 shrink-0 items-center gap-2 whitespace-nowrap rounded-lg border border-slate-200 px-3 text-sm text-slate-600 transition hover:border-teal-300 hover:text-teal-800 disabled:cursor-not-allowed disabled:opacity-40">下一页<ArrowRight size={15} /></button>
        </nav>
        <form onSubmit={jumpToPage} className="flex items-center justify-center gap-2 border-t border-slate-100 pt-3 md:justify-end md:border-l md:border-t-0 md:pl-5 md:pt-0">
          <label htmlFor="campus-page-jump" className="whitespace-nowrap text-xs text-slate-500">跳转到</label>
          <input id="campus-page-jump" type="number" min="1" step="1" value={pageDraft} onChange={(event) => setPageDraft(event.target.value)} className="h-10 w-20 rounded-lg border border-slate-200 px-2 text-center text-sm text-ink outline-none focus:border-teal-500" />
          <span className="text-xs text-slate-500">页</span>
          <button type="submit" disabled={loading} className="h-10 whitespace-nowrap rounded-lg bg-teal-700 px-4 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:opacity-50">跳转</button>
        </form>
        <p className="text-center text-[11px] leading-5 text-slate-400 md:col-span-2 md:text-right">跳转到未读取页时会按官方游标顺序补取中间页；页码不代表平台总页数。</p>
      </div>
    </>}
    {!loading && !result && !error && <div className="rounded-2xl border border-dashed border-slate-300 bg-white/70 px-6 py-12 text-center text-sm text-slate-500">填写至少一个条件，开始查询校招公告。</div>}
  </div>;
}
