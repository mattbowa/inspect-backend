import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, Query

from app.config import settings
from app.services.embeddings import EMBEDDING_DIM  # 384 (fastembed bge-small)

log = structlog.get_logger()

COLLECTION = "seo_pages"

_client = QdrantClient(url=settings.qdrant_url)


def init_collection() -> None:
    existing = [c.name for c in _client.get_collections().collections]
    if COLLECTION not in existing:
        _client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        log.info("vector_store.created", collection=COLLECTION)
    else:
        log.info("vector_store.exists", collection=COLLECTION)


def upsert_page(scan_id: str, page_url: str, embedding: list[float], payload: dict) -> None:
    point_id = abs(hash(f"{scan_id}:{page_url}")) % (2**63)
    _client.upsert(
        collection_name=COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={"scan_id": scan_id, "url": page_url, **payload},
            )
        ],
    )


def search_similar_pages(embedding: list[float], scan_id: str, top_k: int = 5):
    result = _client.query_points(
        collection_name=COLLECTION,
        query=embedding,
        query_filter=Filter(
            must=[FieldCondition(key="scan_id", match=MatchValue(value=scan_id))]
        ),
        limit=top_k,
    )
    return result.points


def get_pages_for_scan(scan_id: str) -> list[dict]:
    results, _ = _client.scroll(
        collection_name=COLLECTION,
        scroll_filter=Filter(
            must=[FieldCondition(key="scan_id", match=MatchValue(value=scan_id))]
        ),
        limit=100,
        with_payload=True,
    )
    return [r.payload for r in results]
