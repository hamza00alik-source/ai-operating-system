"""Standalone OpenCompany ASGI server entry point."""
import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "opencompany_app.api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        proxy_headers=True,
    )


if __name__ == "__main__":
    main()
