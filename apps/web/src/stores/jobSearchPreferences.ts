export type JobSearchProvider = "boss_agent_cli" | "job_pro";

export const JOB_SEARCH_PROVIDERS_STORAGE_KEY = "job-analysis-agent:job-search-providers:v1";

const providerLabels: Record<JobSearchProvider, string> = {
  boss_agent_cli: "BOSS 直聘",
  job_pro: "job-pro",
};

export function readJobSearchProviders(fallback: JobSearchProvider[] = ["job_pro"]): JobSearchProvider[] {
  try {
    const stored = window.localStorage.getItem(JOB_SEARCH_PROVIDERS_STORAGE_KEY);
    if (stored === null) return [...fallback];
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [...fallback];
    return [...new Set(parsed.filter((item): item is JobSearchProvider => item === "boss_agent_cli" || item === "job_pro"))];
  } catch {
    return [...fallback];
  }
}

export function saveJobSearchProviders(providers: readonly string[]): void {
  try {
    const selected = [...new Set(providers.filter((item): item is JobSearchProvider => item === "boss_agent_cli" || item === "job_pro"))];
    window.localStorage.setItem(JOB_SEARCH_PROVIDERS_STORAGE_KEY, JSON.stringify(selected));
  } catch {
    // The search page remains usable when browser storage is unavailable.
  }
}

export function formatJobSearchProviders(providers: readonly JobSearchProvider[]): string {
  return providers.length ? providers.map((provider) => providerLabels[provider]).join(" + ") : "未选择";
}
