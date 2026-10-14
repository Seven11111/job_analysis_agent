"""Explainable, local-only ranking for temporary job search results."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.db.models import CandidateProfile, ResumeVersion
from src.data_provider.base import JobRecord
from src.schemas.resume import ResumeStructuredContent
from src.repositories.profile_repository import ProfileRepository


SKILL_ALIASES = {
    "Python": ("python",),
    "Java": ("java",),
    "Go": ("golang", "go语言"),
    "C++": ("c++",),
    "JavaScript": ("javascript", "js"),
    "TypeScript": ("typescript", "ts"),
    "React": ("react",),
    "Vue": ("vue",),
    "Node.js": ("node.js", "nodejs"),
    "SQL": ("sql",),
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql",),
    "Redis": ("redis",),
    "Docker": ("docker",),
    "Kubernetes": ("kubernetes", "k8s"),
    "FastAPI": ("fastapi",),
    "Django": ("django",),
    "Flask": ("flask",),
    "Spring": ("spring",),
    "PyTorch": ("pytorch",),
    "TensorFlow": ("tensorflow",),
    "Spark": ("spark",),
    "LLM/大模型": ("llm", "大模型", "大语言模型", "large language model"),
    "Agent/智能体": ("agent", "智能体"),
    "RAG": ("rag", "检索增强生成"),
    "Linux": ("linux",),
    "Git": ("git",),
}

ROLE_GROUPS = (
    ("后端", "后端", "服务端", "backend"),
    ("前端", "前端", "frontend"),
    ("算法", "算法", "机器学习", "深度学习", "algorithm"),
    ("AI 应用", "ai应用", "大模型应用", "agent", "智能体", "llm"),
    ("数据分析", "数据分析", "数据挖掘", "商业分析", "bi"),
    ("测试", "测试", "qa", "test"),
    ("产品", "产品", "product"),
    ("运维", "运维", "devops", "sre"),
)


def _normalized(value: str | None) -> str:
    return re.sub(r"[\s\W_]+", "", (value or "").casefold(), flags=re.UNICODE)


def _json_list(value: str | None) -> list[str]:
    return ProfileRepository.decode_list(value)


def _structured_resume(resume: ResumeVersion | None) -> dict:
    if not resume or not resume.structured_content:
        return {}
    try:
        return ResumeStructuredContent.model_validate(json.loads(resume.structured_content)).model_dump()
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _has_term(text: str, term: str) -> bool:
    term = term.strip()
    if not term:
        return False
    if re.fullmatch(r"[a-zA-Z0-9+#. /-]+", term):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None
    return _normalized(term) in _normalized(text)


def _find_skills(text: str) -> set[str]:
    found: set[str] = set()
    for skill, aliases in SKILL_ALIASES.items():
        if any(_has_term(text, alias) for alias in aliases):
            found.add(skill)
    return found


def _education_level(value: str | None) -> int | None:
    text = value or ""
    if not text.strip():
        return None
    for term, level in (("博士", 5), ("硕士", 4), ("研究生", 4), ("本科", 3), ("学士", 3), ("大专", 2), ("专科", 2), ("高中", 1)):
        if term in text:
            return level
    return None


@dataclass(frozen=True)
class RecommendationContext:
    directions: list[str]
    cities: list[str]
    industries: list[str]
    education: str | None
    available_period: str | None
    days_per_week: int | None
    internship_months: float | None
    resume_text: str
    resume_skills: set[str]
    profile_used: bool
    resume_used: bool


class JobRecommendationService:
    """Ranks only the current in-memory search results; never writes profile data."""

    @staticmethod
    def load_context(session: Session | None) -> RecommendationContext:
        if session is None:
            return RecommendationContext([], [], [], None, None, None, None, "", set(), False, False)
        profile = session.scalar(
            select(CandidateProfile)
            .options(selectinload(CandidateProfile.resumes))
            .where(CandidateProfile.active.is_(True))
            .order_by(CandidateProfile.id)
        )
        if profile is None:
            return RecommendationContext([], [], [], None, None, None, None, "", set(), False, False)

        resumes = [resume for resume in profile.resumes if resume.is_current]
        resume = max(resumes, key=lambda item: item.updated_at, default=None)
        structured = _structured_resume(resume)
        intent = structured.get("job_intent") or {}
        basics = structured.get("basics") or {}
        profile_directions = _json_list(profile.target_directions)
        resume_directions = intent.get("target_positions") or []
        profile_cities = _json_list(profile.target_cities)
        resume_cities = intent.get("target_cities") or []
        directions = list(dict.fromkeys([*profile_directions, *resume_directions]))
        cities = list(dict.fromkeys([*profile_cities, *resume_cities]))
        industries = _json_list(profile.desired_industries)
        if not industries and profile.desired_industries:
            # Older local databases may contain comma-separated text, while the
            # current contract stores a JSON list. Do not interpret valid `[]`
            # as a literal industry named "[]".
            try:
                decoded_industries = json.loads(profile.desired_industries)
            except json.JSONDecodeError:
                decoded_industries = None
            if not isinstance(decoded_industries, list):
                industries = [
                    item.strip()
                    for item in re.split(r"[,，、;；]", profile.desired_industries)
                    if item.strip()
                ]

        resume_text_parts = [resume.raw_text if resume else ""]
        resume_text_parts.extend(structured.get("skills") or [])
        for group in ("education", "experience", "campus_experiences", "projects"):
            for entry in structured.get(group) or []:
                resume_text_parts.extend(str(value) for value in entry.values() if isinstance(value, str))
                for key in ("skills", "technologies", "highlights", "achievements"):
                    resume_text_parts.extend(str(value) for value in entry.get(key, []) if value)
        resume_text = " ".join(resume_text_parts)
        structured_skills = " ".join(structured.get("skills") or [])
        resume_skills = _find_skills(resume_text)
        resume_skills.update(_find_skills(structured_skills))

        education = profile.education or basics.get("education")
        if not education:
            education = next(
                (entry.get("degree") for entry in structured.get("education", []) if entry.get("degree")),
                None,
            )
        days_per_week = profile.days_per_week or intent.get("days_per_week")
        internship_months = profile.internship_months
        available_period = profile.available_period or intent.get("availability")
        profile_used = bool(
            directions or cities or industries or education or available_period
            or profile.days_per_week or profile.internship_months
        )
        resume_used = bool(resume and (resume.raw_text.strip() or structured))
        return RecommendationContext(
            directions=directions,
            cities=cities,
            industries=industries,
            education=education,
            available_period=available_period,
            days_per_week=days_per_week,
            internship_months=internship_months,
            resume_text=resume_text,
            resume_skills=resume_skills,
            profile_used=profile_used,
            resume_used=resume_used,
        )

    @staticmethod
    def describe_context(context: RecommendationContext, request) -> dict:
        sort_by = request.sort_by
        personalized = JobRecommendationService.has_usable_context(context, request)
        if sort_by == "newest":
            message = "按岗位发布日期排序；匹配依据仍可查看，但不会影响顺序。"
        elif personalized:
            message = "按本次条件允许使用的求职偏好/在线简历信号进行本地规则排序；不是录用概率，也未调用模型深度分析。"
        else:
            message = "本次明确条件优先；当前资料没有可用于个性化排序的信息，暂按最新发布日期展示。"
        return {
            "sort_by": sort_by,
            "personalized": personalized and sort_by == "recommended",
            "profile_used": context.profile_used,
            "resume_used": context.resume_used,
            "message": message,
        }

    @staticmethod
    def has_usable_context(context: RecommendationContext, request) -> bool:
        has_city_filter = bool(getattr(request, "cities", None) or getattr(request, "city", None))
        return bool(
            (context.directions and not getattr(request, "keyword", None))
            or (context.cities and not has_city_filter)
            or context.industries
            or (context.education and not getattr(request, "education", None))
            or (context.resume_skills and context.resume_used)
            or (context.days_per_week and not getattr(request, "days_per_week", None))
            or (context.internship_months and not getattr(request, "internship_months", None))
        )

    def analyze(self, job: JobRecord, context: RecommendationContext, request) -> dict:
        matched: list[str] = []
        missing: list[str] = []
        unknown: list[str] = []
        score = 50
        job_text = " ".join(
            part for part in (job.title, job.description, job.requirements, job.responsibilities) if part
        )

        keyword = (getattr(request, "keyword", None) or "").strip()
        if keyword:
            if _normalized(keyword) in _normalized(job.title):
                score += 10
                matched.append(f"岗位标题包含本次关键词「{keyword}」")
            else:
                matched.append(f"岗位内容符合本次关键词「{keyword}」筛选")
        elif context.directions:
            matching_direction = next(
                (direction for direction in context.directions if self._direction_matches(direction, job_text)), None
            )
            if matching_direction:
                score += 22
                matched.append(f"岗位内容与求职方向「{matching_direction}」相符")
            else:
                score -= 10
                missing.append("岗位内容未命中已填写的目标岗位方向；可核对后再决定")
        else:
            unknown.append("尚未填写目标岗位方向")

        requested_cities = list(getattr(request, "cities", None) or [])
        if not requested_cities and getattr(request, "city", None):
            requested_cities = [request.city]
        if requested_cities:
            matched.append(f"已按本次指定城市筛选：{'、'.join(requested_cities)}")
        elif context.cities:
            matching_city = next((city for city in context.cities if _normalized(city) in _normalized(job.city)), None)
            if matching_city:
                score += 12
                matched.append(f"工作城市「{job.city}」符合目标城市「{matching_city}」")
            else:
                score -= 8
                missing.append(f"工作城市「{job.city or '未说明'}」与已填写目标城市未匹配")
        else:
            unknown.append("尚未填写目标城市偏好")

        if context.industries:
            matching_industry = next(
                (industry for industry in context.industries if _normalized(industry) in _normalized(job_text)), None
            )
            if matching_industry:
                score += 8
                matched.append(f"岗位公开内容出现关注行业「{matching_industry}」")
            else:
                unknown.append("岗位内容未明确体现已关注行业，无法据此判断")

        if context.resume_used:
            job_skills = _find_skills(job_text)
            shared_skills = sorted(context.resume_skills & job_skills)
            missing_skills = sorted(job_skills - context.resume_skills)
            if shared_skills:
                score += min(20, len(shared_skills) * 5)
                matched.append(f"简历与岗位内容均提及：{'、'.join(shared_skills[:4])}")
            if missing_skills:
                score -= min(12, len(missing_skills) * 3)
                missing.append(
                    f"岗位提及{'、'.join(missing_skills[:4])}，当前简历未检索到对应证据（不代表你不具备）"
                )
            if not job_skills:
                unknown.append("岗位正文没有可识别的技能关键词，技能匹配信息不足")
            elif not context.resume_skills:
                unknown.append("当前在线简历没有可识别的技能关键词")
        else:
            unknown.append("未设置当前在线简历，无法核对技能与项目经历")

        current_education_filter = getattr(request, "education", None)
        if current_education_filter:
            matched.append(f"已应用本次学历条件「{current_education_filter}」，不再用长期学历偏好重排")
        elif job.education:
            candidate_level = _education_level(context.education)
            required_level = _education_level(job.education)
            if candidate_level is None or required_level is None:
                unknown.append(f"岗位学历要求为「{job.education}」，画像学历信息不足以比较")
            elif candidate_level >= required_level:
                score += 8
                matched.append(f"已填写学历与岗位要求「{job.education}」相符")
            else:
                score -= 10
                missing.append(f"已填写学历可能低于岗位要求「{job.education}」，建议核对原文")
        else:
            unknown.append("岗位未说明学历要求")

        if getattr(request, "days_per_week", None) or getattr(request, "internship_months", None):
            matched.append("已优先执行本次明确填写的到岗/实习时长筛选")
        else:
            self._compare_availability(job, context, matched, missing, unknown)

        if not job.description and not job.requirements and not job.responsibilities:
            unknown.append("来源未提供岗位职责或详细要求，匹配解释仅依据基础字段")
        if context.available_period and not (
            getattr(request, "days_per_week", None) or getattr(request, "internship_months", None)
        ):
            unknown.append(f"已填写可到岗时间「{context.available_period}」，岗位来源未提供可比对的到岗日期")

        # Avoid a numeric score when there is no actual candidate information to compare.
        final_score = max(0, min(100, score)) if self.has_usable_context(context, request) else None
        return {
            "score": final_score,
            "label": "画像匹配参考分" if final_score is not None else "待完善画像",
            "matched_points": matched[:5],
            "missing_points": missing[:4],
            "unknown_points": unknown[:5],
            "feedback": None,
        }

    @staticmethod
    def _direction_matches(direction: str, job_text: str) -> bool:
        normalized_direction = _normalized(direction)
        if normalized_direction and normalized_direction in _normalized(job_text):
            return True
        normalized_job = _normalized(job_text)
        for group in ROLE_GROUPS:
            if any(_normalized(term) in normalized_direction for term in group) and any(
                _normalized(term) in normalized_job for term in group
            ):
                return True
        return False

    @staticmethod
    def _compare_availability(job: JobRecord, context: RecommendationContext, matched, missing, unknown) -> None:
        if job.days_per_week is not None:
            if context.days_per_week is None:
                unknown.append(f"岗位要求每周到岗 {job.days_per_week} 天，但未填写可到岗天数")
            elif context.days_per_week >= job.days_per_week:
                matched.append(f"每周可到岗 {context.days_per_week} 天，满足岗位要求")
            else:
                missing.append(f"每周可到岗 {context.days_per_week} 天，低于岗位要求的 {job.days_per_week} 天")
        else:
            unknown.append(
                "岗位未说明每周到岗天数"
                if context.days_per_week is not None
                else "岗位未说明每周到岗天数，画像也未填写可到岗天数"
            )

        if job.internship_months is not None:
            if context.internship_months is None:
                unknown.append(f"岗位要求实习 {job.internship_months:g} 个月，未填写可实习时长")
            elif context.internship_months >= job.internship_months:
                matched.append(f"可实习 {context.internship_months:g} 个月，满足岗位要求")
            else:
                missing.append(f"可实习 {context.internship_months:g} 个月，短于岗位要求的 {job.internship_months:g} 个月")
        else:
            unknown.append(
                "岗位未说明实习时长"
                if context.internship_months is not None
                else "岗位未说明实习时长，画像也未填写可实习时长"
            )
