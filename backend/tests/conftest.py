"""Default test isolation: do not call a real LLM provider even if .env enables it."""
import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _disable_llm_unless_opted_in(monkeypatch, request):
    if request.node.get_closest_marker("llm"):
        return
    monkeypatch.setattr(settings, "llm_enabled", False)
