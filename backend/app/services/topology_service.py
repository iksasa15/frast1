import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings


class TopologyError(RuntimeError):
    pass


class TopologyService:
    def __init__(self):
        self._lock = threading.RLock()
        self.state_path = Path(settings.topology_state_path)
        self.raw = self._load_observed()
        self.metadata = self.raw.pop("discovery", self._empty_metadata())
        self.nodes: dict[str, dict] = {}
        self.links: dict[str, dict] = {}
        self.services: dict[str, dict] = {}
        self.port_to_link: dict[tuple[str, str], str] = {}
        self._index()
        self._apply_layout()

    @staticmethod
    def _empty_metadata() -> dict:
        return {
            "state": "waiting",
            "source": "collector",
            "observedAt": None,
            "receivedAt": None,
            "collectorId": None,
            "errors": [],
        }

    def _load_observed(self) -> dict:
        # Fixture topology is sim-only. Live lab always uses discovery state so we never
        # overwrite a connected EVE/collector topology with configs/topology.json.
        if settings.rootiq_mode == "sim" and settings.topology_path:
            data = json.loads(Path(settings.topology_path).read_text(encoding="utf-8"))
            self._validate(data)
            return data
        if not self.state_path.exists():
            return {"site": "undiscovered", "vantage": "", "nodes": [], "links": [], "services": []}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self._validate(data)
            return data
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise TopologyError(f"invalid observed topology state: {exc}") from exc

    def _index(self):
        self._validate(self.raw)
        self.nodes = {n["id"]: n for n in self.raw["nodes"]}
        self.links = {l["id"]: l for l in self.raw["links"]}
        self.services = {s["id"]: s for s in self.raw["services"]}
        self.port_to_link = {}
        for l in self.links.values():
            self.port_to_link[(l["source"], l["sourcePort"])] = l["id"]
            self.port_to_link[(l["target"], l["targetPort"])] = l["id"]

    @staticmethod
    def _validate(raw: dict):
        for key in ("site", "vantage", "nodes", "links", "services"):
            if key not in raw:
                raise TopologyError(f"missing topology field: {key}")
        node_ids = [n["id"] for n in raw["nodes"]]
        if len(node_ids) != len(set(node_ids)):
            raise TopologyError("duplicate node id")
        ids = {n["id"]: {i["name"] for i in n.get("interfaces", [])} for n in raw["nodes"]}
        if raw["nodes"] and raw["vantage"] not in ids:
            raise TopologyError(f"unknown vantage: {raw['vantage']}")
        link_ids: set[str] = set()
        occupied: set[tuple[str, str]] = set()
        for l in raw["links"]:
            if l["id"] in link_ids:
                raise TopologyError(f"duplicate link id: {l['id']}")
            link_ids.add(l["id"])
            for end, port in ((l["source"], l["sourcePort"]), (l["target"], l["targetPort"])):
                if end not in ids or port not in ids[end]:
                    raise TopologyError(f"link {l['id']}: unknown endpoint {end}:{port}")
                endpoint = (end, port)
                if endpoint in occupied:
                    raise TopologyError(f"interface belongs to multiple links: {end}:{port}")
                occupied.add(endpoint)
        service_ids = [s["id"] for s in raw["services"]]
        if len(service_ids) != len(set(service_ids)):
            raise TopologyError("duplicate service id")
        known_services = set(service_ids)
        for s in raw["services"]:
            if s["host"] not in ids:
                raise TopologyError(f"service {s['id']}: unknown host {s['host']}")
            unknown_dependencies = set(s.get("dependsOn", [])) - known_services
            if unknown_dependencies:
                raise TopologyError(f"service {s['id']}: unknown dependencies {sorted(unknown_dependencies)}")

    def replace_observed(self, raw: dict, *, collector_id: str, observed_at: str, errors: list[str] | None = None):
        candidate = deepcopy(raw)
        candidate.setdefault("services", [])
        self._validate(candidate)
        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "state": "degraded" if errors else "live",
            "source": "cdp-lldp",
            "observedAt": observed_at,
            "receivedAt": now,
            "collectorId": collector_id,
            "errors": errors or [],
        }
        with self._lock:
            old_positions = {nid: n.get("position") for nid, n in self.nodes.items()}
            for node in candidate["nodes"]:
                if old_positions.get(node["id"]):
                    node["position"] = old_positions[node["id"]]
            self.raw = candidate
            self.metadata = metadata
            self._index()
            self._apply_layout()
            self._persist()

    def _persist(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.state_path.parent, suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({**self.raw, "discovery": self.metadata}, f, indent=2)
        os.replace(tmp, self.state_path)

    def _apply_layout(self):
        p = Path(settings.layout_path)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            # Support both flat {nid: {x,y}} and {positions: {...}}
            positions = data.get("positions", data) if isinstance(data, dict) else {}
            for nid, pos in positions.items():
                if nid in self.nodes and isinstance(pos, dict) and "x" in pos:
                    self.nodes[nid]["position"] = pos

    def save_layout(self, positions: dict[str, dict]):
        unknown = set(positions) - set(self.nodes)
        if unknown:
            raise TopologyError(f"unknown nodes: {sorted(unknown)}")
        for nid, pos in positions.items():
            self.nodes[nid]["position"] = {"x": float(pos["x"]), "y": float(pos["y"])}
        layout_path = Path(settings.layout_path)
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=layout_path.parent, suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({k: v["position"] for k, v in self.nodes.items()}, f, indent=2)
        os.replace(tmp, layout_path)

    def speed_of(self, link_id: str) -> int:
        l = self.links[link_id]
        src = next(
            i for i in self.nodes[l["source"]]["interfaces"] if i["name"] == l["sourcePort"]
        )
        return int(src.get("speedMbps", 0))

    def snapshot(self) -> dict:
        nodes = []
        for n in self.nodes.values():
            nodes.append({**n, "status": n.get("status", "healthy"), "metrics": n.get("metrics", {})})
        links = []
        for l in self.links.values():
            links.append(
                {
                    **l,
                    "speedMbps": self.speed_of(l["id"]),
                    "status": l.get("status", "healthy"),
                    "utilization": l.get("utilization", 0),
                    "latencyMs": l.get("latencyMs", 0),
                    "packetLoss": l.get("packetLoss", 0),
                }
            )
        services = [
            {**s, "status": s.get("status", "healthy"), "metrics": s.get("metrics", {})}
            for s in self.services.values()
        ]
        return {
            "site": self.raw["site"],
            "vantage": self.raw["vantage"],
            "nodes": nodes,
            "links": links,
            "services": services,
            "discovery": {**deepcopy(self.metadata), "staleAfterSeconds": settings.discovery_stale_after_s},
        }

    def get_device(self, device_id: str) -> dict | None:
        n = self.nodes.get(device_id)
        if not n:
            return None
        return {**n, "status": n.get("status", "healthy"), "metrics": n.get("metrics", {})}
