import json
from datetime import date

import pytest

from api.v1.schemas.jobs import JobSearchRequest
from src.config import Settings
from src.data_provider.base import JobRecord
from src.data_provider.boss_agent_provider import BossAgentProvider
from src.data_provider.job_pro_provider import JobProProvider, resolve_job_pro_cli
from src.data_provider.manual_import_provider import InvalidJobLink, ManualImportProvider, PageTransportError
from src.services.job_service import JobProviderUnavailable, JobSearchService
from src.data_provider.manual_import_provider import JobPage
from src.schemas.job_import import JobPageExtraction
from src.services.job_service import InvalidImport
from src.services.boss_cli import BossCliInspection


def compatible_boss_inspection(executable="/usr/local/bin/boss"):
    return BossCliInspection(
        executable=executable,
        version="3.0.0",
        root_options=frozenset({"--browser-source", "--cdp-url", "--json"}),
        search_options=frozenset({"--job-type", "--no-cache", "--city"}),
        login_options=frozenset({"--cdp", "--timeout"}),
    )


def test_boss_payload_is_normalized_without_network():
    record = BossAgentProvider._to_record(
        {
            "security_id": "boss-1",
            "title": "Python 后端实习生",
            "company": "示例公司",
            "city": "上海",
            "url": "https://www.zhipin.com/job_detail/boss-1.html",
            "salary": "200-300元/天",
            "date": "2026-09-18",
        },
        city="上海",
    )
    assert record.source_job_id == "boss-1"
    assert record.salary_min == 200
    assert record.salary_max == 300
    assert record.published_date == date(2026, 9, 18)
    assert record.extraction_method == "boss_agent_cli"


def test_boss_search_row_without_url_gets_public_detail_link():
    record = BossAgentProvider._to_record(
        {
            "security_id": "security-1",
            "job_id": "encrypted-job-1",
            "title": "后端开发实习生",
            "company": "示例公司",
            "city": "杭州",
            "salary": "200-300元/天",
        },
        city="杭州",
    )

    assert record.detail_url == "https://www.zhipin.com/job_detail/encrypted-job-1.html"
    assert BossAgentProvider._valid_row(record.raw_payload or {}) is True


def test_boss_camel_case_payload_is_normalized():
    record = BossAgentProvider._to_record(
        {
            "encryptJobId": "encoded-987",
            "jobName": "Agent 开发实习生",
            "brandName": "示例 AI 公司",
            "cityName": "杭州",
            "salaryDesc": "250-350元/天",
            "publishTime": "2026-10-08",
            "jobDegree": "本科",
            "jobDescription": "负责 Agent 产品研发",
            "jobExperience": "了解 Python",
        },
        city="杭州",
    )

    assert record.source_job_id == "encoded-987"
    assert record.title == "Agent 开发实习生"
    assert record.company_name == "示例 AI 公司"
    assert record.city == "杭州"
    assert record.detail_url.endswith("/encoded-987.html")
    assert record.salary_min == 250
    assert record.published_date == date(2026, 10, 8)
    assert record.education == "本科"
    assert record.description == "负责 Agent 产品研发"
    assert record.requirements == "了解 Python"


def test_boss_code_37_enters_cooldown(monkeypatch):
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args[0])
        return type(
            "Completed",
            (),
            {
                "returncode": 1,
                "stdout": json.dumps(
                    {"ok": False, "error": {"code": 37, "message": "您的环境存在异常"}},
                    ensure_ascii=False,
                ),
                "stderr": "",
            },
        )()

    monkeypatch.setattr(
        "src.data_provider.boss_agent_provider.inspect_boss_cli",
        lambda _: compatible_boss_inspection(),
    )
    monkeypatch.setattr("src.data_provider.boss_agent_provider.subprocess.run", fake_run)
    provider = BossAgentProvider(Settings(boss_risk_cooldown_seconds=60))

    with pytest.raises(RuntimeError, match="code 37"):
        provider.search(keyword="后端", city="上海")
    with pytest.raises(RuntimeError, match="冷却"):
        provider.search(keyword="后端", city="杭州")
    assert len(calls) == 1


