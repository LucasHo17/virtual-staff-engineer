import psycopg

from virtual_staff_engineer.config import require_database_url


def connect(database_url=None):
    """Create a PostgreSQL connection using project configuration."""
    return psycopg.connect(require_database_url(database_url))
