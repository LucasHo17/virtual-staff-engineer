import hashlib
from pathlib import Path

from virtual_staff_engineer.database.connection import connect


MIGRATIONS_DIRECTORY = Path(__file__).with_name("sql")


def compute_checksum(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as sql_file:
        for chunk in iter(lambda: sql_file.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def initialize_database(database_url=None):
    """Apply all pending, checksum-verified SQL migrations atomically."""
    print("🔄 Connecting to PostgreSQL...")

    sql_files = sorted(MIGRATIONS_DIRECTORY.glob("*.sql"))
    if not sql_files:
        print(f"⚠️ No SQL migrations discovered in {MIGRATIONS_DIRECTORY}")
        return

    print(f"🔍 Discovered {len(sql_files)} SQL migration(s).")

    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename VARCHAR(255) PRIMARY KEY,
                    checksum VARCHAR(64) NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            for file_path in sql_files:
                filename = file_path.name
                checksum = compute_checksum(file_path)

                cur.execute(
                    """
                    SELECT checksum
                    FROM schema_migrations
                    WHERE filename = %s;
                    """,
                    (filename,),
                )
                applied_migration = cur.fetchone()

                if applied_migration:
                    if applied_migration[0] != checksum:
                        raise RuntimeError(
                            f"Applied migration {filename} was modified. "
                            "Create a new migration instead."
                        )
                    print(f"⏩ Migration already applied: {filename}")
                    continue

                print(f"⚙️ Applying migration: {filename}...")
                cur.execute(file_path.read_text(encoding="utf-8"))
                cur.execute(
                    """
                    INSERT INTO schema_migrations (filename, checksum)
                    VALUES (%s, %s);
                    """,
                    (filename, checksum),
                )

        conn.commit()

    print("✅ All database migrations applied successfully!")