def test_boss_search_uses_fresh_internship_json_command(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return type("Completed", (), {"returncode": 0, "stdout": '{"ok":true,"data":[]}', "stderr": ""})()

    monkeypatch.setattr(
        "src.data_provider.boss_agent_provider.inspect_boss_cli",
        lambda _: compatible_boss_inspection(),
    )
    monkeypatch.setattr("src.data_provider.boss_agent_provider.subprocess.run", fake_run)
    provider = BossAgentProvider(Settings(boss_cli_command="boss", boss_browser_source="existing-browser"))

    assert provider.search(keyword="Agent 开发", city="杭州") == []
    command = calls[0]
    assert command[:6] == [
        "/usr/local/bin/boss",
        "--browser-source",
        "existing-browser",
        "--cdp-url",
        "http://127.0.0.1:9222",
        "--json",
    ]
    assert command[6:] == [
        "search",
        "Agent 开发",
        "--job-type",
        "实习",
        "--no-cache",
        "--city",
        "杭州",
    ]


def test_boss_code_37_stops_remaining_city_requests():
    calls = []

    class RiskProvider:
        def search(self, *, keyword=None, city=None):
            calls.append(city)
            raise RuntimeError("BOSS 直聘访问环境风控 (code 37)")

    service = JobSearchService(
        providers={"boss_agent_cli": RiskProvider()},
        settings=Settings(job_provider="boss_agent_cli"),
    )
    request = JobSearchRequest(
        cities=["上海", "杭州"],
        providers=["boss_agent_cli"],
        published_range="all",
    )

    with pytest.raises(JobProviderUnavailable) as exc_info:
        service.search(None, request)
    assert calls == ["上海"]
    assert "上海" in exc_info.value.quality[0]["error"]
    assert "杭州" not in exc_info.value.quality[0]["error"]


def test_job_pro_payload_is_normalized_and_city_filtered():
    payload = {
        "ok": True,
        "results": [
            {
                "company": "bytedance",
                "ok": True,
                "positions": [
                    {
                        "post_id": "7675681181492807941",
                        "title": "后端开发实习生 - Seed",
                        "project": "后端",
                        "recruit_label": "实习",
                        "work_cities": "深圳 北京",
                        "apply_url": "https://jobs.bytedance.com/campus/position/7675681181492807941/detail",
                    }
                ],
            }
        ],
        "failed": [],
    }

    rows = JobProProvider._find_rows(payload)
    assert len(rows) == 1
    company, row = rows[0]
    record = JobProProvider._to_record(row, company=company, city="北京")
    assert record is not None
    assert record.company_name == "字节跳动"
    assert record.city == "北京"
    assert record.published_date is None
    assert record.salary_status == "unknown"
    assert record.extraction_method == "job_pro"

    assert JobProProvider._to_record(row, company=company, city="杭州") is None


def test_resolve_job_pro_cli_anchors_relative_path_to_project_root(tmp_path, monkeypatch):
    binary = tmp_path / ".tools" / "job-pro" / "node_modules" / ".bin" / "job-pro"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr("src.data_provider.job_pro_provider.PROJECT_ROOT", tmp_path)

    assert resolve_job_pro_cli("./.tools/job-pro/node_modules/.bin/job-pro") == str(binary.resolve())


def test_resolve_job_pro_cli_rejects_non_executable_project_path(tmp_path, monkeypatch):
    binary = tmp_path / ".tools" / "job-pro"
    binary.parent.mkdir(parents=True)
    binary.write_text("not executable", encoding="utf-8")
    monkeypatch.setattr("src.data_provider.job_pro_provider.PROJECT_ROOT", tmp_path)

    assert resolve_job_pro_cli("./.tools/job-pro") is None


def test_job_pro_search_uses_public_cli_and_reports_missing_binary(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps(
                    {
                        "ok": True,
                        "results": [
                            {
                                "company": "tencent",
                                "ok": True,
                                "positions": [
                                    {
                                        "post_id": "t-1",
                                        "title": "后台开发",
                                        "work_cities": "上海",
                                        "apply_url": "https://join.qq.com/post_detail.html?postid=t-1",
                                    }
                                ],
                            }
                        ],
                        "failed": [],
                    },
                    ensure_ascii=False,
                ),
                "stderr": "",
            },
        )()

    monkeypatch.setattr("src.data_provider.job_pro_provider.resolve_job_pro_cli", lambda _: "/usr/local/bin/job-pro")
    monkeypatch.setattr("src.data_provider.job_pro_provider.subprocess.run", fake_run)
    provider = JobProProvider(Settings(job_pro_companies="tencent"))
    records = provider.search(keyword="后端", city="上海", company="腾讯")

    assert records[0].source_job_id == "tencent:t-1"
    assert calls[0][0][:3] == ["/usr/local/bin/job-pro", "find", "后端"]
    assert "--scope" in calls[0][0]
    assert "--companies" in calls[0][0]
    assert calls[0][0][calls[0][0].index("--companies") + 1] == "tencent"


