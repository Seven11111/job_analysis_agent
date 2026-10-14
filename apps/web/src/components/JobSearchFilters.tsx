import { useEffect, useState } from "react";
import { Check, Search, X } from "lucide-react";

import { cityGroups, provinceForCity, quickCityOptions } from "../data/job-search-cities";

export function MultiSelect({ label, values, options, onToggle }: { label: string; values: string[]; options: readonly (readonly [string, string])[]; onToggle: (value: string) => void }) {
  const display = values.length === 0 ? `不限${label}` : values.length === 1 ? options.find(([value]) => value === values[0])?.[1] ?? values[0] : `${options.find(([value]) => value === values[0])?.[1] ?? values[0]} +${values.length - 1}`;
  return <details className="group relative"><summary className="flex h-12 cursor-pointer list-none items-center justify-between rounded-xl border border-slate-200 bg-[#fbfdff] px-4 text-sm text-ink outline-none transition hover:border-brand/60"><span className="truncate">{display}</span><span className="ml-3 text-slate-400">⌄</span></summary><div className="absolute left-0 top-14 z-30 min-w-full rounded-2xl border border-slate-200 bg-white p-2 shadow-[0_18px_45px_rgba(24,64,96,0.16)]">{options.map(([value, text]) => <label key={value} className="flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm hover:bg-blue-50"><input type="checkbox" checked={values.includes(value)} onChange={() => onToggle(value)} className="h-4 w-4 accent-[#1688d8]" />{text}</label>)}</div></details>;
}

