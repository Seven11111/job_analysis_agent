export type JobStatus = "已保存" | "已投递" | "面试中" | "Offer" | "流程终止";

export interface JobSummary {
  id: number;
  title: string;
  company_name: string;
  city: string;
  published_date: string | null;
  salary_status: string;
  is_saved: boolean;
}

export interface MatchSummary {
  match_score: number;
  recommendation: string;
  created_at: string;
}