def test_job_pro_company_catalog_and_default_scope_include_all_fifty_sources():
    settings = Settings(_env_file=None)
    assert settings.job_pro_command == "./.tools/job-pro/node_modules/.bin/job-pro"
    configured = settings.job_pro_companies.split(",")
    assert len(configured) == 50
    assert configured == list(JobProProvider.COMPANY_NAMES)
    assert JobProProvider.COMPANY_NAMES["unitree"] == "宇树科技"
    assert JobProProvider.COMPANY_NAMES["hoyoverse"] == "米哈游国际"
    assert JobProProvider.company_id("中金") == "cicc"


def test_job_pro_can_search_a_specific_company_and_city(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": json.dumps({
                    "ok": True,
                    "results": [{
                        "company": "xiaohongshu",
                        "ok": True,
                        "positions": [{
                            "post_id": "xhs-agent-1",
                            "title": "Agent 开发实习生",
                            "work_cities": "杭州 上海",
                            "apply_url": "https://job.xiaohongshu.com/position/xhs-agent-1",
                        }],
                    }],
                    "failed": [],
                }, ensure_ascii=False),
                "stderr": "",
            },
        )()

    monkeypatch.setattr("src.data_provider.job_pro_provider.resolve_job_pro_cli", lambda _: "/usr/local/bin/job-pro")
    monkeypatch.setattr("src.data_provider.job_pro_provider.subprocess.run", fake_run)
    provider = JobProProvider(Settings(job_pro_companies="xiaohongshu,didi"))

    records = provider.search(keyword="Agent 开发", city="杭州", company="小红书")

    assert len(records) == 1
    assert records[0].company_name == "小红书"
    assert records[0].city == "杭州"
    assert calls[0][calls[0].index("--companies") + 1] == "xiaohongshu"


def test_job_pro_rejects_company_outside_configured_sources():
    provider = JobProProvider(Settings(_env_file=None, job_pro_companies="didi"))
    with pytest.raises(RuntimeError, match="未包含在 JOB_PRO_COMPANIES"):
        provider.search(keyword="Agent", company="小红书")


def test_job_pro_multi_city_search_uses_one_company_scan():
    calls = []

    class CountingProvider:
        def search(self, *, keyword=None, city=None):
            calls.append(city)
            return [
                JobRecord(
                    source_job_id=f"post-{location}",
                    title="后端开发实习生",
                    company_name="字节跳动",
                    city=location,
                    detail_url=f"https://jobs.example.com/{location}",
                    published_date=None,
                )
                for location in ("上海", "杭州")
            ]

    service = JobSearchService(
        providers={"job_pro": CountingProvider()},
        settings=Settings(job_provider="job_pro"),
    )
    result = service.search(
        None,
        JobSearchRequest(cities=["上海", "杭州"], providers=["job_pro"], published_range="all"),
    )

    assert calls == [None]
    assert {item["city"] for item in result["items"]} == {"上海", "杭州"}


def test_job_search_pagination_reuses_first_page_provider_results():
    class CountingProvider:
        calls = 0

        def search(self, *, keyword=None, city=None):
            self.calls += 1
            return [
                JobRecord(
                    source_job_id=f"post-{index}",
                    title=f"后端开发实习生 {index}",
                    company_name="示例科技",
                    city="上海",
                    detail_url=f"https://jobs.example.com/{index}",
                    published_date=None,
                )
                for index in range(3)
            ]

    provider = CountingProvider()
    service = JobSearchService(
        providers={"example": provider},
        settings=Settings(job_provider="example"),
    )
    first = service.search(
        None,
        JobSearchRequest(keyword="后端", cities=["上海"], providers=["example"], page=1, limit=1),
    )
    second = service.search(
        None,
        JobSearchRequest(keyword="后端", cities=["上海"], providers=["example"], page=2, limit=1),
    )

    assert provider.calls == 1
    assert first["total"] == second["total"] == 3
    assert first["items"][0]["title"].endswith("0")
    assert second["items"][0]["title"].endswith("1")


