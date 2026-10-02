"""Verify all three sim scenarios produce the expected root cause."""
import asyncio

import pytest

from tests.simulator_fixture import Simulator
from app.intelligence.correlate import Correlator
from app.intelligence.detector import Detector
from app.intelligence.graph import TopologyGraph
from app.intelligence.history import History
from app.services.action_service import ActionService
from app.services.audit import AuditLog
from app.services.incident_service import IncidentService
from app.services.pipeline import Pipeline
from app.services.state_store import StateStore
from app.services.topology_service import TopologyService


SCENARIOS = ["uplink-congestion", "dns-failure", "server-spike"]
EXPECTED_ROOT = {"uplink-congestion": "link-r1-sw1", "dns-failure": "svc-dns", "server-spike": "app01"}


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS)
async def test_scenario_root_cause(scenario, tmp_path):
    topo = TopologyService()
    state = StateStore(topo)
    detector = Detector()
    graph = TopologyGraph(topo.raw)
    correlator = Correlator(graph)
    history = History(str(tmp_path / "h.json"))
    demo = {"mode": "sim", "scenario": None, "state": "idle", "injectedAt": None}
    incidents = IncidentService(
        correlator, graph, history=history, topology=topo
    )
    actions = ActionService(
        incidents,
        detector=detector,
        history=history,
        audit=AuditLog(),
        execution_adapter_ref=lambda: sim,
    )
    incidents.actions = actions
    pipeline = Pipeline(topo, state, detector, incidents)
    sim = Simulator(pipeline)

    for _ in range(40):
        await sim.step(1.0)

    from datetime import datetime, timezone

    demo.update(
        scenario=scenario,
        state="injected",
        injectedAt=datetime.now(timezone.utc).isoformat(),
    )
    sim.inject(scenario)

    for _ in range(25):
        await sim.step(1.0)
        await asyncio.sleep(0)  # let analyze tasks schedule

    # Force analyze if debounce hasn't finished
    for inc in list(incidents.open.values()):
        await incidents.analyze(inc.id)

    open_incs = [i for i in incidents.list_incidents() if i["status"] != "resolved"]
    assert open_incs, f"no incident for {scenario}"
    root = (open_incs[0].get("rootCause") or {}).get("entityId")
    assert root == EXPECTED_ROOT[scenario], f"{scenario}: got {root}"
    conf = (open_incs[0].get("rootCause") or {}).get("confidence", 0)
    assert conf >= 0.55
