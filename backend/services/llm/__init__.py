"""LLM service: Google Gemini only (no provider abstraction)."""

from backend.services.llm.gemini import GeminiService

__all__ = ["GeminiService"]