def test_manual_import_extracts_public_json_ld_job_posting():
    html = """
    <html><head><title>岗位详情</title>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting","title":"后端开发实习生",
     "datePosted":"2026-09-18","hiringOrganization":{"name":"示例科技"},
     "jobLocation":{"address":{"addressLocality":"上海"}},
     "description":"参与后端岗位开发和招聘工作。","qualifications":"熟悉 Python。"}
    </script></head><body><h1>后端开发实习生</h1></body></html>
    """
    record = ManualImportProvider()._extract("https://example.com/jobs/1", html)
    assert record.title == "后端开发实习生"
    assert record.company_name == "示例科技"
    assert record.city == "上海"
    assert record.published_date == date(2026, 9, 18)
    assert record.extraction_method == "json_ld"


def test_manual_import_rejects_private_and_non_job_links():
    provider = ManualImportProvider()
    try:
        provider._validate_url("http://127.0.0.1:8000/jobs/1")
    except InvalidJobLink as exc:
        assert "本机" in str(exc)
    else:
        raise AssertionError("private URL should be rejected")

    try:
        provider._extract("https://example.com/about", "<html><title>公司介绍</title><p>关于我们</p></html>")
    except InvalidJobLink as exc:
        assert "岗位" in str(exc)
    else:
        raise AssertionError("non-job page should be rejected")


def test_manual_import_uses_rendered_public_page_when_static_html_is_only_shell(monkeypatch):
    url = "https://campus.example.com/position/42"
    shell = JobPage(
        requested_url=url,
        final_url=url,
        html="<html><head><title>校园招聘</title></head><body><div id='app'></div></body></html>",
        title="校园招聘",
        body_text="",
        metadata={},
        json_ld=[],
    )
    rendered = JobPage(
        requested_url=url,
        final_url=url,
        html="<html><body><h1>算法实习生</h1></body></html>",
        title="招聘详情",
        body_text=(
            "岗位名称：算法实习生。工作城市：杭州。岗位职责：参与大模型应用研发和算法验证，"
            "协助团队处理模型数据。任职要求：熟悉 Python，具备机器学习相关项目经验。"
            "实习期间需要按照团队安排参与研发任务并配合完成技术文档。"
        ),
        metadata={},
        json_ld=[],
        rendered=True,
    )
    provider = ManualImportProvider(browser_renderer=lambda _: rendered)
    monkeypatch.setattr(provider, "_fetch_static", lambda _: shell)

    result = provider.fetch_page(url)

    assert result.rendered is True
    assert "参与大模型应用研发" in result.body_text


def test_manual_import_waits_for_job_detail_signal_within_timeout_budget():
    class FakePage:
        call = None

        def wait_for_function(self, expression, *, polling, timeout):
            self.call = (expression, polling, timeout)

    page = FakePage()

    ManualImportProvider._wait_for_job_details(page, remaining_timeout_ms=12_000)

    expression, polling, timeout = page.call
    assert "职位描述" in expression
    assert "responsibilities" in expression
    assert polling == 250
    assert timeout == ManualImportProvider.MAX_JOB_CONTENT_WAIT_MS


def test_manual_import_does_not_wait_when_import_timeout_is_exhausted():
    class FakePage:
        called = False

        def wait_for_function(self, *_args, **_kwargs):
            self.called = True

    page = FakePage()

    ManualImportProvider._wait_for_job_details(page, remaining_timeout_ms=0)

    assert page.called is False


def test_manual_import_restricts_same_origin_posts_to_job_detail_reads():
    allow = ManualImportProvider._is_allowed_public_job_detail_post
    page_url = "https://jobs.example.com/position/42"
    body = json.dumps({"positionId": "42"})

    assert allow(
        method="POST",
        resource_type="xhr",
        request_url="https://jobs.example.com/api/position/detail",
        page_url=page_url,
        post_data=body,
    )
    assert not allow(
        method="POST",
        resource_type="xhr",
        request_url="https://jobs.example.com/api/position/apply",
        page_url=page_url,
        post_data=body,
    )
    assert not allow(
        method="POST",
        resource_type="document",
        request_url="https://jobs.example.com/api/position/detail",
        page_url=page_url,
        post_data=body,
    )
    assert not allow(
        method="POST",
        resource_type="fetch",
        request_url="https://jobs.example.com/api/position/detail",
        page_url=page_url,
        post_data="x" * (ManualImportProvider.MAX_BROWSER_POST_BYTES + 1),
    )
    assert not allow(
        method="DELETE",
        resource_type="xhr",
        request_url="https://jobs.example.com/api/position/42",
        page_url=page_url,
        post_data=None,
    )


