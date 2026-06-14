"""Orchestration: StatsBomb → staging → analytics."""

from football.pipeline.runner import run_full_pipeline

__all__ = ["run_full_pipeline"]
