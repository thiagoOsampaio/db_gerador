"""Reusable knowledge bundles for the agent prompt layer.

These modules expose domain knowledge (universal database design
patterns, etc.) as LangChain prompt fragments so that every agent can
compose its system prompt from a single source of truth.
"""

from backend.agents.knowledge.database_patterns import (
    DATABASE_DESIGN_PATTERNS,
    build_system_prompt,
)

__all__ = ["DATABASE_DESIGN_PATTERNS", "build_system_prompt"]