def test_manual_import_allows_bounded_same_site_job_detail_posts_across_companies():
    allow = ManualImportProvider._is_allowed_public_job_detail_post

    # Ant's public position page is one example of a same-site, cross-subdomain detail API.
    assert allow(
        method="POST",
        resource_type="fetch",
        request_url="https://hrcareersweb.antgroup.com/api/campus/position/detail",
        page_url="https://talent.antgroup.com/campus-position?positionId=260721010986440",
        post_data=json.dumps(
            {"channel": "campus_group_official_site", "language": "zh", "id": 260721010986440}
        ),
    )
    # The same generic policy also supports unrelated company domains and common ID conventions.
    assert allow(
        method="POST",
        resource_type="xhr",
        request_url="https://api.example.cn/api/jobs/getDetail",
        page_url="https://careers.example.cn/job/42",
        post_data=json.dumps({"jobId": "42", "locale": "zh-CN"}),
    )
    assert allow(
        method="POST",
        resource_type="fetch",
        request_url="https://api.example.co.uk/api/recruitment/detail",
        page_url="https://careers.example.co.uk/jobs/42",
        post_data=json.dumps({"positionCode": "42"}),
    )
    assert allow(
        method="POST",
        resource_type="fetch",
        request_url="https://api.example.com/api/job/detail?id=42",
        page_url="https://careers.example.com/jobs/42",
        post_data=None,
    )

    common_args = {
        "method": "POST",
        "resource_type": "fetch",
        "request_url": "https://api.example.com/api/jobs/detail",
        "page_url": "https://careers.example.com/jobs/42",
        "post_data": json.dumps({"jobId": "42"}),
    }
    assert not allow(**{**common_args, "request_url": "https://api.other.com/api/jobs/detail"})
    assert not allow(**{**common_args, "request_url": "https://api.other.com.cn/api/jobs/detail"})
    assert not allow(**{**common_args, "request_url": "https://api.example.com/api/user/detail"})
    assert not allow(**{**common_args, "request_url": "https://api.example.com/api/job/apply"})
    assert not allow(
        **{
            **common_args,
            "post_data": json.dumps({"jobId": "42", "action": "apply"}),
        }
    )
    assert not allow(**{**common_args, "resource_type": "document"})
    assert not allow(**{**common_args, "method": "DELETE"})
    assert not allow(
        **{
            **common_args,
            "post_data": "x" * (ManualImportProvider.MAX_BROWSER_POST_BYTES + 1),
        }
    )


def test_job_import_accepts_short_citation_for_verbatim_long_field_only():
    body = "职位描述：负责智能体平台研发，参与模型应用落地并完成技术文档。"
    long_value = "负责智能体平台研发，参与模型应用落地并完成技术文档。"
    short_citation = "负责智能体平台研发"

    assert JobSearchService._is_evidence_supported(long_value, short_citation, body)
    assert not JobSearchService._is_evidence_supported(
        "负责智能体平台研发，并独立管理十人团队。",
        short_citation,
        body,
    )
    assert not JobSearchService._is_evidence_supported(long_value, "页面没有这段引用", body)


def test_manual_import_can_use_normal_browser_after_transport_failure(monkeypatch):
    url = "https://campus.example.com/position/42"
    rendered = JobPage(
        requested_url=url,
        final_url=url,
        html="<html><body><h1>算法实习生</h1></body></html>",
        title="算法实习生",
        body_text=(
            "岗位名称：算法实习生。工作城市：杭州。岗位职责：参与大模型应用研发和算法验证，"
            "协助团队处理模型数据。任职要求：熟悉 Python，具备机器学习相关项目经验。"
            "实习期间需要按照团队安排参与研发任务并配合完成技术文档。"
        ),
        metadata={},
        json_ld=[],
        rendered=True,
    )
    provider = ManualImportProvider(browser_renderer=lambda _: rendered)

    def fail_static(_):
        raise PageTransportError("test DNS failure")

    monkeypatch.setattr(provider, "_fetch_static", fail_static)

    result = provider.fetch_page(url)

    assert result.rendered is True
    assert result.body_text == rendered.body_text


