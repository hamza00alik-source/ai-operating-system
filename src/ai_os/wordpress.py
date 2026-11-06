"""Read-only WordPress REST client for site content inventory.

The connector deliberately exposes only GET operations for published/draft
content metadata. It has no create, update, delete, media-upload, user, or
plugin-management methods. Use a dedicated WordPress Application Password
with read-only permissions where the site supports scoped credentials.
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
        return {
            "configured": configured,
            "mode": "read_only",
            "capabilities": ["site_posts_read", "site_pages_read"],
            "writes_enabled": False,
            "users_exposed": False,
            "note": "No page, post, media, plugin, theme, user, or settings writes are available.",
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
