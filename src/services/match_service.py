"""User-triggered, explainable job matching for the first analysis version."""

from __future__ import annotations

import json
import re
from datetime import date

from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.db.models import JobMatch
from src.llm.adapter import LLMAdapter, LLMNotConfiguredError
from src.llm.litellm_adapter import LiteLLMAdapter
from src.llm.prompt_builder import MatchPromptBuilder
from src.schemas.report import MatchReport
from src.repositories.job_repository import JobRepository
from src.repositories.profile_repository import ProfileRepository
from src.services.privacy import mask_sensitive_text


class MatchNotFound(Exception):
    pass


class MatchJobNotFound(Exception):
    pass


class MatchModelNotConfigured(Exception):
    pass


class MatchGenerationFailed(Exception):
    pass


def _sanitize_llm_context(value):
    if isinstance(value, str):
        return mask_sensitive_text(value)
    if isinstance(value, list):
        return [_sanitize_llm_context(item) for item in value]
    if isinstance(value, dict):
        return {
            mask_sensitive_text(str(key)): _sanitize_llm_context(item)
            for key, item in value.items()
        }
    return value


class MatchService:
    """Run user-triggered, evidence-backed LLM matching and persist the report."""

    def __init__(
        self,
        job_repository: JobRepository | None = None,
        profile_repository: ProfileRepository | None = None,
        llm_adapter: LLMAdapter | None = None,
        prompt_builder: MatchPromptBuilder | None = None,
        settings: Settings | None = None,
    ):
        self.job_repository = job_repository or JobRepository()
        self.profile_repository = profile_repository or ProfileRepository()
        self.settings = settings or get_settings()
        self.llm_adapter = llm_adapter or LiteLLMAdapter(self.settings)
        self.prompt_builder = prompt_builder or MatchPromptBuilder()

    def analyze(self, session: Session, job_id: int, resume_version_id: int | None = None) -> dict:
        job = self.job_repository.get_detail(session, job_id)
        if job is None:
            raise MatchJobNotFound("岗位不存在，请先保存岗位")

        profile = self.profile_repository.ensure_profile(session)
        resume = None
        if resume_version_id is not None:
            resume = self.profile_repository.get_resume(session, profile.id, resume_version_id)
            if resume is None:
                raise MatchNotFound("指定的简历版本不存在")
        else:
            resume = next((item for item in profile.resumes if item.is_current), None)

        latest_snapshot = max(job.snapshots, key=lambda item: item.fetched_at, default=None)
        rule_signals = self._rule_match(job, profile, resume)
        context = self._build_context(job, profile, resume, latest_snapshot, rule_signals)
        prompt = self.prompt_builder.build(context, MatchReport.model_json_schema())
        try:
            generated = self.llm_adapter.generate_structured(prompt=prompt, response_type=MatchReport)
            report = generated.model_dump()
        except LLMNotConfiguredError as exc:
            raise MatchModelNotConfigured(str(exc)) from exc
        except Exception as exc:
            raise MatchGenerationFailed(str(exc) or "岗位分析生成失败") from exc

        evidence = {
            "analysis_mode": self.settings.litellm_model,
            "job_snapshot_id": latest_snapshot.id if latest_snapshot else None,
            "job_snapshot_fetched_at": latest_snapshot.fetched_at.isoformat() if latest_snapshot else None,
            "profile_id": profile.id,
            "resume_version_id": resume.id if resume else None,
            "job_source": job.source.name if job.source else None,
            "job_source_url": job.detail_url,
            "rule_precheck": rule_signals,
        }
        match = JobMatch(
            job_id=job.id,
            profile_id=profile.id,
            resume_version_id=resume.id if resume else None,
            match_score=report["match_score"],
            recommendation=report["recommendation"],
            matched_points=json.dumps(report["matched_points"], ensure_ascii=False),
            missing_points=json.dumps(report["missing_points"], ensure_ascii=False),
            risk_points=json.dumps(report["risk_points"], ensure_ascii=False),
            next_actions=json.dumps(report["next_actions"], ensure_ascii=False),
            source_evidence=json.dumps(evidence, ensure_ascii=False),
            raw_result=json.dumps(report, ensure_ascii=False),
            model_used=self.settings.litellm_model,
        )
        session.add(match)
        session.commit()
        session.refresh(match)
        return self.serialize(match, report=report, evidence=evidence)

    @staticmethod
    def _build_context(job, profile, resume, snapshot, rule_signals: dict) -> dict:
        target_cities = ProfileRepository.decode_list(profile.target_cities)
        target_directions = ProfileRepository.decode_list(profile.target_directions)
        desired_industries = ProfileRepository.decode_list(profile.desired_industries)
        active_facts = [
            {"type": fact.fact_type, "key": fact.fact_key, "value": mask_sensitive_text(fact.fact_value)[:800]}
            for fact in profile.facts
            if fact.status == "active"
        ][:20]
        description = mask_sensitive_text(snapshot.description or "") if snapshot else ""
        requirements = mask_sensitive_text(snapshot.requirements or "") if snapshot else ""
        responsibilities = mask_sensitive_text(snapshot.responsibilities or "") if snapshot else ""
        resume_text = mask_sensitive_text(resume.raw_text or "")[:20000] if resume else ""
        resume_text = re.sub(
            r"(?im)^\s*(?:姓名|名字|name)\s*[:：]\s*[^\r\n]+",
            "姓名：[个人信息已脱敏]",
            resume_text,
        )
        resume_structured = None
        resume_private_values = []
        if resume and resume.structured_content:
            try:
                resume_structured = json.loads(resume.structured_content)
                basics = resume_structured.get("basics")
                if isinstance(basics, dict):
                    for field in ("full_name", "phone", "email"):
                        value = basics.pop(field, None)
                        if value:
                            resume_private_values.append(str(value))
            except json.JSONDecodeError:
                resume_structured = None
        for value in resume_private_values:
            resume_text = resume_text.replace(value, "[个人信息已脱敏]")
        salary = {
            "status": job.salary_status,
            "min": job.salary_min if job.salary_status == "disclosed" else None,
            "max": job.salary_max if job.salary_status == "disclosed" else None,
            "unit": job.salary_unit if job.salary_status == "disclosed" else None,
        }
        context = {
            "candidate_profile": {
                "school": profile.school,
                "major": profile.major,
                "education": profile.education,
                "graduation_year": profile.graduation_year,
                "target_directions": target_directions,
                "target_cities": target_cities,
                "available_period": profile.available_period,
                "days_per_week": profile.days_per_week,
                "internship_months": profile.internship_months,
                "desired_industries": desired_industries,
                "confirmed_facts": active_facts,
            },
            "resume": {
                "version_id": resume.id if resume else None,
                "title": resume.title if resume else None,
                "text": resume_text or None,
                "structured_content": resume_structured,
            },
            "job": {
                "id": job.id,
                "title": job.title,
                "company": job.company_name,
                "city": job.city,
                "job_type": job.job_type,
                "education": job.education,
                "published_date": job.published_date.isoformat() if isinstance(job.published_date, date) else None,
                "salary": salary,
                "source": job.source.name if job.source else None,
                "source_url": job.detail_url,
                "snapshot_id": snapshot.id if snapshot else None,
                "snapshot_fetched_at": snapshot.fetched_at.isoformat() if snapshot else None,
                "description": description[:8000] or None,
                "requirements": requirements[:8000] or None,
                "responsibilities": responsibilities[:8000] or None,
            },
            "rule_based_precheck": rule_signals,
        }
        return _sanitize_llm_context(context)

    def history(self, session: Session, job_id: int) -> list[dict]:
        job = self.job_repository.get_detail(session, job_id)
        if job is None:
            raise MatchJobNotFound("岗位不存在")
        return [self.serialize(item) for item in sorted(job.matches, key=lambda item: item.created_at, reverse=True)]

    def get(self, session: Session, match_id: int) -> dict:
        match = session.get(JobMatch, match_id)
        if match is None:
            raise MatchNotFound("岗位分析记录不存在")
        return self.serialize(match)

    @staticmethod
    def _rule_match(job, profile, resume) -> dict:
        target_cities = ProfileRepository.decode_list(profile.target_cities)
        target_directions = ProfileRepository.decode_list(profile.target_directions)
        resume_text = (resume.raw_text if resume else "") or ""
        job_text = " ".join(
            item or ""
            for item in (
                job.title,
                job.company_name,
                job.education,
                *(
                    [max(job.snapshots, key=lambda snapshot: snapshot.fetched_at).description]
                    if job.snapshots
                    else []
                ),
                *(
                    [max(job.snapshots, key=lambda snapshot: snapshot.fetched_at).requirements]
                    if job.snapshots
                    else []
                ),
            )
        ).lower()
        matched: list[str] = []
        missing: list[str] = []
        risks: list[str] = []
        score = 45

        if not target_cities or job.city in target_cities:
            score += 15
            matched.append(f"工作城市{job.city}符合当前画像")
        else:
            missing.append(f"工作城市为{job.city}，不在当前目标城市中")

        direction = next((item for item in target_directions if item.lower() in job_text), None)
        if direction:
            score += 20
            matched.append(f"岗位方向与画像中的“{direction}”相关")
        elif target_directions:
            missing.append("岗位方向与当前目标方向的直接匹配证据不足")
        else:
            missing.append("尚未填写目标岗位方向")

        if resume_text:
            resume_terms = {item for item in ("python", "java", "golang", "c++", "sql", "fastapi", "django", "react", "linux") if item in resume_text.lower()}
            overlapping = sorted(term for term in resume_terms if term in job_text)
            if overlapping:
                score += min(20, len(overlapping) * 5)
                matched.append(f"简历与岗位文本存在技能交集：{', '.join(overlapping)}")
            else:
                missing.append("简历技能与当前岗位文本缺少可直接核验的交集")
        else:
            risks.append("尚未设置当前简历，分析仅使用岗位和求职画像")

        if job.salary_status != "disclosed":
            risks.append("岗位薪资未公开，无法据此比较机会成本")
        if job.published_date is None:
            risks.append("来源未提供明确发布日期，时效性需要打开来源页面确认")

        score = max(0, min(100, score))
        recommendation = "strong_match" if score >= 80 else "match" if score >= 60 else "observe" if score >= 40 else "not_recommended"
        return {
            "summary": f"规则初筛得分 {score} 分。该结果用于帮助你决定是否值得进一步查看，不替代人工判断。",
            "match_score": score,
            "recommendation": recommendation,
            "matched_points": matched,
            "missing_points": missing,
            "risk_points": risks,
            "next_actions": ["打开岗位来源核对最新 JD 和投递要求", "确认岗位方向和城市仍符合当前求职目标"],
        }

    @staticmethod
    def _load_json(value: str | None) -> list | dict:
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, (list, dict)) else []

    @classmethod
    def serialize(cls, match: JobMatch, *, report: dict | None = None, evidence: dict | None = None) -> dict:
        report = report or {
            "summary": cls._load_json(match.raw_result).get("summary", "") if isinstance(cls._load_json(match.raw_result), dict) else "",
            "match_score": match.match_score,
            "recommendation": match.recommendation,
            "matched_points": cls._load_json(match.matched_points),
            "missing_points": cls._load_json(match.missing_points),
            "risk_points": cls._load_json(match.risk_points),
            "next_actions": cls._load_json(match.next_actions),
        }
        evidence = evidence or cls._load_json(match.source_evidence)
        return {
            "id": match.id,
            **report,
            "analysis_mode": match.model_used or "rules_v1",
            "evidence": evidence,
            "created_at": match.created_at,
        }
