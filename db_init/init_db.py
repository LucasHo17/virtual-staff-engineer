import os
import glob
import hashlib
import psycopg
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

# Locate the folder containing your SQL scripts
SQL_FOLDER_PATH = os.path.join(os.path.dirname(__file__), "sql")

def compute_checksum(file_path):
    hasher = hashlib.sha256()
    with open(file_path, "rb") as sql_file:
        for chunk in iter(lambda: sql_file.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def initialize_database():
    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    print("🔄 Connecting to PostgreSQL container...")
    
    # Use glob to find all files ending in .sql inside the folder
    search_pattern = os.path.join(SQL_FOLDER_PATH, "*.sql")
    sql_files = glob.glob(search_pattern)
    
    if not sql_files:
        print(f"⚠️ Warning: No .sql files discovered in {SQL_FOLDER_PATH}")
        return

    # Sort files alphabetically to enforce consistent migration order
    sql_files.sort()
    print(f"🔍 Discovered {len(sql_files)} SQL script(s) via glob.")

    with psycopg.connect(DB_URL) as conn:
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
                filename = os.path.basename(file_path)
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
                with open(file_path, "r", encoding="utf-8") as sql_file:
                    cur.execute(sql_file.read())

                cur.execute(
                    """
                    INSERT INTO schema_migrations (filename, checksum)
                    VALUES (%s, %s);
                    """,
                    (filename, checksum),
                )

        conn.commit()
        print("✅ All database migrations applied successfully!")

if __name__ == "__main__":
    try:
        initialize_database()
    except Exception as error:
        print(f"❌ Database migration failed: {error}")
        raise
