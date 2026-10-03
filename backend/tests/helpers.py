"""Shared wiring for agent tests: the full simulated stack with an explicit AgentRuntime."""
import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace

from app.agents.runtime import AgentRuntime
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


def build_stack(tmp_path, mode: str = "sim") -> SimpleNamespace:
    topo = TopologyService()
    state = StateStore(topo)
    detector = Detector()
    graph = TopologyGraph(topo.raw)
    correlator = Correlator(graph)
    history = History(str(tmp_path / "history.json"))
    audit = AuditLog()
    demo = {"mode": mode, "scenario": None, "state": "idle", "injectedAt": None}
    agents = AgentRuntime(
        graph=graph, history=history, topology=topo, correlator=correlator,
        detector=detector, audit=audit, postmortem_dir=tmp_path / "postmortems",
    )
    holder: dict = {}
    incidents = IncidentService(
        correlator, graph, history=history, topology=topo, agents=agents
    )
    actions = ActionService(
        incidents, detector=detector, history=history, audit=audit, agents=agents,
        execution_adapter_ref=lambda: holder.get("sim") if mode != "live" else None,
        demo_ref=lambda: demo,
        simulator_ref=lambda: holder.get("sim"),
    )
    incidents.actions = actions
    agents.bind(state=state, demo_ref=lambda: demo, simulator_ref=lambda: holder.get("sim"))
    pipeline = Pipeline(topo, state, detector, incidents)
    pipeline.agents = agents
    agents.bind(pipeline=pipeline)
    sim = Simulator(pipeline)
    holder["sim"] = sim
    return SimpleNamespace(
        topo=topo, state=state, detector=detector, graph=graph, history=history, audit=audit,
        demo=demo, agents=agents, incidents=incidents, actions=actions, pipeline=pipeline, sim=sim,
    )


async def run_scenario(s, scenario: str = "uplink-congestion", warm: int = 40, steps: int = 25):
    """Warm up baselines, inject a fault, let the pipeline diagnose. Returns the open IncidentState."""
    for _ in range(warm):
        await s.sim.step(1.0)
    s.demo.update(scenario=scenario, state="injected", injectedAt=datetime.now(timezone.utc).isoformat())
    s.sim.inject(scenario)
    for _ in range(steps):
        await s.sim.step(1.0)
        await asyncio.sleep(0)
    for inc in list(s.incidents.open.values()):
        await s.incidents.analyze(inc.id)
    return next(iter(s.incidents.open.values()))


async def recover(s, inc):
    """Approve path helper: let metrics recover in the simulator and fast-forward the 15 s clock."""
    for _ in range(25):
        await s.sim.step(1.0)
    s.actions._recovering[inc.id] = time.time() - 30
    await s.actions.recovery_tick()