export function CityPicker({ values, onChange, label = "工作城市" }: { values: string[]; onChange: (cities: string[]) => void; label?: string }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(values);
  const [query, setQuery] = useState("");
  const [activeProvince, setActiveProvince] = useState("热门城市");
  const normalizedQuery = query.trim();
  const searchResults = normalizedQuery
    ? cityGroups.flatMap(({ province, cities }) => cities
      .filter((city) => city.includes(normalizedQuery) || province.includes(normalizedQuery))
      .map((city) => ({ city, province })))
    : [];
  const activeGroup = cityGroups.find((group) => group.province === activeProvince);
  const visibleCities = normalizedQuery
    ? searchResults
    : activeProvince === "热门城市"
      ? quickCityOptions.map((city) => ({ city, province: provinceForCity(city) ?? "" }))
      : (activeGroup?.cities ?? []).map((city) => ({ city, province: activeGroup?.province ?? "" }));

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open]);

  const toggleDraft = (city: string) => setDraft((current) => {
    if (current.includes(city)) return current.filter((item) => item !== city);
    if (current.length >= 10) return current;
    return [...current, city];
  });
  const toggleQuickCity = (city: string) => {
    if (values.includes(city)) onChange(values.filter((item) => item !== city));
    else if (values.length < 10) onChange([...values, city]);
  };
  const openPicker = () => {
    setDraft(values);
    setQuery("");
    setActiveProvince(values[0] ? provinceForCity(values[0]) ?? "热门城市" : "热门城市");
    setOpen(true);
  };

  return <>
    <div className="rounded-2xl border border-slate-200/90 bg-[#fbfdff] px-4 py-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="min-w-24"><p className="text-xs font-semibold tracking-wide text-slate-500">{label}</p><p className="mt-1 text-xs text-slate-400">{values.length ? `已选 ${values.length} 个` : "全国范围"}</p></div>
        <div className="flex min-w-0 flex-1 flex-wrap gap-2">
          <button type="button" onClick={() => onChange([])} className={`rounded-full px-3 py-1.5 text-sm transition ${values.length === 0 ? "bg-ink text-white" : "bg-white text-slate-600 hover:bg-blue-50"}`}>全国</button>
          {quickCityOptions.map((city) => <button key={city} type="button" onClick={() => toggleQuickCity(city)} disabled={!values.includes(city) && values.length >= 10} className={`rounded-full px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${values.includes(city) ? "bg-blue-100 font-medium text-brand" : "bg-white text-slate-600 hover:bg-blue-50"}`}>{city}</button>)}
          {values.filter((city) => !quickCityOptions.includes(city)).map((city) => <button key={city} type="button" onClick={() => toggleQuickCity(city)} className="rounded-full bg-blue-100 px-3 py-1.5 text-sm font-medium text-brand">{city} ×</button>)}
          <button type="button" onClick={openPicker} className="inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-sm font-medium text-brand transition hover:bg-blue-50">更多城市 <span aria-hidden="true">→</span></button>
        </div>
      </div>
    </div>
    {open && <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-[2px]" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
      <div role="dialog" aria-modal="true" aria-labelledby="city-picker-title" className="flex max-h-[calc(100dvh-2rem)] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-[0_28px_90px_rgba(12,36,70,0.28)]">
        <div className="flex shrink-0 items-start justify-between border-b border-slate-100 px-6 py-5">
          <div><p className="text-xs font-semibold uppercase tracking-[0.2em] text-brand">LOCATION FILTER</p><h2 id="city-picker-title" className="mt-1 text-xl font-semibold text-ink">选择{label}</h2><p className="mt-1 text-sm text-slate-500">按省份查看市级行政区划（含自治州、盟和地区），可跨省多选，最多 10 个。</p></div>
          <button type="button" onClick={() => setOpen(false)} aria-label="关闭城市选择" className="rounded-full p-2 text-slate-400 transition hover:bg-slate-100 hover:text-ink"><X size={19} /></button>
        </div>
        <div className="shrink-0 px-6 pt-5">
          <label className="relative block"><Search size={17} className="absolute left-4 top-3.5 text-slate-400" /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索城市或省份" className="h-11 w-full rounded-xl border border-slate-200 bg-[#fbfdff] pl-11 pr-4 text-sm outline-none transition focus:border-brand focus:ring-4 focus:ring-brand/10" /></label>
          <div className="mt-4 min-h-10">
            <div className="flex items-center justify-between gap-3"><p className="text-xs font-medium text-slate-500">当前选择</p>{draft.length > 0 && <span className="text-xs text-slate-400">{draft.length}/10</span>}</div>
            {draft.length ? <div className="mt-2 flex flex-wrap gap-2">{draft.map((city) => <button key={city} type="button" onClick={() => toggleDraft(city)} className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 px-3 py-1.5 text-xs font-medium text-brand">{city}<X size={13} /></button>)}</div> : <p className="mt-2 text-sm text-slate-400">未选择城市，搜索范围为全国</p>}
          </div>
        </div>
        <div className={`min-h-[220px] flex-1 border-t border-slate-100 ${normalizedQuery ? "grid min-h-0 grid-rows-1" : "grid grid-rows-[auto_minmax(0,1fr)] md:grid-cols-[210px_minmax(0,1fr)] md:grid-rows-1"}`}>
          {!normalizedQuery && <nav aria-label="省份" className="city-picker-scrollbar flex min-h-0 gap-2 overflow-x-auto border-b border-slate-100 bg-slate-50/70 p-3 md:block md:space-y-1 md:overflow-x-hidden md:overflow-y-auto md:border-b-0 md:border-r md:p-3">
            <button type="button" onClick={() => setActiveProvince("热门城市")} aria-pressed={activeProvince === "热门城市"} className={`flex shrink-0 items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition md:w-full ${activeProvince === "热门城市" ? "bg-white font-semibold text-brand shadow-sm" : "text-slate-600 hover:bg-white/80 hover:text-ink"}`}><span>热门城市</span><span className="text-xs text-slate-400">{quickCityOptions.length}</span></button>
            {cityGroups.map((group) => {
              const selectedCount = group.cities.filter((city) => draft.includes(city)).length;
              const active = activeProvince === group.province;
              return <button key={group.province} type="button" onClick={() => setActiveProvince(group.province)} aria-pressed={active} className={`flex shrink-0 items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition md:w-full ${active ? "bg-white font-semibold text-brand shadow-sm" : "text-slate-600 hover:bg-white/80 hover:text-ink"}`}><span className="truncate">{group.province}</span><span className={`text-xs ${selectedCount ? "font-semibold text-brand" : "text-slate-400"}`}>{selectedCount ? `${selectedCount}/${group.cities.length}` : group.cities.length}</span></button>;
            })}
          </nav>}
          <div className="city-picker-scrollbar min-h-0 min-w-0 overflow-y-auto overscroll-contain p-4 sm:p-5">
            <div className="mb-3 flex items-center justify-between"><p className="text-sm font-semibold text-ink">{normalizedQuery ? `搜索结果（${searchResults.length}）` : activeProvince}</p>{!normalizedQuery && activeProvince !== "热门城市" && <span className="text-xs text-slate-400">{visibleCities.length} 个市级地区</span>}</div>
            {visibleCities.length ? <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{visibleCities.map(({ city, province }) => {
              const selected = draft.includes(city);
              const disabled = !selected && draft.length >= 10;
              return <button key={`${province}-${city}`} type="button" onClick={() => toggleDraft(city)} disabled={disabled} aria-pressed={selected} className={`flex min-h-[58px] items-center justify-between gap-2 rounded-xl border px-3.5 py-2.5 text-left transition disabled:cursor-not-allowed disabled:opacity-40 ${selected ? "border-brand/40 bg-blue-50 font-medium text-brand" : "border-slate-200 text-slate-600 hover:border-brand/40 hover:bg-blue-50/60"}`}><span><span className="block text-sm">{city}</span>{normalizedQuery && <span className="mt-0.5 block text-xs text-slate-400">{province}</span>}</span>{selected && <Check size={16} className="shrink-0" />}</button>;
            })}</div> : <p className="rounded-xl bg-slate-50 px-4 py-8 text-center text-sm text-slate-400">{normalizedQuery ? "没有找到匹配的城市" : "该省份暂无市级行政区划"}</p>}
          </div>
        </div>
        <div className="flex flex-col gap-3 border-t border-slate-100 bg-slate-50/70 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <button type="button" onClick={() => setDraft([])} className="self-start whitespace-nowrap text-sm text-slate-500 transition hover:text-brand">清空选择（全国范围）</button>
          <div className="flex justify-end gap-2"><button type="button" onClick={() => setOpen(false)} className="whitespace-nowrap rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50">取消</button><button type="button" onClick={() => { onChange(draft); setOpen(false); }} className="whitespace-nowrap rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#203c61]">应用选择{draft.length > 0 ? `（${draft.length}）` : ""}</button></div>
        </div>
      </div>
    </div>}
  </>;
}
