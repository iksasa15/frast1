from __future__ import annotations

import ipaddress
import time
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.core.config import settings
from app.knowledge import get_kb

from .base import Agent
from .playbooks import ALLOWED_ACTIONS, WIDE_BLAST_ELEMENTS
from .roster import SPECS

# Identities that can never approve: only a named human can.
AGENT_ACTORS = {
    "system", "agent", "rootiq", "orchestrator", "auto", "autopilot", "bot",
    "copilot", "ai", "llm", "guardrail", "execution",
}
PRIVATE_SUFFIXES = (".lab", ".local", ".internal", ".lan", ".test", ".localhost")
WINDOW_S = 300


def is_agent_actor(name: str | None) -> bool:
    n = (name or "").strip().lower()
    return (not n) or n in AGENT_ACTORS or n.startswith("agent:") or n.startswith("system:")


def lab_url_is_private(url: str) -> bool:
    host = urlparse(url).hostname or ""
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except ValueError:
        return "." not in host or host.endswith(PRIVATE_SUFFIXES)


@dataclass
class Check:
    id: str
    ok: bool
    level: str  # block | warn | info
    message: str

    def to_dict(self) -> dict:
        return {"id": self.id, "ok": self.ok, "level": self.level, "message": self.message}


@dataclass
class Verdict:
    stage: str
    checks: list[Check] = field(default_factory=list)
    execute: bool = True  # False -> live remediation runs as a dry run

    @property
    def allowed(self) -> bool:
        return not any((not c.ok) and c.level == "block" for c in self.checks)

    @property
    def warnings(self) -> list[str]:
        return [c.message for c in self.checks if (not c.ok) and c.level == "warn"]

    @property
    def denial(self) -> str | None:
        b = [c.message for c in self.checks if (not c.ok) and c.level == "block"]
        return "; ".join(b) or None

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "allowed": self.allowed,
            "execute": self.execute,
            "warnings": self.warnings,
            "checks": [c.to_dict() for c in self.checks],
        }


class GuardrailAgent(Agent):
    spec = SPECS["guardrail"]

    def __init__(self, runtime):
        super().__init__(runtime)
        self.executions: deque[float] = deque(maxlen=100)

    def record_execution(self):
        self.executions.append(time.time())

    def _recent_executions(self) -> int:
        now = time.time()
        return sum(1 for t in self.executions if now - t <= WINDOW_S)

    @staticmethod
    def _vendor_command_violations(vc: dict) -> list[str]:
        kb = get_kb()
        bad: list[str] = []
        if vc.get("executable") is not False:
            bad.append("vendorCommands.executable must be false")
        for d in vc.get("diagnose", []):
            for chk in d.get("checks", []):
                for cmd in chk.get("commands", []):
                    if not kb.is_read_only(cmd):
                        bad.append(f"{d.get('device')}: {cmd!r}")
        for f in vc.get("fixes", []):
            if f.get("needsApproval") is not True:
                bad.append(f"fix {f.get('id')} does not require approval")
        return bad

    # ---- policy engine (pure, unit-testable) ----
    def evaluate(
        self,
        stage: str,
        *,
        action: dict | None = None,
        incident=None,
        decided_by: str | None = None,
        mode: str | None = None,
    ) -> Verdict:
        v = Verdict(stage)
        add = v.checks.append
        action = action or {}
        plan = action.get("plan") or {}

        if stage in ("approve", "reject"):
            human = not is_agent_actor(decided_by)
            add(Check(
                "human_decider", human, "block",
                "A named human engineer must decide; agents and system accounts cannot approve or reject"
                if not human else f"Decision by {decided_by}",
            ))

        if stage in ("recommend", "approve"):
            wl = action.get("actionType") in ALLOWED_ACTIONS
            add(Check("whitelist", wl, "block",
                      f"Action type '{action.get('actionType')}' is not in the playbook whitelist" if not wl
                      else f"'{action.get('actionType')}' is a whitelisted playbook action"))

        if stage == "recommend":
            req = plan.get("requiresApproval", True) is True and not plan.get("autoExecutable", False)
            add(Check("requires_human", req, "block",
                      "Plan must require human approval and cannot be auto-executable" if not req
                      else "Plan requires human approval"))

        if stage == "approve":
            pending = action.get("approvalStatus") == "pending"
            add(Check("action_pending", pending, "block",
                      f"Action is '{action.get('approvalStatus')}', only a pending action can be approved" if not pending
                      else "Action is pending"))
            st = getattr(incident, "status", None)
            ok_state = st in ("awaiting_approval", "recommendation_ready", "investigating")
            add(Check("incident_state", ok_state, "block",
                      f"Incident is '{st}' and cannot accept an approval" if not ok_state
                      else f"Incident state '{st}' accepts approval"))
            n = self._recent_executions()
            add(Check("rate_limit", n < settings.guardrail_max_executions, "block",
                      f"{n} executions in the last {WINDOW_S // 60} min (limit {settings.guardrail_max_executions})"
                      if n >= settings.guardrail_max_executions else f"{n} recent execution(s), under the limit"))
            if mode == "live":
                priv = lab_url_is_private(settings.lab_agent_url)
                add(Check("lab_scope", priv, "block",
                          "LAB_AGENT_URL is not a private/loopback address — lab isolation violated" if not priv
                          else "Lab agent is on a private address"))
                if not settings.rootiq_execution_enabled:
                    v.execute = False
                    add(Check("execution_switch", False, "warn",
                              "Execution is switched off (ROOTIQ_EXECUTION_ENABLED=0): approval is recorded, remediation is a dry run"))

        if stage in ("recommend", "approve") and plan.get("vendorCommands"):
            bad = self._vendor_command_violations(plan["vendorCommands"])
            add(Check("vendor_commands_read_only", not bad, "block",
                      "Vendor diagnostic commands must be read-only, non-executable and fixes must need approval — violations: "
                      + "; ".join(bad[:3]) if bad else "Vendor diagnostic commands are read-only reference text (not executed)"))

        if stage in ("recommend", "approve") and incident is not None:
            low = bool(getattr(incident, "needs_investigation", False))
            if low:
                add(Check("low_confidence", False, "warn",
                          "Root-cause confidence is below 55% — the engineer should verify before approving"))
            wide = len(getattr(incident, "impact_path", []) or []) >= WIDE_BLAST_ELEMENTS
            if wide:
                add(Check("blast_radius", False, "warn", f"Wide blast radius ({WIDE_BLAST_ELEMENTS}+ downstream elements)"))
        return v

    # ---- traced wrapper ----
    async def check(self, stage: str, *, incident=None, action=None, decided_by=None, mode=None) -> Verdict:
        iid = getattr(incident, "id", None)
        async with self.step(f"policy_{stage}", iid) as st:
            v = self.evaluate(stage, action=action, incident=incident, decided_by=decided_by, mode=mode)
            st.data = v.to_dict()
            if v.allowed:
                st.decision = "allow" + (" (with warnings)" if v.warnings else "")
                st.summary = f"{stage}: {len(v.checks)} policy check(s) passed" + (
                    f", {len(v.warnings)} warning(s)" if v.warnings else ""
                )
            else:
                st.status = "denied"
                st.decision = "deny"
                st.summary = f"{stage} DENIED — {v.denial}"
                self.rt.audit.log(
                    decided_by or "system", "guardrail_denied", (action or {}).get("id") or iid or "n/a",
                    {"stage": stage, "reason": v.denial},
                )
        return v
