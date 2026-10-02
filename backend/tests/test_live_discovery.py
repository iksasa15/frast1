from pathlib import Path
import sys

from app.core.config import settings
from app.services.topology_service import TopologyService

COLLECTOR_DIR = Path(__file__).resolve().parents[2] / "lab" / "collector"
sys.path.insert(0, str(COLLECTOR_DIR))
from discovery import parse_cdp  # noqa: E402


def test_cdp_parser_uses_observed_names_ports_and_management_address():
    output = """
Device ID: SW1.rootiq.lab
Entry address(es):
  IP address: 10.10.10.2
Platform: Cisco IOL L2, Capabilities: Switch IGMP
Interface: Ethernet0/0, Port ID (outgoing port): Ethernet0/1
Holdtime : 122 sec
"""
    assert parse_cdp(output) == [
        {
            "name": "SW1.rootiq.lab",
            "localPort": "Ethernet0/0",
            "remotePort": "Ethernet0/1",
            "managementIp": "10.10.10.2",
            "platform": "Cisco IOL L2",
            "capabilities": "Switch IGMP",
            "protocol": "cdp",
        }
    ]


def test_topology_can_be_replaced_atomically_from_live_observation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "topology_path", "")
    monkeypatch.setattr(settings, "topology_state_path", str(tmp_path / "observed.json"))
    monkeypatch.setattr(settings, "layout_path", str(tmp_path / "layout.json"))
    topology = TopologyService()
    observed = {
        "site": "lab",
        "vantage": "collector-01",
        "nodes": [
            {"id": "collector-01", "type": "collector", "label": "COLLECTOR-01", "managementIp": "10.10.20.10", "interfaces": [{"name": "ens3", "side": "right", "speedMbps": 1000}], "position": {"x": 0, "y": 0}},
            {"id": "sw2", "type": "switch", "label": "SW2", "managementIp": "10.10.20.2", "interfaces": [{"name": "Ethernet0/1", "side": "left", "speedMbps": 1000}], "position": {"x": 200, "y": 0}},
        ],
        "links": [{"id": "link-collector-01-sw2", "source": "collector-01", "sourcePort": "ens3", "target": "sw2", "targetPort": "Ethernet0/1", "role": "discovered"}],
        "services": [],
    }
    topology.replace_observed(observed, collector_id="COLLECTOR-01", observed_at="2026-10-01T00:00:00+00:00")

    assert set(topology.nodes) == {"collector-01", "sw2"}
    assert set(topology.links) == {"link-collector-01-sw2"}
    assert topology.metadata["state"] == "live"
    assert (tmp_path / "observed.json").exists()
