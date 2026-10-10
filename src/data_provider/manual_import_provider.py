"""Fetch public job pages and extract trusted, structured JobPosting data."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

from src.config import Settings, get_settings
from src.data_provider.base import JobRecord


class InvalidJobLink(ValueError):
    """Raised when a URL is not a usable public job posting."""


class PageTransportError(InvalidJobLink):
    """Raised for network transport failures where a normal browser may differ."""


@dataclass(frozen=True)
class JobPage:
    requested_url: str
    final_url: str
    html: str
    title: str
    body_text: str
    metadata: dict[str, str]
    json_ld: list[Any]
    rendered: bool = False


class _PageParser(HTMLParser):
    """Read visible-ish body text, page metadata, headings, and JSON-LD."""

    _SKIP_TAGS = {"style", "noscript", "template", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.headings: list[str] = []
        self.text_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.json_ld: list[Any] = []
        self._tag = ""
        self._in_body = False
        self._skip_depth = 0
        self._script_type = ""
        self._script_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attributes = {key.lower(): value or "" for key, value in attrs}
        self._tag = normalized_tag
        if normalized_tag == "body":
            self._in_body = True
        if normalized_tag == "meta":
            key = attributes.get("property") or attributes.get("name")
            if key and attributes.get("content"):
                self.meta[key.lower()] = attributes["content"]
        if normalized_tag == "script":
            self._script_type = attributes.get("type", "").lower()
            self._script_buffer = []
        elif normalized_tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "script" and "ld+json" in self._script_type:
            try:
                self.json_ld.append(json.loads("".join(self._script_buffer)))
            except (json.JSONDecodeError, TypeError):
                pass
        if normalized_tag == "script":
            self._script_type = ""
            self._script_buffer = []
        elif normalized_tag in self._SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif normalized_tag == "body":
            self._in_body = False
        self._tag = ""

    def handle_data(self, data: str) -> None:
        if self._script_type:
            if "ld+json" in self._script_type:
                self._script_buffer.append(data)
            return
        if self._skip_depth:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self._tag == "title":
            self.title = f"{self.title} {value}".strip()
        if self._in_body:
            if self._tag in {"h1", "h2", "h3"}:
                self.headings.append(value)
            self.text_parts.append(value)


class ManualImportProvider:
    """Read user-supplied public pages without authenticating or bypassing controls."""

    provider_name = "manual_link"
    MAX_REDIRECTS = 5
    MAX_PAGE_BYTES = 5 * 1024 * 1024
    MAX_VISIBLE_TEXT = 24_000
    MAX_BROWSER_POST_BYTES = 64 * 1024
    MULTI_LABEL_PUBLIC_SUFFIXES = {
        "ac.cn", "com.cn", "edu.cn", "gov.cn", "net.cn", "org.cn",
        "com.hk", "edu.hk", "gov.hk", "net.hk", "org.hk",
        "com.tw", "edu.tw", "gov.tw", "net.tw", "org.tw",
        "co.uk", "gov.uk", "ltd.uk", "me.uk", "org.uk", "plc.uk",
        "ac.uk", "net.uk", "sch.uk",
        "com.au", "edu.au", "gov.au", "net.au", "org.au", "asn.au", "id.au",
        "co.jp", "ac.jp", "go.jp", "ne.jp", "or.jp",
        "co.kr", "ac.kr", "go.kr", "or.kr",
        "com.sg", "edu.sg", "gov.sg", "net.sg", "org.sg",
        "com.my", "edu.my", "gov.my", "net.my", "org.my",
        "co.nz", "ac.nz", "govt.nz", "net.nz", "org.nz",
        "com.br", "edu.br", "gov.br", "net.br", "org.br",
        "com.mx", "edu.mx", "gob.mx", "net.mx", "org.mx",
        "co.in", "firm.in", "gen.in", "ind.in", "net.in", "org.in",
        "com.tr", "edu.tr", "gov.tr", "net.tr", "org.tr",
        "ac.za", "co.za", "com.za", "gov.za", "net.za", "org.za",
    }
    KNOWN_SINGLE_LABEL_PUBLIC_SUFFIXES = {
        "com", "org", "net", "edu", "gov", "mil", "int", "io", "ai", "app", "dev",
        "tech", "xyz", "online", "site", "cloud", "cn", "hk", "tw", "uk", "au", "jp",
        "kr", "sg", "my", "nz", "br", "mx", "in", "tr", "de", "fr", "es", "it", "nl",
        "be", "ch", "se", "no", "fi", "dk", "pl", "cz", "at", "gr", "pt", "ie", "ca",
        "us", "za", "ar", "cl", "co", "ru", "ua", "id", "th", "vn", "ph", "il", "is",
    }
    JOB_DETAIL_PATH_SEGMENTS = {
        "career", "careers", "job", "jobs", "position", "positions",
        "posting", "postings", "recruit", "recruits", "recruitment",
        "vacancy", "vacancies",
    }
    WRITE_ACTION_PATH_SEGMENTS = {
        "apply", "application", "submit", "save", "delete", "remove", "cancel",
        "login", "logout", "auth", "captcha", "upload", "resume", "favorite",
        "collect", "withdraw", "send", "create", "update", "edit", "subscribe",
    }
    JOB_IDENTIFIER_KEYS = {
        "id", "jobid", "positionid", "postingid", "postid", "careerid", "jobkey",
        "positionkey", "jobcode", "positioncode", "vacancyid", "vacancycode",
        "reqid", "reqno", "requisitionid", "requisitionno",
    }
    SENSITIVE_POST_KEYS = {
        "action", "operation", "method", "token", "password", "authorization",
        "csrf", "submit", "apply", "upload", "resume",
    }
    MAX_JOB_CONTENT_WAIT_MS = 10_000
    JOB_CONTENT_READY_EXPRESSION = """() => {
        const text = (document.body?.innerText || '').replace(/\\s+/g, ' ');
        const hasDetailSection = /(岗位职责|岗位要求|任职要求|职位描述|职位要求|工作职责|工作内容|responsibilities|qualifications|job description|requirements)/i.test(text);
        return text.length >= 300 && hasDetailSection;
    }"""

    def __init__(self, settings: Settings | None = None, *, browser_renderer=None) -> None:
        self.settings = settings or get_settings()
        self._browser_renderer = browser_renderer

    def fetch(self, detail_url: str) -> JobRecord:
        """Compatibility helper for deterministic JSON-LD extraction."""
        page = self.fetch_page(detail_url)
        record = self.extract_job_posting(page)
        if record is None:
            raise InvalidJobLink("页面没有可直接识别的岗位结构化数据，请通过预览流程使用网页正文提取")
        return record

    def fetch_page(self, detail_url: str) -> JobPage:
        self._validate_url(detail_url)
        try:
            page = self._fetch_static(detail_url)
        except PageTransportError as exc:
            # A normal browser may use a different system proxy/network route.
            # This is only a transport fallback; HTTP access-denied/rate-limit
            # responses never reach this branch and are not retried.
            rendered = self._render_public_page(detail_url)
            if rendered and len(rendered.body_text) >= 80:
                return rendered
            raise InvalidJobLink("岗位链接暂时无法读取，请检查网络或来源可用状态") from exc
        if self.extract_job_posting(page) is not None or not self._needs_browser_render(page):
            return page

        rendered = self._render_public_page(page.final_url)
        if rendered and (
            self.extract_job_posting(rendered) is not None
            or not self._needs_browser_render(rendered)
            or len(rendered.body_text) > len(page.body_text)
        ):
            return rendered
        return page

    def _fetch_static(self, detail_url: str) -> JobPage:
        current_url = detail_url
        try:
            with httpx.Client(
                follow_redirects=False,
                timeout=self.settings.import_timeout_seconds,
                headers={
                    "User-Agent": "JobAnalysisAgent/0.1 (personal public-page reader)",
                    "Accept": "text/html,application/xhtml+xml,application/ld+json;q=0.9,*/*;q=0.5",
                },
            ) as client:
                for redirect_count in range(self.MAX_REDIRECTS + 1):
                    self._validate_url(current_url)
                    with client.stream("GET", current_url) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location or redirect_count == self.MAX_REDIRECTS:
                                raise InvalidJobLink("岗位链接重定向次数过多或目标无效")
                            current_url = urljoin(str(response.url), location)
                            continue
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").lower()
                        if "html" not in content_type and "text" not in content_type:
                            raise InvalidJobLink("链接不是可读取的网页岗位页面")
                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > self.MAX_PAGE_BYTES:
                            raise InvalidJobLink("页面内容过大，暂不支持解析")
                        chunks: list[bytes] = []
                        total_bytes = 0
                        for chunk in response.iter_bytes():
                            total_bytes += len(chunk)
                            if total_bytes > self.MAX_PAGE_BYTES:
                                raise InvalidJobLink("页面内容过大，暂不支持解析")
                            chunks.append(chunk)
                        encoding = response.encoding or "utf-8"
                        content = b"".join(chunks).decode(encoding, errors="replace")
                        return self._page_from_html(
                            requested_url=detail_url,
                            final_url=str(response.url),
                            content=content,
                            rendered=False,
                        )
        except InvalidJobLink:
            raise
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {401, 403, 407, 429}:
                raise InvalidJobLink("来源拒绝公开读取或请求过于频繁；请在官方页面确认权限后再试") from exc
            raise InvalidJobLink("岗位链接返回异常状态，请确认链接公开有效") from exc
        except httpx.HTTPError as exc:
            raise PageTransportError("网页网络连接失败") from exc
        except (UnicodeError, ValueError) as exc:
            raise InvalidJobLink("岗位链接暂时无法读取，请确认链接公开有效且来源允许访问") from exc
        raise InvalidJobLink("岗位链接暂时无法读取")

    def _render_public_page(self, detail_url: str) -> JobPage | None:
        """Render a public JS page with ordinary Playwright; never logs in or evades controls."""
        if self._browser_renderer is not None:
            try:
                return self._browser_renderer(detail_url)
            except Exception:
                return None
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return None

        timeout_ms = self.settings.import_timeout_seconds * 1000
        browser = None
        try:
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(channel="chrome", headless=True)
                except Exception:
                    # The standard Playwright Chromium is a normal browser fallback,
                    # not a stealth or anti-bot patched runtime.
                    browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(locale="zh-CN")
                page = context.new_page()

                def guard_request(route) -> None:
                    request_url = route.request.url
                    resource_type = route.request.resource_type
                    method = route.request.method.upper()
                    if method not in {"GET", "HEAD"} and not self._is_allowed_public_job_detail_post(
                        method=method,
                        resource_type=resource_type,
                        request_url=request_url,
                        page_url=page.url,
                        post_data=route.request.post_data,
                    ):
                        route.abort()
                        return
                    if resource_type in {"image", "font", "media"}:
                        route.abort()
                        return
                    if request_url.startswith(("data:", "blob:", "about:")):
                        route.continue_()
                        return
                    try:
                        self._validate_url(request_url)
                        route.continue_()
                    except InvalidJobLink:
                        route.abort()

                page.route("**/*", guard_request)
                render_started_at = time.monotonic()
                response = page.goto(detail_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if response is None or response.status >= 400:
                    return None
                final_url = page.url
                self._validate_url(final_url)
                remaining_timeout_ms = max(
                    0,
                    timeout_ms - int((time.monotonic() - render_started_at) * 1000),
                )
                self._wait_for_job_details(page, remaining_timeout_ms)
                title = page.title()
                body_text = page.locator("body").inner_text(timeout=min(timeout_ms, 5000))
                rendered_html = page.content()
                return self._page_from_html(
                    requested_url=detail_url,
                    final_url=final_url,
                    content=rendered_html,
                    rendered=True,
                    visible_title=title,
                    visible_text=body_text,
                )
        except InvalidJobLink:
            return None
        except Exception:
            # A missing local browser installation or a site that does not render
            # should not turn a readable static page into a server error.
            return None
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass

    @classmethod
    def _wait_for_job_details(cls, page, remaining_timeout_ms: int) -> None:
        """Wait for hydrated job content, within the existing import timeout budget."""
        wait_timeout_ms = min(remaining_timeout_ms, cls.MAX_JOB_CONTENT_WAIT_MS)
        if wait_timeout_ms <= 0:
            return
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

            page.wait_for_function(
                cls.JOB_CONTENT_READY_EXPRESSION,
                polling=250,
                timeout=wait_timeout_ms,
            )
        except PlaywrightTimeoutError:
            # A site may not use recognizable section headings. Read the best
            # content available and let the evidence-based extractor decide.
            return

    @classmethod
    def _is_allowed_public_job_detail_post(
        cls,
        *,
        method: str,
        resource_type: str,
        request_url: str,
        page_url: str,
        post_data: str | None,
    ) -> bool:
        """Allow bounded POSTs for public job-detail reads, never state changes."""
        if method.upper() != "POST" or resource_type not in {"xhr", "fetch"}:
            return False
        if post_data and len(post_data.encode("utf-8")) > cls.MAX_BROWSER_POST_BYTES:
            return False
        request = urlparse(request_url)
        page = urlparse(page_url)
        try:
            request_port = request.port
            page_port = page.port
        except ValueError:
            return False
        if (
            request.scheme != "https"
            or not request.hostname
            or request.fragment
            or request_port not in {None, 443}
            or page.scheme != "https"
            or not page.hostname
            or page.fragment
            or page_port not in {None, 443}
        ):
            return False
        same_origin = cls._origin_key(request_url) == cls._origin_key(page_url)
        if not same_origin:
            request_site = cls._registrable_domain(request.hostname)
            page_site = cls._registrable_domain(page.hostname)
            if not request_site or request_site != page_site:
                return False
        path = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", unquote(request.path))
        path_segments = set(re.findall(r"[a-z0-9]+", path.lower()))
        if (
            not path_segments.intersection(cls.JOB_DETAIL_PATH_SEGMENTS)
            or path_segments.intersection(cls.WRITE_ACTION_PATH_SEGMENTS)
        ):
            return False
        payload: dict[str, Any] = {}
        if post_data:
            try:
                parsed_body = json.loads(post_data)
                if not isinstance(parsed_body, dict):
                    return False
                payload = parsed_body
            except json.JSONDecodeError:
                form_fields = parse_qs(post_data, keep_blank_values=True)
                if not form_fields:
                    return False
                payload = {key: values[0] for key, values in form_fields.items()}
        query_fields = parse_qs(request.query, keep_blank_values=True)
        fields = {**query_fields, **payload}
        normalized_keys = {re.sub(r"[^a-z0-9]", "", str(key).lower()) for key in fields}
        if normalized_keys.intersection(cls.SENSITIVE_POST_KEYS) or any(
            any(marker in key for marker in ("token", "password", "authorization", "cookie"))
            or key.startswith("csrf")
            for key in normalized_keys
        ):
            return False
        identifier_key = next(
            (key for key in fields if re.sub(r"[^a-z0-9]", "", str(key).lower()) in cls.JOB_IDENTIFIER_KEYS),
            None,
        )
        if identifier_key is None:
            return False
        identifier = fields[identifier_key]
        if isinstance(identifier, list):
            identifier = identifier[0] if identifier else None
        if isinstance(identifier, bool) or not isinstance(identifier, (int, str)) or not str(identifier).strip():
            return False
        return True

    @classmethod
    def _registrable_domain(cls, hostname: str) -> str | None:
        """Return a conservative registrable-domain approximation for common public suffixes."""
        normalized = hostname.lower().rstrip(".")
        try:
            ipaddress.ip_address(normalized)
            return normalized
        except ValueError:
            pass
        labels = normalized.split(".")
        if len(labels) < 2:
            return None
        suffix = ".".join(labels[-2:])
        if suffix in cls.MULTI_LABEL_PUBLIC_SUFFIXES:
            suffix_label_count = 2
        elif labels[-1] in cls.KNOWN_SINGLE_LABEL_PUBLIC_SUFFIXES:
            suffix_label_count = 1
        else:
            # Unknown suffixes are not guessed: same-origin POST still works,
            # but sibling subdomains remain blocked until their site boundary is clear.
            return None
        if len(labels) <= suffix_label_count:
            return None
        return ".".join(labels[-(suffix_label_count + 1):])

    @staticmethod
    def _origin_key(value: str) -> tuple[str, str, int] | None:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        try:
            port = parsed.port
        except ValueError:
            return None
        effective_port = port or (443 if parsed.scheme == "https" else 80)
        return parsed.scheme.lower(), parsed.hostname.lower().rstrip("."), effective_port

    def _page_from_html(
        self,
        *,
        requested_url: str,
        final_url: str,
        content: str,
        rendered: bool,
        visible_title: str | None = None,
        visible_text: str | None = None,
    ) -> JobPage:
        self._validate_url(final_url)
        parser = _PageParser()
        parser.feed(content)
        title = self._clean_text(visible_title) or parser.title or parser.meta.get("og:title") or ""
        body_text = self._clean_text(visible_text) if visible_text is not None else " ".join(parser.text_parts)
        return JobPage(
            requested_url=requested_url,
            final_url=final_url,
            html=content,
            title=(title or "")[:500],
            body_text=(body_text or "")[: self.MAX_VISIBLE_TEXT],
            metadata=parser.meta,
            json_ld=parser.json_ld,
            rendered=rendered,
        )

    @staticmethod
    def _needs_browser_render(page: JobPage) -> bool:
        content = f"{page.title} {page.body_text}".lower()
        has_job_signal = any(term in content for term in ("实习", "招聘", "岗位", "职位", "job", "intern", "career"))
        has_detail_signal = any(
            term in content
            for term in ("岗位职责", "任职要求", "工作内容", "职位描述", "responsibilities", "requirements", "qualifications")
        )
        return len(page.body_text) < 1200 or not (has_job_signal and has_detail_signal)

    @staticmethod
    def _validate_url(value: str) -> None:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
            raise InvalidJobLink("请输入完整的 http 或 https 岗位链接")
        if parsed.username or parsed.password:
            raise InvalidJobLink("链接中不能包含账号或密码")
        hostname = parsed.hostname.lower().rstrip(".")
        if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith((".localhost", ".local", ".internal")):
            raise InvalidJobLink("不支持访问本机或内网地址")
        try:
            literal_ip = ipaddress.ip_address(hostname)
        except ValueError:
            literal_ip = None
        if literal_ip is not None and (
            not literal_ip.is_global or literal_ip.is_private or literal_ip.is_loopback or literal_ip.is_link_local
        ):
            raise InvalidJobLink("不支持访问内网或本机地址")

    def extract_job_posting(self, page: JobPage) -> JobRecord | None:
        posting = self._find_job_posting(page.json_ld)
        if not posting:
            return None
        title = self._clean_text(self._string(posting.get("title")))
        description = self._clean_text(self._string(posting.get("description")))
        requirements = self._clean_text(self._string(posting.get("qualifications")))
        responsibilities = self._clean_text(self._string(posting.get("responsibilities")))
        if not title or not (description or requirements or responsibilities):
            return None
        company = self._organization_name(posting.get("hiringOrganization")) or ""
        city = self._location_name(posting.get("jobLocation")) or ""
        published = self._parse_date(posting.get("datePosted"))
        salary_text = self._salary_text(posting.get("baseSalary")) or ""
        salary_min, salary_max, salary_unit = self._parse_salary(salary_text)
        salary_status = "disclosed" if salary_min is not None else "unknown"
        if not salary_text and any(word in page.body_text for word in ("薪资未公开", "薪酬保密", "薪资保密")):
            salary_status = "undisclosed"
        return JobRecord(
            source_job_id=hashlib.sha256(page.final_url.encode("utf-8")).hexdigest()[:32],
            title=title[:300],
            company_name=company[:200],
            city=city[:64],
            detail_url=page.final_url,
            published_date=published,
            job_type="实习生" if "实习" in title or "实习" in (description or "") else "未说明",
            salary_min=salary_min,
            salary_max=salary_max,
            salary_unit=salary_unit,
            salary_status=salary_status,
            description=description,
            requirements=requirements,
            responsibilities=responsibilities,
            extraction_method="json_ld",
            raw_payload={"url": page.final_url, "extraction_method": "json_ld"},
        )

    def _extract(self, detail_url: str, content: str) -> JobRecord:
        """Retained for deterministic tests and callers with already-fetched HTML."""
        page = self._page_from_html(
            requested_url=detail_url,
            final_url=detail_url,
            content=content,
            rendered=False,
        )
        record = self.extract_job_posting(page)
        if record is None:
            raise InvalidJobLink("这个链接不是可识别的岗位详情页，或页面没有岗位描述")
        return record

    @staticmethod
    def _find_job_posting(values: list[Any]) -> dict[str, Any] | None:
        for value in values:
            candidates = value if isinstance(value, list) else [value]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                types = candidate.get("@type", [])
                types = types if isinstance(types, list) else [types]
                if any(str(item).lower() == "jobposting" for item in types):
                    return candidate
                nested = ManualImportProvider._find_job_posting([candidate.get("@graph", [])])
                if nested:
                    return nested
        return None

    @staticmethod
    def _organization_name(value: Any) -> str | None:
        if isinstance(value, dict):
            return ManualImportProvider._string(value.get("name"))
        return ManualImportProvider._string(value)

    @staticmethod
    def _location_name(value: Any) -> str | None:
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, dict):
            address = value.get("address", value)
            if isinstance(address, dict):
                return ManualImportProvider._string(
                    address.get("addressLocality") or address.get("addressRegion") or address.get("streetAddress")
                )
        return ManualImportProvider._string(value)

    @staticmethod
    def _salary_text(value: Any) -> str | None:
        if isinstance(value, dict):
            currency = value.get("currency") or ""
            amount = value.get("value", value)
            if isinstance(amount, dict):
                low = amount.get("minValue") or amount.get("value")
                high = amount.get("maxValue")
                if low is not None and high is not None:
                    return f"{low}-{high} {currency}".strip()
                return f"{low} {currency}".strip() if low is not None else None
        return ManualImportProvider._string(value)

    @staticmethod
    def _string(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, list):
            return "\n".join(filter(None, (ManualImportProvider._string(item) for item in value))) or None
        return str(value).strip() or None

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if not value:
            return None
        text = re.sub(r"<[^>]+>", " ", html.unescape(value))
        text = " ".join(text.split())
        return text[:10000] or None

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if not value:
            return None
        match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", str(value))
        if not match:
            return None
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    @staticmethod
    def _parse_salary(value: str) -> tuple[float | None, float | None, str | None]:
        numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value)]
        if not numbers:
            return None, None, None
        unit = "元/月" if "月" in value else "元/天" if "天" in value else None
        return (numbers[0], numbers[1] if len(numbers) > 1 else numbers[0], unit)
