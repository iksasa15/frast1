from __future__ import annotations

import networkx as nx

from .base import Agent
from .roster import SPECS


class TopologyAgent(Agent):
    spec = SPECS["topology"]

    @property
    def graph(self):
        if self.rt.graph is None:
            raise RuntimeError("topology graph not available")
        return self.rt.graph

    def known_ids(self) -> set[str]:
        topo = self.rt.topology
        if topo is not None:
            return set(topo.nodes) | set(topo.links) | set(topo.services)
        return set(self.graph.g.nodes)

    def label(self, entity_id: str) -> str:
        try:
            return self.graph.label(entity_id)
        except KeyError:
            return entity_id

    def services_for(self, members) -> list[str]:
        out: set[str] = set()
        for m in members:
            out.update(self.graph.services_through(m))
        return sorted(out)

    def impact(self, root_id: str) -> dict:
        g = self.graph
        downstream = g.downstream(root_id)
        return {
            "rootId": root_id,
            "impactPath": sorted(downstream & self.known_ids()),
            "services": sorted(g.services_through(root_id)),
            "upstream": sorted(g.upstream(root_id) & self.known_ids()),
        }

    def path(self, a: str, b: str) -> list[str]:
        try:
            return list(nx.shortest_path(self.graph.g, a, b))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    async def scope(self, inc, affected: list[str]) -> dict:
        """Before RCA: which services and dependency chains are in play for this incident."""
        async with self.step("scope_dependencies", inc.id) as st:
            chains = {s: self.graph.service_dependencies(s) for s in affected}
            data = {
                "members": sorted(inc.members),
                "affectedServices": affected,
                "dependencyChains": chains,
            }
            st.data = data
            st.summary = (
                f"{len(inc.members)} symptomatic element(s) affect {len(affected)} service(s): "
                f"{', '.join(affected) or 'none'}"
            )
        return data

    def reconcile(self, observed: list[dict]) -> dict:
        """Compare CDP/LLDP neighbours against the declared topology.

        `observed` items use IDs from the active discovery snapshot.
        """
        topo = self.rt.topology
        if topo is None:
            raise RuntimeError("topology service not available")
        declared = set()
        for l in topo.links.values():
            declared.add((l["source"], l["sourcePort"], l["target"], l["targetPort"]))
            declared.add((l["target"], l["targetPort"], l["source"], l["sourcePort"]))
        seen = {
            (o["device"], o["port"], o["neighbor"], o["neighborPort"]) for o in observed
        }
        unexpected = sorted(seen - declared)
        reported_devices = {o["device"] for o in observed}
        missing = sorted(
            t
            for t in declared
            if t[0] in reported_devices and t not in seen
        )
        fmt = lambda t: {"device": t[0], "port": t[1], "neighbor": t[2], "neighborPort": t[3]}
        return {
            "ok": not unexpected and not missing,
            "matched": len(seen & declared),
            "unexpected": [fmt(t) for t in unexpected],
            "missing": [fmt(t) for t in missing],
        }
