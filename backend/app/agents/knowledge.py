from __future__ import annotations

import threading

from app.rag.index import KnowledgeIndex

from .base import Agent
from .playbooks import PLAYBOOKS
from .roster import SPECS


def _public(hit: dict) -> dict:
    return {k: v for k, v in hit.items() if k != "text"}


class KnowledgeAgent(Agent):
    spec = SPECS["knowledge"]

    def __init__(self, runtime):
        super().__init__(runtime)
        self.index = KnowledgeIndex()
        self._loaded = False
        self._lock = threading.RLock()

    # ---- lifecycle
    def reindex(self) -> dict:
        with self._lock:
            return self._reindex()

    def _reindex(self) -> dict:
        topo = self.rt.topology
        self.index.load_static(
            topology_raw=topo.raw if topo is not None else None,
            graph=self.rt.graph,
            playbooks=PLAYBOOKS,
        )
        inc_svc = self.rt.incidents
        if inc_svc is not None:
            for blob in inc_svc.list_incidents(limit=200):
                self.index.upsert_incident(blob)
        for pm in self.rt.learning.postmortems.values():
            self.index_postmortem(pm)
        self.index.warm()
        self._loaded = True
        return self.index.stats()

    def ensure_loaded(self):
        if not self._loaded:
            with self._lock:
                if not self._loaded:
                    self._reindex()

    def index_incident(self, inc: dict):
        self.ensure_loaded()
        self.index.upsert_incident(inc)

    def index_postmortem(self, pm: dict):
        self.index.remove_prefix(f"postmortem:{pm['incidentId']}")
        self.index.add_text(
            f"postmortem:{pm['incidentId']}", "postmortem", f"postmortem/{pm['incidentId']}",
            f"Postmortem {pm['incidentId']}", pm["markdown"],
            entityId=(pm.get("rootCause") or {}).get("entityId"),
        )

    # ---- retrieval
    def search(self, query: str, k: int = 5, kinds: set[str] | None = None) -> list[dict]:
        if not self.enabled():
            return []
        self.ensure_loaded()
        self.stats.runs += 1
        return self.index.search(query, k=k, kinds=kinds)

    async def related(self, inc, root_id: str) -> dict:
        """After RCA: similar past incidents + the docs/playbooks relevant to this cause."""
        async with self.step("retrieve_context", inc.id) as st:
            self.ensure_loaded()
            label = (inc.root_cause or {}).get("label") or root_id
            metrics = " ".join(sorted({a.metric for a in inc.anomalies}))
            query = f"{label} {root_id} {metrics} runbook remediation"
            similar = [
                h for h in self.index.search(query, k=4, kinds={"incident", "postmortem"})
                if not h["id"].startswith((f"incident:{inc.id}", f"postmortem:{inc.id}"))
            ][:3]
            refs = self.index.search(query, k=3, kinds={"doc", "playbook", "topology"})
            out = {
                "similar": [_public(h) for h in similar],
                "references": [_public(h) for h in refs],
            }
            st.data = {
                "similar": [h["id"] for h in similar],
                "references": [h["id"] for h in refs],
            }
            st.decision = "similar_found" if similar else "no_similar"
            st.summary = f"{len(similar)} similar past incident(s), {len(refs)} reference passage(s)"
        return out
