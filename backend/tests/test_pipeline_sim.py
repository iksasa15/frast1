import pytest

from tests.simulator_fixture import Simulator
from app.intelligence.correlate import Correlator
from app.intelligence.detector import Detector
from app.intelligence.graph import TopologyGraph
from app.intelligence.history import History
from app.services.incident_service import IncidentService
from app.services.pipeline import Pipeline
from app.services.state_store import StateStore
from app.services.topology_service import TopologyService


@pytest.mark.asyncio
async def test_pipeline_sim_uplink_alerts(tmp_path):
    topo = TopologyService()
    state = StateStore(topo)
    detector = Detector()
    graph = TopologyGraph(topo.raw)
    correlator = Correlator(graph)
    demo = {"mode": "sim", "scenario": None, "state": "idle", "injectedAt": None}
    history = History(str(tmp_path / "history.json"))
    incidents = IncidentService(
        correlator, graph, history=history, topology=topo
    )
    pipeline = Pipeline(topo, state, detector, incidents)
    sim = Simulator(pipeline)

    for _ in range(60):
        await sim.step(1.0)

    before = len(pipeline.alerts)
    demo.update(scenario="uplink-congestion", state="injected", injectedAt="t0")
    sim.inject("uplink-congestion")

    for _ in range(20):
        await sim.step(1.0)

    util_alerts = [
        a
        for a in pipeline.alerts
        if a["sourceId"] == "link-r1-sw1" and a["metric"] == "link_utilization"
    ]
    assert util_alerts, "expected raw alert on link-r1-sw1 utilization"
    new_alerts = len(pipeline.alerts) - before
    assert 5 <= len(pipeline.alerts) <= 40 or new_alerts >= 5

    open_incs = [i for i in incidents.list_incidents() if i["status"] != "resolved"]
    assert len(open_incs) == 1
    members = set(open_incs[0].get("members") or [])
    assert "link-r1-sw1" in members
    assert open_incs[0]["rawAlertCount"] >= 3