def test_job_link_llm_extracts_only_page_evidence_and_keeps_preview_ephemeral():
    url = "https://jobs.example.com/position/42"
    page_text = (
        "岗位名称：AI算法实习生 公司：示例科技 工作城市：杭州\n"
        "岗位职责：参与大模型应用研发，负责算法验证和数据处理。\n"
        "任职要求：熟悉 Python，有机器学习项目经验。\n"
        "发布日期：2026-04-01 联系电话：13800138000"
    )
    page = JobPage(
        requested_url=url,
        final_url=url,
        html="<html><body></body></html>",
        title="招聘职位",
        body_text=page_text,
        metadata={},
        json_ld=[],
    )

    class FakeImporter:
        def fetch_page(self, _: str) -> JobPage:
            return page

        @staticmethod
        def extract_job_posting(_: JobPage):
            return None

    class FakeLLM:
        def generate_structured(self, *, prompt, response_type, system_prompt=None):
            assert "不可信数据" in system_prompt
            assert "13800138000" not in prompt
            assert "[手机号已脱敏]" in prompt
            return response_type(
                is_job_posting=True,
                confidence=0.94,
                title="AI算法实习生",
                company_name="示例科技",
                city="杭州",
                job_type="实习生",
                published_date=date(2026, 4, 1),
                salary_status="unknown",
                description="参与大模型应用研发，负责算法验证和数据处理。",
                requirements="熟悉 Python，有机器学习项目经验。",
                field_evidence={
                    "title": "岗位名称：AI算法实习生",
                    "company_name": "公司：示例科技",
                    "city": "工作城市：杭州",
                    "job_type": "岗位名称：AI算法实习生",
                    "published_date": "发布日期：2026-04-01",
                    "description": "岗位职责：参与大模型应用研发，负责算法验证和数据处理。",
                    "requirements": "任职要求：熟悉 Python，有机器学习项目经验。",
                },
            )

    service = JobSearchService(settings=Settings(litellm_model="test/mock"), llm_adapter=FakeLLM())
    service.import_provider = FakeImporter()

    preview = service.preview_import(url)

    assert preview["job"]["title"] == "AI算法实习生"
    assert preview["job"]["company_name"] == "示例科技"
    assert preview["job"]["city"] == "杭州"
    assert preview["job"]["published_date"] == date(2026, 4, 1)
    assert preview["job"]["extraction_method"] == "llm_text"
    assert preview["job"]["is_saved"] is False
    assert any("模型" in warning for warning in preview["warnings"])


def test_job_link_llm_rejects_fields_without_source_evidence():
    url = "https://jobs.example.com/position/42"
    page = JobPage(
        requested_url=url,
        final_url=url,
        html="",
        title="招聘",
        body_text=(
            "本页面只介绍校园招聘流程，没有具体职位信息。页面说明了公司文化、招聘活动安排、"
            "宣讲会时间、校招流程和常见问题，没有任何具体岗位名称、工作职责或任职资格。"
            "页面里也没有具体岗位的报名条件、工作城市、薪酬范围或岗位描述，不能作为单个招聘职位详情。"
        ),
        metadata={},
        json_ld=[],
    )

    class FakeImporter:
        def fetch_page(self, _: str) -> JobPage:
            return page

        @staticmethod
        def extract_job_posting(_: JobPage):
            return None

    class HallucinatingLLM:
        def generate_structured(self, *, prompt, response_type, system_prompt=None):
            return response_type(
                is_job_posting=True,
                confidence=0.99,
                title="高级算法实习生",
                company_name="虚构科技",
                description="负责大模型算法研发。",
                field_evidence={
                    "title": "校园招聘流程",
                    "company_name": "校园招聘流程",
                    "description": "本页面只介绍校园招聘流程",
                },
            )

    service = JobSearchService(llm_adapter=HallucinatingLLM())
    service.import_provider = FakeImporter()

    with pytest.raises(InvalidImport, match="具体岗位详情"):
        service.preview_import(url)


def test_confirm_import_requires_identified_title_and_company():
    url = "https://jobs.example.com/position/42"
    record = JobRecord(
        source_job_id="42",
        title="算法实习生",
        company_name="",
        city="杭州",
        detail_url=url,
        published_date=None,
        description="岗位职责内容",
        extraction_method="llm_text",
    )

    class FakeImporter:
        def fetch(self, _: str) -> JobRecord:
            return record

    service = JobSearchService()
    service.import_provider = FakeImporter()
    preview = service.preview_import(url)

    with pytest.raises(InvalidImport, match="岗位名称和公司名称"):
        service.confirm_import(None, preview["preview_token"], {})
