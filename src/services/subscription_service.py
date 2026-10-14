"""Local job-search subscriptions with explicit, opt-in persistence."""

from __future__ import annotations

import hashlib
import json
import threading
import calendar
from dataclasses import asdict, replace
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.data_provider.base import JobRecord
from src.db.models import (
    Application,
    JobSubscription,
    JobSubscriptionRun,
    JobSubscriptionRunItem,
    JobSubscriptionSeenJob,
)
from src.db.session import get_session_factory
from src.repositories.profile_repository import ProfileRepository
from src.services.application_service import ApplicationService
from src.services.job_service import JobProviderUnavailable, JobSearchService
from api.v1.schemas.jobs import JobSearchRequest


class SubscriptionNotFound(Exception):
    pass


class InvalidSubscription(Exception):
    pass


class SubscriptionBusy(Exception):
    pass


class JobSubscriptionService:
    """Own subscription configuration, scheduled runs and temporary previews."""

    PREVIEW_RETENTION_DAYS = 30
    PAGE_SIZE = 100
    TIMEZONE = "Asia/Shanghai"
    ALLOWED_PROVIDERS = {"boss_agent_cli", "job_pro"}

    def __init__(self, search_service: JobSearchService | None = None):
        self.search_service = search_service or JobSearchService()
        self.profile_repository = ProfileRepository()
        self.application_service = ApplicationService()
        self._active_lock = threading.Lock()
        self._active_runs: set[int] = set()

    @staticmethod
    def now_utc_naive() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def next_run_time(
        cls,
        frequency: str,
        schedule_time: str,
        weekday: int | None,
        interval_days: int | None = None,
        month_day: int | None = None,
        *,
        now: datetime | None = None,
    ) -> datetime | None:
        if frequency == "manual":
            return None
        timezone_info = ZoneInfo(cls.TIMEZONE)
        current_utc = now or datetime.now(timezone.utc)
        if current_utc.tzinfo is None:
            current_utc = current_utc.replace(tzinfo=timezone.utc)
        local_now = current_utc.astimezone(timezone_info)
        hour, minute = (int(part) for part in schedule_time.split(":"))
        target_time = time(hour=hour, minute=minute)
        candidate = datetime.combine(local_now.date(), target_time, tzinfo=timezone_info)
        if frequency == "daily":
            if candidate <= local_now:
                candidate += timedelta(days=1)
        elif frequency == "weekdays":
            if candidate <= local_now:
                candidate += timedelta(days=1)
            while candidate.isoweekday() > 5:
                candidate += timedelta(days=1)
        elif frequency == "weekly":
            target_weekday = weekday or 1
            candidate += timedelta(days=(target_weekday - local_now.isoweekday()) % 7)
            if candidate <= local_now:
                candidate += timedelta(days=7)
        elif frequency == "interval":
            if candidate <= local_now:
                candidate += timedelta(days=interval_days or 3)
        elif frequency == "monthly":
            target_day = month_day or 1
            last_day = calendar.monthrange(candidate.year, candidate.month)[1]
            candidate = candidate.replace(day=min(target_day, last_day))
            if candidate <= local_now:
                year = candidate.year + (1 if candidate.month == 12 else 0)
                month = 1 if candidate.month == 12 else candidate.month + 1
                last_day = calendar.monthrange(year, month)[1]
                candidate = candidate.replace(year=year, month=month, day=min(target_day, last_day))
        else:
            raise InvalidSubscription("查新频率不受支持")
        return candidate.astimezone(timezone.utc).replace(tzinfo=None)

    def normalize_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        try:
            request = JobSearchRequest.model_validate(filters)
        except Exception as exc:
            raise InvalidSubscription(f"搜索条件无效：{exc}") from exc
        providers = list(dict.fromkeys(request.providers))
        if not providers:
            raise InvalidSubscription("请至少选择一个岗位来源")
        unsupported = [
            provider
            for provider in providers
            if provider not in self.ALLOWED_PROVIDERS or provider not in self.search_service.providers
        ]
        if unsupported:
            raise InvalidSubscription(f"订阅只能使用已接入的岗位来源：{', '.join(unsupported)}")
        request.providers = providers
        payload = request.model_dump(mode="json", exclude_none=True)
        payload.pop("page", None)
        payload.pop("limit", None)
        return payload

    def create(
        self,
        session: Session,
        *,
        name: str,
        filters: dict[str, Any],
        frequency: str,
        schedule_time: str,
        weekday: int | None,
        interval_days: int | None = None,
        month_day: int | None = None,
    ) -> JobSubscription:
        clean_name = name.strip()
        if not clean_name:
            raise InvalidSubscription("请填写查新名称")
        normalized_filters = self.normalize_filters(filters)
        if frequency == "weekly" and weekday is None:
            weekday = 1
        if frequency == "interval" and interval_days is None:
            interval_days = 3
        if frequency == "monthly" and month_day is None:
            month_day = 1
        next_run_at = self.next_run_time(
            frequency, schedule_time, weekday, interval_days, month_day
        )
        profile = self.profile_repository.ensure_profile(session)
        subscription = JobSubscription(
            profile_id=profile.id,
            name=clean_name,
            filters_json=json.dumps(normalized_filters, ensure_ascii=False),
            frequency=frequency,
            schedule_time=schedule_time,
            weekday=weekday,
            interval_days=interval_days,
            month_day=month_day,
            timezone=self.TIMEZONE,
            enabled=True,
            next_run_at=next_run_at,
        )
        session.add(subscription)
        session.commit()
        session.refresh(subscription)
        return subscription

    def update(self, session: Session, subscription_id: int, changes: dict[str, Any]) -> JobSubscription:
        subscription = self._get_subscription(session, subscription_id)
        if "name" in changes:
            name = (changes["name"] or "").strip()
            if not name:
                raise InvalidSubscription("查新名称不能为空")
            subscription.name = name
        if "filters" in changes:
            subscription.filters_json = json.dumps(
                self.normalize_filters(changes["filters"] or {}), ensure_ascii=False
            )
        if "frequency" in changes and changes["frequency"] is not None:
            subscription.frequency = changes["frequency"]
        if "schedule_time" in changes and changes["schedule_time"] is not None:
            subscription.schedule_time = changes["schedule_time"]
        if "weekday" in changes:
            subscription.weekday = changes["weekday"]
        if "interval_days" in changes and changes["interval_days"] is not None:
            subscription.interval_days = changes["interval_days"]
        if "month_day" in changes and changes["month_day"] is not None:
            subscription.month_day = changes["month_day"]
        if subscription.frequency == "weekly" and subscription.weekday is None:
            subscription.weekday = 1
        if subscription.frequency == "interval" and subscription.interval_days is None:
            subscription.interval_days = 3
        if subscription.frequency == "monthly" and subscription.month_day is None:
            subscription.month_day = 1
        if subscription.frequency != "weekly":
            subscription.weekday = None
        if subscription.frequency != "interval":
            subscription.interval_days = None
        if subscription.frequency != "monthly":
            subscription.month_day = None
        if "enabled" in changes and changes["enabled"] is not None:
            subscription.enabled = changes["enabled"]
        subscription.next_run_at = (
            self.next_run_time(
                subscription.frequency,
                subscription.schedule_time,
                subscription.weekday,
                subscription.interval_days,
                subscription.month_day,
            )
            if subscription.enabled
            else None
        )
        session.commit()
        session.refresh(subscription)
        return subscription

    def delete(self, session: Session, subscription_id: int) -> None:
        subscription = self._get_subscription(session, subscription_id)
        run_ids = list(session.scalars(select(JobSubscriptionRun.id).where(
            JobSubscriptionRun.subscription_id == subscription.id
        )))
        if run_ids:
            session.execute(delete(JobSubscriptionRunItem).where(JobSubscriptionRunItem.run_id.in_(run_ids)))
            session.execute(delete(JobSubscriptionRun).where(JobSubscriptionRun.id.in_(run_ids)))
        session.execute(delete(JobSubscriptionSeenJob).where(
            JobSubscriptionSeenJob.subscription_id == subscription.id
        ))
        session.delete(subscription)
        session.commit()

    def list(self, session: Session) -> list[dict[str, Any]]:
        profile = self.profile_repository.ensure_profile(session)
        subscriptions = list(session.scalars(
            select(JobSubscription)
            .where(JobSubscription.profile_id == profile.id)
            .order_by(JobSubscription.updated_at.desc(), JobSubscription.id.desc())
        ))
        result = []
        for subscription in subscriptions:
            latest = session.scalar(
                select(JobSubscriptionRun)
                .where(JobSubscriptionRun.subscription_id == subscription.id)
                .order_by(JobSubscriptionRun.started_at.desc(), JobSubscriptionRun.id.desc())
                .limit(1)
            )
            result.append(self.serialize_subscription(subscription, latest))
        return result

    def get(self, session: Session, subscription_id: int) -> dict[str, Any]:
        subscription = self._get_subscription(session, subscription_id)
        latest = session.scalar(
            select(JobSubscriptionRun)
            .where(JobSubscriptionRun.subscription_id == subscription.id)
            .order_by(JobSubscriptionRun.started_at.desc(), JobSubscriptionRun.id.desc())
            .limit(1)
        )
        return self.serialize_subscription(subscription, latest)

    def run(self, session: Session, subscription_id: int, *, trigger: Literal["manual", "scheduled"] = "manual") -> dict[str, Any]:
        with self._active_lock:
            if subscription_id in self._active_runs:
                raise SubscriptionBusy("这条岗位查新正在运行")
            self._active_runs.add(subscription_id)

        try:
            subscription = self._get_subscription(session, subscription_id)
            if trigger == "scheduled" and not subscription.enabled:
                raise InvalidSubscription("该岗位查新已暂停")
            filters = json.loads(subscription.filters_json)
            started_at = self.now_utc_naive()
            run = JobSubscriptionRun(
                subscription_id=subscription.id,
                trigger=trigger,
                status="running",
                started_at=started_at,
                provider_results_json="[]",
            )
            subscription.last_run_at = started_at
            session.add(run)
            session.commit()
            session.refresh(run)
            self._cleanup_previews(session)

            try:
                candidates, provider_results, total_count = self._collect_candidates(session, filters)
            except JobProviderUnavailable as exc:
                candidates = []
                provider_results = exc.quality
                total_count = 0
                final_status = "failed"
                provider_errors = [
                    f"{item.get('provider')}: {item.get('error')}"
                    for item in provider_results
                    if item.get("error")
                ]
                error_message = "；".join(provider_errors) or str(exc)
            except Exception as exc:
                candidates = []
                provider_results = [{
                    "provider": "search",
                    "status": "failed",
                    "count": 0,
                    "error": str(exc)[:300] or exc.__class__.__name__,
                }]
                total_count = 0
                final_status = "failed"
                error_message = f"岗位查新执行失败：{provider_results[0]['error']}"
            else:
                error_items = [item for item in provider_results if item.get("status") in {"failed", "partial"}]
                error_message = "；".join(
                    f"{item.get('provider')}: {item.get('error')}" for item in error_items if item.get("error")
                ) or None
                final_status = "partial_failed" if error_items else "succeeded"

            new_count = 0
            run_seen: set[tuple[str, str]] = set()
            for provider, record in candidates:
                identity_hash = self.identity_hash(record)
                key = (provider, identity_hash)
                if key in run_seen:
                    continue
                run_seen.add(key)
                seen = session.scalar(select(JobSubscriptionSeenJob).where(
                    JobSubscriptionSeenJob.subscription_id == subscription.id,
                    JobSubscriptionSeenJob.provider == provider,
                    JobSubscriptionSeenJob.identity_hash == identity_hash,
                ))
                is_new = seen is None
                observed_at = self.now_utc_naive()
                if seen is None:
                    session.add(JobSubscriptionSeenJob(
                        subscription_id=subscription.id,
                        provider=provider,
                        identity_hash=identity_hash,
                        first_seen_at=observed_at,
                        last_seen_at=observed_at,
                    ))
                    new_count += 1
                else:
                    seen.last_seen_at = observed_at
                session.add(JobSubscriptionRunItem(
                    run_id=run.id,
                    provider=provider,
                    identity_hash=identity_hash,
                    is_new=is_new,
                    job_json=json.dumps(self.record_payload(record), ensure_ascii=False, default=str),
                    created_at=observed_at,
                ))

            if final_status == "succeeded" and new_count == 0:
                final_status = "no_new"
            run.status = final_status
            run.total_count = total_count
            run.new_count = new_count
            run.provider_results_json = json.dumps(provider_results, ensure_ascii=False, default=str)
            run.error_message = error_message
            run.completed_at = self.now_utc_naive()
            if trigger == "scheduled":
                subscription.next_run_at = self.next_run_time(
                    subscription.frequency,
                    subscription.schedule_time,
                    subscription.weekday,
                    subscription.interval_days,
                    subscription.month_day,
                    now=datetime.now(timezone.utc),
                )
            session.commit()
            session.refresh(run)
            return self.serialize_run(run)
        except Exception:
            session.rollback()
            raise
        finally:
            with self._active_lock:
                self._active_runs.discard(subscription_id)

    def runs(self, session: Session, subscription_id: int, *, page: int = 1, limit: int = 20) -> dict[str, Any]:
        subscription = self._get_subscription(session, subscription_id)
        base = select(JobSubscriptionRun).where(JobSubscriptionRun.subscription_id == subscription.id)
        total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        items = list(session.scalars(
            base.order_by(JobSubscriptionRun.started_at.desc(), JobSubscriptionRun.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        ))
        return {"items": [self.serialize_run(item) for item in items], "total": total, "page": page, "limit": limit}

    def run_detail(
        self, session: Session, subscription_id: int, run_id: int, *, page: int = 1, limit: int = 20
    ) -> dict[str, Any]:
        subscription = self._get_subscription(session, subscription_id)
        run = session.scalar(select(JobSubscriptionRun).where(
            JobSubscriptionRun.id == run_id,
            JobSubscriptionRun.subscription_id == subscription.id,
        ))
        if run is None:
            raise SubscriptionNotFound("查新记录不存在")
        statement = select(JobSubscriptionRunItem).where(JobSubscriptionRunItem.run_id == run.id)
        total_items = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        items = list(session.scalars(
            statement.order_by(JobSubscriptionRunItem.is_new.desc(), JobSubscriptionRunItem.id)
            .offset((page - 1) * limit)
            .limit(limit)
        ))
        completed_at = run.completed_at or run.started_at
        preview_cutoff = self.now_utc_naive() - timedelta(days=self.PREVIEW_RETENTION_DAYS)
        return {
            **self.serialize_run(run),
            "items": [self.serialize_item(item) for item in items],
            "total_items": total_items,
            "page": page,
            "limit": limit,
            "preview_expired": (
                total_items == 0
                and run.total_count > 0
                and completed_at < preview_cutoff
            ),
        }

    def save_item(self, session: Session, item_id: int) -> dict[str, Any]:
        item = session.get(JobSubscriptionRunItem, item_id)
        if item is None:
            raise SubscriptionNotFound("岗位预览已过期，请重新查新")
        if item.saved_job_id is not None:
            profile = self.application_service.repository.ensure_profile(session)
            application = self.application_service.repository.get_by_job(session, profile.id, item.saved_job_id)
            if application is not None:
                return {
                    "item_id": item.id,
                    "job_id": item.saved_job_id,
                    "application_id": application.id,
                    "already_saved": True,
                }

        payload = json.loads(item.job_json)
        if payload.get("published_date"):
            payload["published_date"] = date.fromisoformat(payload["published_date"])
        record = JobRecord(**payload)
        if not record.source_job_id.strip():
            record = replace(record, source_job_id=f"subscription:{item.identity_hash}")
        try:
            job = self.search_service.save_provider_record(session, item.provider, record, commit=False)
            application_repository = self.application_service.repository
            profile = application_repository.ensure_profile(session)
            application = application_repository.get_by_job(session, profile.id, job.id)
            already_saved = application is not None
            if application is None:
                statuses = application_repository.list_statuses(session)
                if not statuses:
                    raise InvalidSubscription("没有可用的岗位状态，请先在岗位管理中设置")
                application = application_repository.create_application(
                    session,
                    profile=profile,
                    job=job,
                    status=statuses[0],
                    note=None,
                )
            item.saved_job_id = job.id
            session.commit()
            return {
                "item_id": item.id,
                "job_id": job.id,
                "application_id": application.id,
                "already_saved": already_saved,
            }
        except Exception:
            session.rollback()
            raise

    def recover_interrupted_runs(self, session: Session) -> int:
        running = list(session.scalars(select(JobSubscriptionRun).where(JobSubscriptionRun.status == "running")))
        now = self.now_utc_naive()
        for run in running:
            run.status = "interrupted"
            run.error_message = "后端在查新完成前退出；请手动重新查新或等待下次计划运行。"
            run.completed_at = now
        if running:
            session.commit()
        return len(running)

    def run_due(self, session_factory=None) -> int:
        factory = session_factory or get_session_factory()
        session = factory()
        try:
            self._cleanup_previews(session)
            session.commit()
            now = self.now_utc_naive()
            due_ids = list(session.scalars(select(JobSubscription.id).where(
                JobSubscription.enabled.is_(True),
                JobSubscription.frequency.in_(
                    ("daily", "weekdays", "weekly", "interval", "monthly")
                ),
                JobSubscription.next_run_at.is_not(None),
                JobSubscription.next_run_at <= now,
            ).order_by(JobSubscription.next_run_at, JobSubscription.id)))
        finally:
            session.close()
        completed = 0
        for subscription_id in due_ids:
            run_session = factory()
            try:
                self.run(run_session, subscription_id, trigger="scheduled")
                completed += 1
            except (SubscriptionNotFound, SubscriptionBusy, InvalidSubscription):
                run_session.rollback()
            finally:
                run_session.close()
        return completed

    def _collect_candidates(
        self, session: Session, filters: dict[str, Any]
    ) -> tuple[list[tuple[str, JobRecord]], list[dict[str, Any]], int]:
        request_payload = {**filters, "page": 1, "limit": self.PAGE_SIZE}
        request = JobSearchRequest.model_validate(request_payload)
        first = self.search_service.search(session, request)
        provider_results = first["quality"]["providers"]
        total_count = first["total"]
        candidates: list[tuple[str, JobRecord]] = []
        page_count = max(1, (total_count + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        for page in range(1, page_count + 1):
            result = first if page == 1 else self.search_service.search(
                session, JobSearchRequest.model_validate({**filters, "page": page, "limit": self.PAGE_SIZE})
            )
            for item in result["items"]:
                token = item.get("result_token")
                if not token:
                    continue
                cached = self.search_service.get_cached_search_job(token)
                candidates.append((cached.provider, cached.record))
        return candidates, provider_results, total_count

    def _get_subscription(self, session: Session, subscription_id: int) -> JobSubscription:
        profile = self.profile_repository.ensure_profile(session)
        subscription = session.scalar(select(JobSubscription).where(
            JobSubscription.id == subscription_id,
            JobSubscription.profile_id == profile.id,
        ))
        if subscription is None:
            raise SubscriptionNotFound("岗位查新不存在")
        return subscription

    def _cleanup_previews(self, session: Session) -> None:
        cutoff = self.now_utc_naive() - timedelta(days=self.PREVIEW_RETENTION_DAYS)
        session.execute(delete(JobSubscriptionRunItem).where(JobSubscriptionRunItem.created_at < cutoff))
        session.flush()

    @classmethod
    def identity_hash(cls, record: JobRecord) -> str:
        source_id = (record.source_job_id or "").strip()
        if source_id and source_id.lower() not in {"none", "null", "unknown", "0"}:
            identity = f"id:{source_id}"
        else:
            identity = f"url:{cls.normalize_url(record.detail_url)}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    @staticmethod
    def normalize_url(value: str) -> str:
        parsed = urlsplit(value.strip())
        query = [
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() != "spm" and not key.lower().startswith("utm_")
        ]
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), urlencode(sorted(query)), ""))

    @staticmethod
    def record_payload(record: JobRecord) -> dict[str, Any]:
        payload = asdict(record)
        if record.published_date:
            payload["published_date"] = record.published_date.isoformat()
        return payload

    def serialize_subscription(
        self, subscription: JobSubscription, latest: JobSubscriptionRun | None
    ) -> dict[str, Any]:
        return {
            "id": subscription.id,
            "name": subscription.name,
            "filters": json.loads(subscription.filters_json),
            "frequency": subscription.frequency,
            "schedule_time": subscription.schedule_time,
            "weekday": subscription.weekday,
            "interval_days": subscription.interval_days,
            "month_day": subscription.month_day,
            "timezone": subscription.timezone,
            "enabled": subscription.enabled,
            "next_run_at": subscription.next_run_at,
            "last_run_at": subscription.last_run_at,
            "created_at": subscription.created_at,
            "updated_at": subscription.updated_at,
            "latest_run": self.serialize_run(latest) if latest else None,
        }

    @staticmethod
    def serialize_run(run: JobSubscriptionRun) -> dict[str, Any]:
        try:
            provider_results = json.loads(run.provider_results_json or "[]")
        except json.JSONDecodeError:
            provider_results = []
        return {
            "id": run.id,
            "subscription_id": run.subscription_id,
            "trigger": run.trigger,
            "status": run.status,
            "total_count": run.total_count,
            "new_count": run.new_count,
            "provider_results": provider_results,
            "error_message": run.error_message,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
        }

    def serialize_item(self, item: JobSubscriptionRunItem) -> dict[str, Any]:
        record = json.loads(item.job_json)
        source_name, source_type, authorization_mode, terms_url = self.search_service.source_meta(item.provider)
        salary_status = record.get("salary_status") or "unknown"
        salary_min = record.get("salary_min")
        salary_max = record.get("salary_max")
        if salary_status == "undisclosed":
            salary_display = "薪资未公开"
        elif salary_status == "negotiable":
            salary_display = "面议"
        elif salary_min is not None and salary_max is not None:
            salary_display = f"{salary_min:g}-{salary_max:g} {record.get('salary_unit') or ''}".strip()
        else:
            salary_display = "薪资待确认"
        job = {
            **record,
            "salary": {
                "min": salary_min,
                "max": salary_max,
                "unit": record.get("salary_unit"),
                "status": salary_status,
                "display": salary_display,
            },
            "source": {
                "name": source_name,
                "provider": item.provider,
                "quality_status": "healthy",
                "source_type": source_type,
                "authorization_mode": authorization_mode,
                "terms_url": terms_url,
            },
        }
        return {
            "id": item.id,
            "provider": item.provider,
            "is_new": item.is_new,
            "job": job,
            "saved_job_id": item.saved_job_id,
        }
