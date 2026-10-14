from collections.abc import Generator
from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.app import create_app
from api.deps import db_session
from api.v1.endpoints import subscriptions as subscription_endpoints
from src.data_provider.base import JobRecord
from src.db.base import Base
from src.db.models import JobSubscription, JobSubscriptionRun, JobSubscriptionRunItem
from src.services.subscription_scheduler import JobSubscriptionScheduler
from src.services.subscription_service import JobSubscriptionService


class FakeJobProvider:
    def __init__(self, records: list[JobRecord] | None = None, error: Exception | None = None):
        self.records = records or []
        self.error = error

    def search(self, *, keyword=None, city=None, company=None):
        if self.error:
            raise self.error
        return self.records


def make_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'subscriptions.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)

    def override_db() -> Generator[Session, None, None]:
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[db_session] = override_db
    return TestClient(app), engine


def sample_job() -> JobRecord:
    return JobRecord(
        source_job_id="job-pro-7788",
        title="Agent 平台开发实习生",
        company_name="示例科技",
        city="杭州",
        detail_url="https://jobs.example.com/positions/7788?utm_source=test",
        published_date=date(2026, 10, 12),
        salary_status="undisclosed",
        description="参与 Agent 平台研发。",
        requirements="熟悉 Python。",
        extraction_method="provider_api",
    )


def make_subscription(client: TestClient, *, frequency="manual", schedule_options=None) -> dict:
    payload = {
        "name": "杭州 Agent 实习",
        "filters": {
            "keyword": "Agent",
            "cities": ["杭州"],
            "published_range": "all",
            "salary_mode": "any",
            "providers": ["job_pro"],
            "sort_by": "newest",
        },
        "frequency": frequency,
        "schedule_time": "09:00",
        "weekday": 1 if frequency == "weekly" else None,
    }
    payload.update(schedule_options or {})
    response = client.post("/api/v1/subscriptions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_subscription_preview_deduplicates_and_only_saves_after_confirmation(tmp_path, monkeypatch):
    client, engine = make_client(tmp_path)
    monkeypatch.setitem(
        subscription_endpoints.service.search_service.providers,
        "job_pro",
        FakeJobProvider([sample_job()]),
    )
    subscription = make_subscription(client)

    first_run = client.post(f"/api/v1/subscriptions/{subscription['id']}/runs")
    assert first_run.status_code == 200, first_run.text
    assert first_run.json()["status"] == "succeeded"
    assert first_run.json()["new_count"] == 1
    first_detail = client.get(
        f"/api/v1/subscriptions/{subscription['id']}/runs/{first_run.json()['id']}"
    ).json()
    assert first_detail["items"][0]["is_new"] is True
    assert first_detail["items"][0]["job"]["source"]["provider"] == "job_pro"

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 0
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM applications").scalar_one() == 0

    second_run = client.post(f"/api/v1/subscriptions/{subscription['id']}/runs")
    assert second_run.status_code == 200, second_run.text
    assert second_run.json()["status"] == "no_new"
    assert second_run.json()["new_count"] == 0
    second_detail = client.get(
        f"/api/v1/subscriptions/{subscription['id']}/runs/{second_run.json()['id']}"
    ).json()
    assert second_detail["items"][0]["is_new"] is False

    item_id = first_detail["items"][0]["id"]
    saved = client.post(f"/api/v1/subscriptions/items/{item_id}/save")
    assert saved.status_code == 200, saved.text
    assert saved.json()["already_saved"] is False
    repeated_save = client.post(f"/api/v1/subscriptions/items/{item_id}/save")
    assert repeated_save.status_code == 200, repeated_save.text
    assert repeated_save.json()["already_saved"] is True

    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM jobs").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM job_snapshots").scalar_one() == 1
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM applications").scalar_one() == 1


