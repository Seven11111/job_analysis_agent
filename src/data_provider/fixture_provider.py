"""Offline provider for deterministic Phase 1 development and demos."""

from __future__ import annotations

from datetime import date, timedelta

from src.data_provider.base import JobRecord


class FixtureProvider:
    provider_name = "fixture"

    def _records(self) -> list[JobRecord]:
        today = date.today()
        return [
            JobRecord(
                source_job_id="fixture-sh-001",
                title="Python 后端开发实习生",
                company_name="示例科技",
                city="上海",
                district="浦东新区",
                detail_url="https://fixture.local/jobs/fixture-sh-001",
                published_date=today - timedelta(days=2),
                salary_status="undisclosed",
                education="本科",
                internship_months=3,
                days_per_week=4,
                conversion_chance="unknown",
                description="参与后端服务开发，使用 Python 构建业务 API 和数据处理能力。",
                requirements="熟悉 Python；了解 FastAPI、SQL 或其他后端框架。",
                responsibilities="参与接口开发、测试和线上问题排查。",
            ),
            JobRecord(
                source_job_id="fixture-sh-002",
                title="AI 应用开发实习生",
                company_name="示例 AI",
                city="上海",
                district="徐汇区",
                detail_url="https://fixture.local/jobs/fixture-sh-002",
                published_date=today - timedelta(days=1),
                salary_min=180,
                salary_max=260,
                salary_unit="元/天",
                salary_status="disclosed",
                education="本科",
                internship_months=3,
                days_per_week=4,
                conversion_chance="possible",
                description="参与 LLM 应用和智能工作流的工程实现。",
                requirements="了解 Python、HTTP API 和基础机器学习概念。",
                responsibilities="参与 Prompt、工具调用和评测链路开发。",
            ),
            JobRecord(
                source_job_id="fixture-hz-001",
                title="数据分析实习生",
                company_name="示例互联网",
                city="杭州",
                district="滨江区",
                detail_url="https://fixture.local/jobs/fixture-hz-001",
                published_date=today - timedelta(days=6),
                salary_min=150,
                salary_max=220,
                salary_unit="元/天",
                salary_status="disclosed",
                education="本科",
                internship_months=3,
                days_per_week=5,
                conversion_chance="unknown",
                description="支持业务数据分析、指标建设和可视化。",
                requirements="熟悉 SQL；会使用 Python 或 BI 工具。",
                responsibilities="参与数据清洗、报表和分析结论输出。",
            ),
            JobRecord(
                source_job_id="fixture-bj-001",
                title="Java 服务端实习生",
                company_name="示例云服务",
                city="北京",
                district="海淀区",
                detail_url="https://fixture.local/jobs/fixture-bj-001",
                published_date=today - timedelta(days=15),
                salary_status="unknown",
                education="本科",
                internship_months=6,
                days_per_week=5,
                conversion_chance="yes",
                description="参与云服务平台的 Java 后端研发。",
                requirements="熟悉 Java 基础和常见数据结构。",
                responsibilities="参与服务开发、接口联调和自动化测试。",
            ),
        ]

    def search(self, *, keyword: str | None = None, city: str | None = None) -> list[JobRecord]:
        records = self._records()
        normalized_keyword = keyword.strip().lower() if keyword else None
        normalized_city = city.strip().lower() if city else None
        return [
            record
            for record in records
            if (not normalized_keyword or normalized_keyword in f"{record.title} {record.company_name}".lower())
            and (not normalized_city or normalized_city in record.city.lower())
        ]
