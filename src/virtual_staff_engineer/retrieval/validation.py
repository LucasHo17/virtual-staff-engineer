from virtual_staff_engineer.embeddings import EMBEDDING_DIMENSION


MAX_TOP_K = 100


def validate_query(query):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Query must be a non-empty string.")
    return query.strip()


def validate_top_k(top_k):
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise ValueError("top_k must be an integer.")
    if top_k < 1 or top_k > MAX_TOP_K:
        raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}.")


def validate_category(category):
    if category is None:
        return None
    if not isinstance(category, str) or not category.strip():
        raise ValueError("category must be a non-empty string when provided.")
    return category.strip()


def validate_embedding_dimension(embedding_dimension):
    if embedding_dimension != EMBEDDING_DIMENSION:
        raise ValueError(
            f"The current pgvector schema requires {EMBEDDING_DIMENSION} "
            f"dimensions, received {embedding_dimension}."
        )
