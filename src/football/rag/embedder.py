"""Local sentence-transformers embeddings + pgvector cosine similarity search.

Runs fully offline at zero cost — no API key, no external calls. The model
(default BAAI/bge-small-en-v1.5, 384-dim) is downloaded once and cached locally.
Documents are encoded as-is; queries get the bge retrieval instruction prefix.
Embeddings are L2-normalized so cosine distance is meaningful.
"""
from __future__ import annotations

from psycopg2.extensions import connection as PGConnection

from football.config import EMBED_MODEL, EMBED_QUERY_INSTRUCTION

_MODEL = None


def _model(name: str = EMBED_MODEL):
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(name)
    return _MODEL


def _to_pgvector(vec) -> str:
    """pgvector accepts the text form '[v1,v2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def embed_query(text: str, model: str = EMBED_MODEL) -> list[float]:
    vec = _model(model).encode(
        EMBED_QUERY_INSTRUCTION + text, normalize_embeddings=True
    )
    return vec.tolist()


def embed_pending(
    conn: PGConnection, model: str = EMBED_MODEL, batch_size: int = 64
) -> int:
    """Embed every embedding_documents row where embedding IS NULL.

    Returns rows_embedded. Idempotent — already-embedded rows are skipped.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, content FROM analytics.embedding_documents "
            "WHERE embedding IS NULL ORDER BY doc_id"
        )
        pending = cur.fetchall()
    if not pending:
        return 0

    st = _model(model)
    embedded = 0
    for start in range(0, len(pending), batch_size):
        chunk = pending[start : start + batch_size]
        vecs = st.encode([c for _, c in chunk], normalize_embeddings=True)
        with conn.cursor() as cur:
            for (doc_id, _), vec in zip(chunk, vecs):
                cur.execute(
                    "UPDATE analytics.embedding_documents "
                    "SET embedding = %s::vector WHERE doc_id = %s",
                    (_to_pgvector(vec), doc_id),
                )
        conn.commit()
        embedded += len(chunk)
    return embedded


def search_similar(
    conn: PGConnection,
    query_text: str,
    top_k: int = 5,
    doc_type: str | None = None,
    model: str = EMBED_MODEL,
) -> list[dict]:
    """Cosine top-k over analytics.embedding_documents. Higher score = closer."""
    qvec = _to_pgvector(embed_query(query_text, model=model))
    where = "WHERE embedding IS NOT NULL"
    params: list = []
    if doc_type:
        where += " AND doc_type = %s"
        params.append(doc_type)
    sql = f"""
        SELECT doc_id, doc_type, ref_id, content, metadata,
               1 - (embedding <=> %s::vector) AS score
        FROM analytics.embedding_documents
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    params = [qvec, *params, qvec, top_k]
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
