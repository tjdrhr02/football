"""Hybrid lineup recommendation — SQL facts → pgvector context → Gemini.

  football-recommend
  football-recommend --question "브라질의 고압박을 무력화할 라인업은?" --top-k 6
  football-recommend --opponent-id 781 --match-id 3869253
"""
from __future__ import annotations

import argparse
import sys

from football.config import BRAZIL_TEAM_ID
from football.db.connection import get_connection
from football.rag.recommend import (
    DEFAULT_QUESTION,
    HEAD_TO_HEAD_MATCH_ID,
    build_prompt,
    format_sql_context,
    generate,
    matchup_stats,
    retrieve_context,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hybrid (SQL+RAG+Gemini) lineup recommendation")
    parser.add_argument("--opponent-id", type=int, default=BRAZIL_TEAM_ID)
    parser.add_argument("--match-id", type=int, default=HEAD_TO_HEAD_MATCH_ID)
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build SQL + vector context and print the prompt, but skip the Gemini call.",
    )
    args = parser.parse_args(argv)

    conn = get_connection()
    try:
        print("[1/3] SQL 실측 컨텍스트 조회 ...")
        stats = matchup_stats(conn, args.opponent_id, args.match_id)
        sql_context = format_sql_context(stats)
        print(f"      상대={stats['opponent_name']} | 한국 가용선수 {len(stats['korea_squad'])}명 "
              f"| 맞대결 한국 출전 {len(stats['korea_h2h'])}명")

        print(f"[2/3] 벡터 유사 검색 (top-k={args.top_k}) ...")
        hits, vector_context = retrieve_context(
            conn, args.question, stats["opponent_name"], top_k=args.top_k
        )
        for h in hits:
            print(f"      [{h['doc_type']} ref={h['ref_id']}] score={h['score']:.3f}")

        prompt = build_prompt(args.question, sql_context, vector_context)
        if args.dry_run:
            print("\n[dry-run] === PROMPT ===\n")
            print(prompt)
            return 0

        print("[3/3] Gemini 생성 ...")
        answer = generate(prompt)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print("\n=== 추천 결과 ===\n")
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
