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
    SESSION_TTL_HOURS: int = int(os.getenv("SESSION_TTL_HOURS", "168"))
    SESSION_COOKIE_NAME: str = "autopilot_session"

    GITHUB_APP_ID: str = os.environ["GITHUB_APP_ID"]
    GITHUB_APP_PRIVATE_KEY: str = os.environ["GITHUB_APP_PRIVATE_KEY"]
    GITHUB_APP_SLUG: str = os.environ["GITHUB_APP_SLUG"]

    LINEAR_CLIENT_ID: str = os.environ["LINEAR_CLIENT_ID"]
    LINEAR_CLIENT_SECRET: str = os.environ["LINEAR_CLIENT_SECRET"]
    LINEAR_REDIRECT_URL: str = os.environ["LINEAR_REDIRECT_URL"]
    LINEAR_WEBHOOK_SECRET: str = os.environ["LINEAR_WEBHOOK_SECRET"]
    ANTHROPIC_API_KEY: str = os.environ["ANTHROPIC_API_KEY"]
    WORKER_IMAGE: str = os.environ["WORKER_IMAGE"]
    SANDBOX_TTL: int = int(os.getenv("SANDBOX_TTL", "900"))

    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    AUTOPILOT_LABEL_DEFAULT: str = os.getenv("AUTOPILOT_LABEL_DEFAULT", "autopilot")


config = Config()
