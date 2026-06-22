"""Cosine similarity search over the RAG vector store (Voyage query embedding + pgvector).

  football-search --query "high-pressing opponent that defends deep"
  football-search --query "Brazil tactical approach against Korea" --doc-type tactical_pattern --top-k 3
"""
from __future__ import annotations

import argparse
import sys

from football.db.connection import get_connection
from football.rag.documents import DOC_TYPES
from football.rag.embedder import search_similar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Similarity search over WC2022 RAG documents")
    parser.add_argument("--query", required=True, help="Natural-language query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--doc-type", choices=DOC_TYPES, default=None)
    args = parser.parse_args(argv)

    conn = get_connection()
    try:
        results = search_similar(conn, args.query, top_k=args.top_k, doc_type=args.doc_type)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f'=== top {len(results)} for: "{args.query}"'
          + (f" [{args.doc_type}]" if args.doc_type else "") + " ===")
    for i, r in enumerate(results, 1):
        print(f"\n{i}. [{r['doc_type']} ref={r['ref_id']}] score={r['score']:.4f}")
        print(f"   {r['content']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
