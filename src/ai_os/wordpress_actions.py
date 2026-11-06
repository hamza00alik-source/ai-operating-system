"""Owner-approved WordPress draft-page adapter.

Registration is opt-in. The adapter can only create unpublished pages; it has
no method for publishing or modifying existing WordPress content.
"""
import os

from ai_os.action_gateway import register_action_adapter
from ai_os.wordpress import WordPressReadOnlyClient


def register_wordpress_draft_adapter() -> bool:
    enabled = (
        os.getenv("AI_OS_EXTERNAL_ACTIONS_ENABLED", "false").strip().lower() == "true"
        and os.getenv("AI_OS_WORDPRESS_DRAFT_WRITES_ENABLED", "false").strip().lower() == "true"
        and all(os.getenv(name, "").strip() for name in (
            "AI_OS_WORDPRESS_URL",
            "AI_OS_WORDPRESS_USERNAME",
            "AI_OS_WORDPRESS_APPLICATION_PASSWORD",
        ))
    )
    if not enabled:
        return False

    def create_draft(parameters: dict, execution_id: str) -> dict:
        if set(parameters) != {"title", "content"}:
            raise ValueError("Website draft action accepts only title and content.")
        client = WordPressReadOnlyClient.from_environment()
        result = client.create_page_draft(
            title=parameters["title"],
            content=parameters["content"],
        )
        return {"execution_id": execution_id, "draft_page": result}

    register_action_adapter(
        "create_website_draft",
        adapter_id="wordpress-create-unpublished-page-v1",
        adapter=create_draft,
    )
    return True
