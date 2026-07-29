import os
import hashlib
import re
import psycopg
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load configuration
load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

EMBEDDING_MODEL = "models/gemini-embedding-2"
EMBEDDING_DIMENSION = 1536
RULE_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9_-]*-\d+)\b", re.IGNORECASE)


def get_ai_client():
    """Constructs the API client lazily so pure parsing tests need no API key."""
    return genai.Client()


def compute_checksum(file_path):
    """Generates a SHA-256 hash of a file to check for updates."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def derive_rule_key(section):
    """Returns a stable rule identifier from a Markdown section heading."""
    rule_match = RULE_KEY_PATTERN.search(section)
    if rule_match:
        return rule_match.group(1).upper()

    normalized_section = re.sub(r"[^A-Z0-9]+", "-", section.upper()).strip("-")
    return normalized_section[:100] or "GENERAL"


def parse_markdown(file_path):
    """Splits a markdown file into discrete sections based on H2 headers (##)."""
    chunks = []
    current_section = "General"
    current_content = []

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                # If we already have content accumulated, save the previous section
                text_content = "".join(current_content).strip()
                if text_content:
                    chunks.append((current_section, text_content))
                    current_content = []
                current_section = line.replace("## ", "").strip()
            else:
                # Don't capture the top H1 header as a text block
                if not line.startswith("# "):
                    current_content.append(line)
        
        # Append the final section
        text_content = "".join(current_content).strip()
        if text_content:
            chunks.append((current_section, text_content))
            
    return chunks


def generate_embeddings(parsed_chunks, ai_client):
    """Embeds all non-empty chunks before opening the write transaction."""
    embedded_chunks = []

    for chunk_index, (section, text_content) in enumerate(parsed_chunks):
        print(f"🧠 Generating embedding for section: {section}...")
        response = ai_client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text_content,
            config=types.EmbedContentConfig(
                output_dimensionality=EMBEDDING_DIMENSION
            ),
        )
        embedding_vector = response.embeddings[0].values

        if len(embedding_vector) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"Expected {EMBEDDING_DIMENSION} embedding dimensions, "
                f"received {len(embedding_vector)}."
            )

        embedded_chunks.append(
            {
                "chunk_index": chunk_index,
                "rule_key": derive_rule_key(section),
                "section": section,
                "content": text_content,
                "embedding": embedding_vector,
            }
        )

    return embedded_chunks


def ingest_playbook(file_path, category="general"):
    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    filename = os.path.basename(file_path)
    current_checksum = compute_checksum(file_path)
    parsed_chunks = parse_markdown(file_path)

    print(f"📄 Processing playbook: {filename}...")

    if not parsed_chunks:
        raise ValueError(f"No non-empty Markdown sections found in {file_path}.")

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    pd.document_id,
                    pd.archived_at,
                    pv.playbook_version_id
                FROM playbook_documents AS pd
                JOIN playbook_versions AS pv
                    ON pv.document_id = pd.document_id
                WHERE pd.filename = %s
                  AND pv.checksum = %s
                  AND pv.embedding_model = %s
                  AND pv.embedding_dimension = %s;
                """,
                (
                    filename,
                    current_checksum,
                    EMBEDDING_MODEL,
                    EMBEDDING_DIMENSION,
                ),
            )
            existing_version = cur.fetchone()
            if existing_version:
                document_id, archived_at, _ = existing_version
                if archived_at is not None:
                    cur.execute(
                        """
                        UPDATE playbook_documents
                        SET archived_at = NULL,
                            category = %s
                        WHERE document_id = %s;
                        """,
                        (category, document_id),
                    )
                print(f"⏩ No changes detected for {filename}. Skipping ingestion.")
                return {
                    "status": "skipped",
                    "filename": filename,
                    "chunk_count": 0,
                }

    print(f"✂️ Parsed {len(parsed_chunks)} non-empty playbook chunks.")
    embedded_chunks = generate_embeddings(parsed_chunks, get_ai_client())

    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO playbook_documents (filename, category)
                VALUES (%s, %s)
                ON CONFLICT (filename) DO UPDATE
                SET category = EXCLUDED.category,
                    archived_at = NULL
                RETURNING document_id;
                """,
                (filename, category),
            )
            document_id = cur.fetchone()[0]

            # Serialize version allocation for concurrent ingestion of one document.
            cur.execute(
                """
                SELECT document_id
                FROM playbook_documents
                WHERE document_id = %s
                FOR UPDATE;
                """,
                (document_id,),
            )

            # Another worker may have inserted this version while embeddings ran.
            cur.execute(
                """
                SELECT playbook_version_id
                FROM playbook_versions
                WHERE document_id = %s
                  AND checksum = %s
                  AND embedding_model = %s
                  AND embedding_dimension = %s;
                """,
                (
                    document_id,
                    current_checksum,
                    EMBEDDING_MODEL,
                    EMBEDDING_DIMENSION,
                ),
            )
            concurrent_version = cur.fetchone()
            if concurrent_version:
                print(
                    f"⏩ Version was ingested concurrently for {filename}. "
                    "Skipping duplicate write."
                )
                return {
                    "status": "skipped",
                    "filename": filename,
                    "chunk_count": 0,
                }

            cur.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM playbook_versions
                WHERE document_id = %s;
                """,
                (document_id,),
            )
            version_number = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO playbook_versions (
                    document_id,
                    version,
                    checksum,
                    embedding_model,
                    embedding_dimension
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING playbook_version_id;
                """,
                (
                    document_id,
                    version_number,
                    current_checksum,
                    EMBEDDING_MODEL,
                    EMBEDDING_DIMENSION,
                ),
            )
            playbook_version_id = cur.fetchone()[0]

            for chunk in embedded_chunks:
                cur.execute(
                    """
                    INSERT INTO playbook_chunks (
                        playbook_version_id,
                        rule_key,
                        chunk_index,
                        section,
                        content,
                        embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (
                        playbook_version_id,
                        chunk["rule_key"],
                        chunk["chunk_index"],
                        chunk["section"],
                        chunk["content"],
                        chunk["embedding"],
                    ),
                )

        conn.commit()

    print(
        f"✅ Ingested {filename} version {version_number} "
        f"with {len(embedded_chunks)} chunks."
    )
    return {
        "status": "ingested",
        "filename": filename,
        "version": version_number,
        "chunk_count": len(embedded_chunks),
    }

if __name__ == "__main__":
    # Let's test it against your sample playbook
    sample_path = "playbooks/sample_playbook.md"
    if os.path.exists(sample_path):
        ingest_playbook(sample_path, category="standards")
    else:
        print(f"❌ Missing target document: {sample_path}. Please create it first.")
