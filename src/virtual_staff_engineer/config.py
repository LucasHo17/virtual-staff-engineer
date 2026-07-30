import os

from dotenv import load_dotenv


load_dotenv()


def require_database_url(database_url=None):
    """Return an explicit or environment-provided PostgreSQL connection URL."""
    resolved_url = database_url or os.getenv("DATABASE_URL")
    if not resolved_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    return resolved_url
