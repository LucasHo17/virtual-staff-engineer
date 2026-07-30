from google import genai
from google.genai import types

from virtual_staff_engineer.ingestion.markdown import derive_rule_key


DEFAULT_EMBEDDING_MODEL = "models/gemini-embedding-2"
EMBEDDING_DIMENSION = 1536


def get_embedding_client():
    """Construct the external embedding client lazily."""
    return genai.Client()


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
        response = ai_client.models.embed_content(
            model=embedding_model,
            contents=text_content,
            config=types.EmbedContentConfig(
                output_dimensionality=embedding_dimension
            ),
        )
        embedding_vector = response.embeddings[0].values

        if len(embedding_vector) != embedding_dimension:
            raise ValueError(
                f"Expected {embedding_dimension} embedding dimensions, "
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
