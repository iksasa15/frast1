"""Agent building blocks: spec, trace steps, per-agent stats and the traced `step()` helper.

Design rule: an agent is a small unit with ONE job, explicit inputs/outputs and a bounded
set of tools. Every meaningful action an agent takes is recorded as a trace step, so the
operator can audit *who decided what* during an incident.
"""
from __future__ import annotations

import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count
from typing import Any, AsyncIterator

from app.services.hub import hub


@dataclass(frozen=True)
class AgentSpec:
    id: str
    name: str
    name_ar: str
    layer: str  # supervisor | perception | reasoning | knowledge | governance | action | learning
    autonomy: str  # observe | advise | coordinate | act_with_approval
    mission: str
    mission_ar: str
    benefit: str
    benefit_ar: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    tools: tuple[str, ...]
    needs: tuple[str, ...]
    guardrails: tuple[str, ...]
    uses_llm: bool = False
    can_disable: bool = True

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "nameAr": self.name_ar,
            "layer": self.layer,
            "autonomy": self.autonomy,
            "mission": self.mission,
            "missionAr": self.mission_ar,
            "benefit": self.benefit,
            "benefitAr": self.benefit_ar,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "tools": list(self.tools),
            "needs": list(self.needs),
            "guardrails": list(self.guardrails),
            "usesLlm": self.uses_llm,
            "canDisable": self.can_disable,
        }


@dataclass
class AgentStats:
    runs: int = 0
    errors: int = 0
    skipped: int = 0
    total_ms: float = 0.0
    last_at: str | None = None
    last_status: str | None = None
    last_summary: str | None = None

    def to_dict(self) -> dict:
        return {
            "runs": self.runs,
            "errors": self.errors,
            "skipped": self.skipped,
            "avgMs": round(self.total_ms / self.runs, 2) if self.runs else 0.0,
            "lastAt": self.last_at,
            "lastStatus": self.last_status,
            "lastSummary": self.last_summary,
        }


@dataclass
class TraceStep:
    id: str
    agent: str
    action: str
    incident_id: str | None
    status: str  # ok | error | skipped | denied
    started_at: str
    duration_ms: float
    summary: str
    data: dict = field(default_factory=dict)
    decision: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "action": self.action,
            "incidentId": self.incident_id,
            "status": self.status,
            "startedAt": self.started_at,
            "durationMs": self.duration_ms,
            "summary": self.summary,
            "data": self.data,
            "decision": self.decision,
        }


class TraceStore:
    def __init__(self, maxlen: int = 3000):
        self.steps: deque[TraceStep] = deque(maxlen=maxlen)
        self._seq = count(1)

    def add(self, **kw) -> TraceStep:
        step = TraceStep(id=f"AS-{next(self._seq):06d}", **kw)
        self.steps.append(step)
        return step

    def for_incident(self, incident_id: str) -> list[dict]:
        return [s.to_dict() for s in sorted(self.steps, key=lambda s: s.started_at) if s.incident_id == incident_id]

    def recent(self, limit: int = 100, incident_id: str | None = None) -> list[dict]:
        items = [s for s in self.steps if incident_id is None or s.incident_id == incident_id]
        items = sorted(items, key=lambda s: s.started_at)
        return [s.to_dict() for s in items[-limit:]]

    def clear(self):
        self.steps.clear()


class StepHandle:
    """Filled in by the agent inside `async with self.step(...)`."""

    def __init__(self):
        self.summary = ""
        self.data: dict[str, Any] = {}
        self.decision: str | None = None
        self.status = "ok"

    def skip(self, reason: str):
        self.status = "skipped"
        self.summary = reason


class Agent:
    spec: AgentSpec

    def __init__(self, runtime):
        self.rt = runtime
        self.stats = AgentStats()

    @property
    def id(self) -> str:
        return self.spec.id

    def enabled(self) -> bool:
        return self.rt.enabled(self.spec.id)

    @asynccontextmanager
    async def step(self, action: str, incident_id: str | None = None) -> AsyncIterator[StepHandle]:
        h = StepHandle()
        started = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        try:
            yield h
        except Exception as e:
            h.status = "error"
            h.summary = f"{type(e).__name__}: {e}"
            self._record(action, incident_id, h, started, t0)
            await self._publish()
            raise
        self._record(action, incident_id, h, started, t0)
        await self._publish()

    def _record(self, action, incident_id, h: StepHandle, started, t0):
        ms = round((time.perf_counter() - t0) * 1000, 2)
        st = self.stats
        if h.status == "skipped":
            st.skipped += 1
        else:
            st.runs += 1
            st.total_ms += ms
        if h.status == "error":
            st.errors += 1
        st.last_at = started.isoformat()
        st.last_status = h.status
        st.last_summary = h.summary
        self._last = self.rt.trace.add(
            agent=self.spec.id,
            action=action,
            incident_id=incident_id,
            status=h.status,
            started_at=started.isoformat(),
            duration_ms=ms,
            summary=h.summary,
            data=h.data,
            decision=h.decision,
        )

    async def _publish(self):
        try:
            await hub.broadcast("agent_step", self._last.to_dict())
        except Exception:
            pass

    def describe(self) -> dict:
        return {
            **self.spec.to_dict(),
            "enabled": self.enabled(),
            "stats": self.stats.to_dict(),
        }