def test_subscription_rejects_unconfigured_or_non_job_sources(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post("/api/v1/subscriptions", json={
        "name": "不允许离线示例",
        "filters": {"published_range": "all", "salary_mode": "any", "providers": ["fixture"]},
    })
    assert response.status_code == 422
    assert "job_pro" in response.json()["detail"]["message"] or "已接入" in response.json()["detail"]["message"]


def test_subscription_preserves_provider_failure_in_run_history(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path)
    monkeypatch.setitem(
        subscription_endpoints.service.search_service.providers,
        "job_pro",
        FakeJobProvider(error=RuntimeError("provider is temporarily unavailable")),
    )
    subscription = make_subscription(client)

    response = client.post(f"/api/v1/subscriptions/{subscription['id']}/runs")
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "failed"
    assert "temporarily unavailable" in run["error_message"]
    assert run["provider_results"][0]["status"] == "failed"


def test_subscription_schedule_uses_beijing_wall_clock():
    before_daily = JobSubscriptionService.next_run_time(
        "daily", "09:00", None, now=datetime(2026, 10, 12, 0, 30, tzinfo=timezone.utc)
    )
    assert before_daily == datetime(2026, 10, 12, 1, 0)

    after_monday = JobSubscriptionService.next_run_time(
        "weekly", "09:00", 1, now=datetime(2026, 10, 12, 1, 30, tzinfo=timezone.utc)
    )
    assert after_monday == datetime(2026, 10, 19, 1, 0)

    after_workday = JobSubscriptionService.next_run_time(
        "weekdays", "09:00", None, now=datetime(2026, 10, 16, 2, 30, tzinfo=timezone.utc)
    )
    assert after_workday == datetime(2026, 10, 19, 1, 0)

    after_interval = JobSubscriptionService.next_run_time(
        "interval", "09:00", None, 5, now=datetime(2026, 10, 12, 1, 30, tzinfo=timezone.utc)
    )
    assert after_interval == datetime(2026, 10, 17, 1, 0)

    monthly_at_month_end = JobSubscriptionService.next_run_time(
        "monthly", "09:00", None, None, 31,
        now=datetime(2027, 2, 28, 0, 30, tzinfo=timezone.utc),
    )
    assert monthly_at_month_end == datetime(2027, 2, 28, 1, 0)

    next_month = JobSubscriptionService.next_run_time(
        "monthly", "09:00", None, None, 31,
        now=datetime(2027, 2, 28, 2, 0, tzinfo=timezone.utc),
    )
    assert next_month == datetime(2027, 3, 31, 1, 0)

    assert JobSubscriptionService.next_run_time("manual", "09:00", None) is None


def test_daily_schedule_accepts_custom_minute_and_scheduler_aligns_to_minute():
    next_run = JobSubscriptionService.next_run_time(
        "daily", "08:35", None, now=datetime(2026, 10, 12, 0, 14, 30, tzinfo=timezone.utc)
    )
    assert next_run == datetime(2026, 10, 12, 0, 35)
    assert next_run.second == 0 and next_run.microsecond == 0
    assert JobSubscriptionScheduler.seconds_until_next_minute(
        datetime(2026, 10, 12, 8, 35, 59, 750_000)
    ) == pytest.approx(0.25)


def test_due_scheduler_runs_enabled_subscription_and_advances_next_run(tmp_path, monkeypatch):
    client, engine = make_client(tmp_path)
    monkeypatch.setitem(
        subscription_endpoints.service.search_service.providers,
        "job_pro",
        FakeJobProvider([sample_job()]),
    )
    subscription = make_subscription(client, frequency="daily")
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    session = factory()
    record = session.get(JobSubscription, subscription["id"])
    assert record is not None
    record.next_run_at = JobSubscriptionService.now_utc_naive().replace(microsecond=0)
    session.commit()
    session.close()

    assert subscription_endpoints.service.run_due(factory) == 1
    session = factory()
    try:
        run = session.query(JobSubscriptionRun).filter_by(subscription_id=subscription["id"]).one()
        updated = session.get(JobSubscription, subscription["id"])
        assert run.trigger == "scheduled"
        assert run.status == "succeeded"
        assert updated is not None and updated.next_run_at is not None
        assert updated.next_run_at > JobSubscriptionService.now_utc_naive()
    finally:
        session.close()


@pytest.mark.parametrize(
    ("frequency", "schedule_options"),
    [
        ("weekdays", {}),
        ("weekly", {}),
        ("interval", {"interval_days": 5}),
        ("monthly", {"month_day": 15}),
    ],
)
def test_due_scheduler_runs_each_added_frequency(tmp_path, monkeypatch, frequency, schedule_options):
    client, engine = make_client(tmp_path)
    monkeypatch.setitem(
        subscription_endpoints.service.search_service.providers,
        "job_pro",
        FakeJobProvider([sample_job()]),
    )
    subscription = make_subscription(
        client, frequency=frequency, schedule_options=schedule_options
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    session = factory()
    record = session.get(JobSubscription, subscription["id"])
    assert record is not None
    record.next_run_at = JobSubscriptionService.now_utc_naive().replace(microsecond=0)
    session.commit()
    session.close()

    assert subscription_endpoints.service.run_due(factory) == 1
    session = factory()
    try:
        run = session.query(JobSubscriptionRun).filter_by(subscription_id=subscription["id"]).one()
        updated = session.get(JobSubscription, subscription["id"])
        assert run.trigger == "scheduled"
        assert run.status == "succeeded"
        assert updated is not None and updated.next_run_at is not None
        assert updated.next_run_at > JobSubscriptionService.now_utc_naive()
    finally:
        session.close()


def test_due_scheduler_cleans_expired_previews_but_keeps_run_history(tmp_path, monkeypatch):
    client, engine = make_client(tmp_path)
    monkeypatch.setitem(
        subscription_endpoints.service.search_service.providers,
        "job_pro",
        FakeJobProvider([sample_job()]),
    )
    subscription = make_subscription(client)
    run_response = client.post(f"/api/v1/subscriptions/{subscription['id']}/runs")
    assert run_response.status_code == 200, run_response.text
    run_id = run_response.json()["id"]

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)
    session = factory()
    try:
        item = session.query(JobSubscriptionRunItem).filter_by(run_id=run_id).one()
        expired_at = datetime.utcnow() - timedelta(days=31)
        item.created_at = expired_at
        run = session.get(JobSubscriptionRun, run_id)
        assert run is not None
        run.started_at = expired_at
        run.completed_at = expired_at
        session.commit()
    finally:
        session.close()

    assert subscription_endpoints.service.run_due(factory) == 0
    session = factory()
    try:
        assert session.get(JobSubscriptionRun, run_id) is not None
        assert session.query(JobSubscriptionRunItem).filter_by(run_id=run_id).count() == 0
    finally:
        session.close()

    detail = client.get(f"/api/v1/subscriptions/{subscription['id']}/runs/{run_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["preview_expired"] is True
