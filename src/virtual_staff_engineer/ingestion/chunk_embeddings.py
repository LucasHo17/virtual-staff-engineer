from virtual_staff_engineer.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EMBEDDING_DIMENSION,
    embed_text,
    get_embedding_client,
)
from virtual_staff_engineer.ingestion.markdown import derive_rule_key


def generate_embeddings(
    parsed_chunks,
    ai_client,
    embedding_model=DEFAULT_EMBEDDING_MODEL,
    embedding_dimension=EMBEDDING_DIMENSION,
):
    """Embed all parsed chunks before opening the database write transaction."""
    embedded_chunks = []

    for chunk_index, (section, text_content) in enumerate(parsed_chunks):
        print(f"🧠 Generating embedding for section: {section}...")
        embedding_vector = embed_text(
            text_content,
            ai_client,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
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
