"""WordPress REST client: read-only inventory plus owner-approved draft-page creation.

No publish, update, delete, media, user, plugin, theme, or settings methods exist.
Draft creation is separately opt-in and always forces status=draft.
"""
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request


class WordPressNotConfigured(RuntimeError):
    pass


class WordPressReadError(RuntimeError):
    pass


class WordPressWriteDisabled(RuntimeError):
    pass


class WordPressWriteError(RuntimeError):
    pass


class WordPressReadOnlyClient:
    def __init__(self, site_url: str, username: str, application_password: str,
                 *, timeout: int = 15):
        parsed = urllib.parse.urlparse(site_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise ValueError(
                "WordPress site URL must be HTTPS without embedded credentials, query, or fragment."
            )
        self.api_url = urllib.parse.urljoin(site_url.rstrip("/") + "/", "wp-json/wp/v2/")
        credentials = (username + ":" + application_password).encode("utf-8")
        self.authorization = "Basic " + base64.b64encode(credentials).decode("ascii")
        self.timeout = max(3, min(int(timeout), 30))

    @classmethod
    def from_environment(cls):
        site_url = os.getenv("AI_OS_WORDPRESS_URL", "").strip()
        username = os.getenv("AI_OS_WORDPRESS_USERNAME", "").strip()
        password = os.getenv("AI_OS_WORDPRESS_APPLICATION_PASSWORD", "").strip()
        if not (site_url and username and password):
            raise WordPressNotConfigured(
                "WordPress read-only credentials are not configured; no request was made."
            )
        return cls(site_url, username, password)

    @staticmethod
    def status() -> dict:
        configured = all(os.getenv(name, "").strip() for name in (
            "AI_OS_WORDPRESS_URL",
            "AI_OS_WORDPRESS_USERNAME",
            "AI_OS_WORDPRESS_APPLICATION_PASSWORD",
        ))
        draft_writes = (
            configured
            and os.getenv("AI_OS_WORDPRESS_DRAFT_WRITES_ENABLED", "false").strip().lower() == "true"
            and os.getenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false").strip().lower() == "true"
        )
        return {
            "configured": configured,
            "mode": "read_only_with_optional_approved_drafts",
            "capabilities": ["site_posts_read", "site_pages_read"] + (
                ["create_unpublished_page_draft"] if draft_writes else []
            ),
            "writes_enabled": draft_writes,
            "published_writes_enabled": False,
            "users_exposed": False,
            "note": "Only owner-approved page drafts may be created; publishing and all other writes remain unavailable.",
        }

    def _get(self, resource: str, *, page: int = 1, per_page: int = 20) -> list[dict]:
        if resource not in {"posts", "pages"}:
            raise ValueError("Unsupported WordPress content resource.")
        page = max(1, min(int(page), 1000))
        per_page = max(1, min(int(per_page), 50))
        query = urllib.parse.urlencode({
            "page": page,
            "per_page": per_page,
            "context": "edit",
            "_fields": "id,date,modified,slug,status,link,title,excerpt",
        })
        url = urllib.parse.urljoin(self.api_url, resource) + "?" + query
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": self.authorization,
                "Accept": "application/json",
                "User-Agent": "ai-operating-system-wordpress-readonly/1.0",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WordPressReadError(
                "WordPress read request failed; credentials and response were not logged."
            ) from exc
        if len(raw) > 2_000_000:
            raise WordPressReadError("WordPress response exceeded the 2 MB safety limit.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WordPressReadError("WordPress returned invalid JSON.") from exc
        if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
            raise WordPressReadError("WordPress returned an unexpected response shape.")

        result = []
        for row in payload:
            title = row.get("title")
            excerpt = row.get("excerpt")
            result.append({
                "id": row.get("id"),
                "date": row.get("date"),
                "modified": row.get("modified"),
                "slug": row.get("slug"),
                "status": row.get("status"),
                "link": row.get("link"),
                "title": title.get("rendered") if isinstance(title, dict) else None,
                "excerpt": excerpt.get("rendered") if isinstance(excerpt, dict) else None,
            })
        return result

    def list_posts(self, *, page: int = 1, per_page: int = 20) -> list[dict]:
        return self._get("posts", page=page, per_page=per_page)

    def list_pages(self, *, page: int = 1, per_page: int = 20) -> list[dict]:
        return self._get("pages", page=page, per_page=per_page)

    def create_page_draft(self, *, title: str, content: str) -> dict:
        """Create an unpublished page draft; both explicit feature flags are mandatory."""
        if (
            os.getenv("AI_OS_WORDPRESS_DRAFT_WRITES_ENABLED", "false").strip().lower() != "true"
            or os.getenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false").strip().lower() != "true"
        ):
            raise WordPressWriteDisabled("WordPress draft writes require both explicit feature flags.")
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("Draft page title must contain 1 to 200 characters.")
        if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > 12000:
            raise ValueError("Draft page content must contain 1 to 12,000 UTF-8 bytes.")
        url = urllib.parse.urljoin(self.api_url, "pages")
        payload = json.dumps({
            "title": title.strip(),
            "content": content,
            "status": "draft",
        }, ensure_ascii=False, allow_nan=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": self.authorization,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "ai-operating-system-approved-draft/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(2000001)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WordPressWriteError(
                "WordPress draft creation failed; credentials and response were not logged. Check the audit trail before retrying."
            ) from exc
        if len(raw) > 2000000:
            raise WordPressWriteError("WordPress draft response exceeded the 2 MB safety limit.")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WordPressWriteError("WordPress returned invalid JSON after draft creation.") from exc
        if not isinstance(result, dict) or result.get("status") != "draft":
            raise WordPressWriteError("WordPress did not confirm an unpublished draft; inspect the site before retrying.")
        title_value = result.get("title")
        return {
            "id": result.get("id"),
            "status": result.get("status"),
            "link": result.get("link"),
            "title": title_value.get("rendered") if isinstance(title_value, dict) else title.strip(),
        }
