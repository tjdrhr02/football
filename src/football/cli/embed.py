"""Build RAG documents from analytics SQL, then embed them with Voyage AI.

  football-embed                      # rebuild all doc_types + embed pending
  football-embed --doc-type tactical_pattern
  football-embed --no-rebuild         # only embed rows still missing an embedding
"""
from __future__ import annotations

import argparse
import sys

from football.config import COMPETITION_ID, SEASON_ID
from football.db.connection import get_connection
from football.rag.documents import DOC_TYPES, generate_documents
from football.rag.embedder import embed_pending


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate + embed WC2022 RAG documents")
    parser.add_argument("--competition-id", type=int, default=COMPETITION_ID)
    parser.add_argument("--season-id", type=int, default=SEASON_ID)
    parser.add_argument(
        "--doc-type",
        action="append",
        choices=DOC_TYPES,
        help="Limit to specific doc_type(s); repeatable. Default: all.",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Skip document regeneration; only embed rows with NULL embedding.",
    )
    args = parser.parse_args(argv)
    doc_types = tuple(args.doc_type) if args.doc_type else DOC_TYPES

    conn = get_connection()
    try:
        if not args.no_rebuild:
            summary = generate_documents(conn, args.competition_id, args.season_id, doc_types)
            print("--- documents generated ---")
            for dt in doc_types:
                print(f"  {dt:18} {summary.get(dt, 0)}")
        embedded = embed_pending(conn)
        print(f"--- embedded {embedded} rows (local sentence-transformers, zero cost) ---")
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
