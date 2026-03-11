import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_URL: str = os.environ["DB_URL"]
    BASE_URL: str = os.environ["BASE_URL"]

    GOOGLE_CLIENT_ID: str = os.environ["GOOGLE_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET: str = os.environ["GOOGLE_CLIENT_SECRET"]
    GOOGLE_REDIRECT_URL: str = os.environ["GOOGLE_REDIRECT_URL"]

    JWT_SECRET: str = os.environ["JWT_SECRET"]
    JWT_ALGORITHM: str = "HS256"
    SESSION_TTL_MINUTES: int = int(os.getenv("SESSION_TTL_MINUTES", "60"))
    SESSION_COOKIE_NAME: str = "autopilot_session"

    GITHUB_APP_ID: str = os.environ["GITHUB_APP_ID"]
    GITHUB_APP_PRIVATE_KEY: str = os.environ["GITHUB_APP_PRIVATE_KEY"]
    GITHUB_APP_SLUG: str = os.environ["GITHUB_APP_SLUG"]

    LINEAR_CLIENT_ID: str = os.environ["LINEAR_CLIENT_ID"]
    LINEAR_CLIENT_SECRET: str = os.environ["LINEAR_CLIENT_SECRET"]
    LINEAR_REDIRECT_URL: str = os.environ["LINEAR_REDIRECT_URL"]
    LINEAR_WEBHOOK_SECRET: str = os.environ["LINEAR_WEBHOOK_SECRET"]
    WORKER_IMAGE: str = os.environ["WORKER_IMAGE"]

    CLAUDE_CLIENT_ID: str = os.getenv("CLAUDE_CLIENT_ID", "")
    CLAUDE_CLIENT_SECRET: str = os.getenv("CLAUDE_CLIENT_SECRET", "")
    CLAUDE_REDIRECT_URL: str = os.getenv("CLAUDE_REDIRECT_URL", "")
    SANDBOX_TTL: int = int(os.getenv("SANDBOX_TTL", "900"))
    VOLUME_TTL: int = int(os.getenv("VOLUME_TTL", "86400"))
    REVIEW_DEBOUNCE_SECONDS: int = int(os.getenv("REVIEW_DEBOUNCE_SECONDS", "600"))

    GITHUB_APP_WEBHOOK_SECRET: str = os.getenv("GITHUB_APP_WEBHOOK_SECRET", "")

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    AUTOPILOT_LABEL_DEFAULT: str = os.getenv("AUTOPILOT_LABEL_DEFAULT", "autopilot")


config = Config()
