import math

from google import genai
from google.genai import types


DEFAULT_EMBEDDING_MODEL = "models/gemini-embedding-2"
EMBEDDING_DIMENSION = 1536


def get_embedding_client():
    """Construct the external embedding client lazily."""
    return genai.Client()


def embed_text(
    text,
    ai_client,
    embedding_model=DEFAULT_EMBEDDING_MODEL,
    embedding_dimension=EMBEDDING_DIMENSION,
):
    """Generate and validate one embedding vector."""
    response = ai_client.models.embed_content(
        model=embedding_model,
        contents=text,
        config=types.EmbedContentConfig(
            output_dimensionality=embedding_dimension
        ),
    )
    embedding_vector = response.embeddings[0].values
    validate_embedding(embedding_vector, embedding_dimension)
    return embedding_vector


def validate_embedding(embedding_vector, expected_dimension):
    """Reject malformed vectors before sending them to PostgreSQL."""
    if len(embedding_vector) != expected_dimension:
        raise ValueError(
            f"Expected {expected_dimension} embedding dimensions, "
            f"received {len(embedding_vector)}."
        )

    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in embedding_vector
    ):
        raise ValueError("Embedding values must be finite numbers.")
