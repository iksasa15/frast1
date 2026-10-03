"""Default test isolation: use the explicit simulator fixture and never call a real LLM."""
from pathlib import Path

import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def _disable_llm_unless_opted_in(monkeypatch, request):
    topology_fixture = Path(__file__).resolve().parents[2] / "configs" / "topology.json"
    monkeypatch.setattr(settings, "rootiq_mode", "sim")
    monkeypatch.setattr(settings, "topology_path", str(topology_fixture))
    if request.node.get_closest_marker("llm"):
        return
    monkeypatch.setattr(settings, "llm_enabled", False)
