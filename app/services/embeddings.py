from fastembed import TextEmbedding

# BAAI/bge-small-en-v1.5 — 384-dim, ~24MB, fast
_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

EMBEDDING_DIM = 384


def embed(text: str) -> list[float]:
    results = list(_model.embed([text[:8000]]))
    return results[0].tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    cleaned = [t[:8000] for t in texts]
    return [vec.tolist() for vec in _model.embed(cleaned)]
