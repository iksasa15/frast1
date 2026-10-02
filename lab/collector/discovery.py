"""Live CDP/LLDP discovery. No lab addresses or device names are embedded."""
from __future__ import annotations

import json
import re
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable


def slug(value: str) -> str:
    value = value.split(".")[0].strip().lower()
    return re.sub(r"[^a-z0-9_-]+", "-", value).strip("-") or "unknown"


def normalize_port(value: str) -> str:
    port = value.strip().lower().replace(" ", "")
    for long, short in (("tengigabitethernet", "te"), ("gigabitethernet", "gi"), ("fastethernet", "fa"), ("ethernet", "et")):
        if port.startswith(long):
            return short + port[len(long):]
    return port


def _blocks(text: str, marker: str) -> list[str]:
    starts = [m.start() for m in re.finditer(marker, text, re.I | re.M)]
    return [text[start : starts[i + 1] if i + 1 < len(starts) else None] for i, start in enumerate(starts)]


def parse_cdp(text: str) -> list[dict]:
    found = []
    for block in _blocks(text, r"^Device ID\s*:"):
        name = re.search(r"^Device ID\s*:\s*(.+)$", block, re.I | re.M)
        ports = re.search(r"Interface\s*:\s*([^,\r\n]+).*?Port ID \(outgoing port\)\s*:\s*([^\r\n]+)", block, re.I | re.S)
        if not name or not ports:
            continue
        ip = re.search(r"(?:IP address|IPv4 Address)\s*:\s*([0-9.]+)", block, re.I)
        platform = re.search(r"Platform\s*:\s*([^,\r\n]+)", block, re.I)
        capabilities = re.search(r"Capabilities\s*:\s*([^\r\n]+)", block, re.I)
        found.append({
            "name": name.group(1).strip(), "localPort": ports.group(1).strip(),
            "remotePort": ports.group(2).strip(), "managementIp": ip.group(1) if ip else "",
            "platform": platform.group(1).strip() if platform else "",
            "capabilities": capabilities.group(1).strip() if capabilities else "", "protocol": "cdp",
        })
    return found


def parse_lldp(text: str) -> list[dict]:
    found = []
    for block in _blocks(text, r"^(?:Local Intf|Local Interface)\s*:"):
        local = re.search(r"^(?:Local Intf|Local Interface)\s*:\s*(.+)$", block, re.I | re.M)
        remote = re.search(r"^(?:Port id|Port ID)\s*:\s*(.+)$", block, re.I | re.M)
        name = re.search(r"^(?:System Name|System name)\s*:\s*(.+)$", block, re.I | re.M)
        if not local or not remote or not name:
            continue
        ip = re.search(r"(?:Management Address|Management address)\s*:\s*([0-9.]+)", block, re.I)
        desc = re.search(r"^System Description\s*:\s*(.+)$", block, re.I | re.M)
        caps = re.search(r"^Enabled Capabilities\s*:\s*(.+)$", block, re.I | re.M)
        found.append({
            "name": name.group(1).strip(), "localPort": local.group(1).strip(),
            "remotePort": remote.group(1).strip(), "managementIp": ip.group(1) if ip else "",
            "platform": desc.group(1).strip() if desc else "", "capabilities": caps.group(1).strip() if caps else "",
            "protocol": "lldp",
        })
    return found


def classify(platform: str, capabilities: str) -> str:
    value = f"{platform} {capabilities}".lower()
    if any(word in value for word in ("linuxl2", "ios-l2", "ethernet switch")):
        return "switch"
    if any(word in value for word in ("router", "rtr")):
        return "router"
    if any(word in value for word in ("switch", "bridge", "ios-l2")):
        return "switch"
    if any(word in value for word in ("cisco ios", "ios software", "iol")):
        return "router"
    return "server"


@dataclass(frozen=True)
class Seed:
    host: str
    username: str
    password: str
    device_type: str = "cisco_ios"
    port: int = 22


class Discoverer:
    def __init__(self, seeds: list[Seed], connector: Callable | None = None, max_devices: int = 100):
        self.seeds, self.max_devices = seeds, max_devices
        self.connector = connector or self._netmiko_connect

    @staticmethod
    def _netmiko_connect(seed: Seed):
        from netmiko import ConnectHandler
        return ConnectHandler(device_type=seed.device_type, host=seed.host, username=seed.username,
                              password=seed.password, port=seed.port, conn_timeout=8,
                              auth_timeout=8, banner_timeout=8)

    def run(self, site: str, collector_id: str) -> dict:
        queue, attempted, nodes, observations, errors = list(self.seeds), set(), {}, [], []
        creds = self.seeds[0] if self.seeds else None
        while queue and len(attempted) < self.max_devices:
            seed = queue.pop(0)
            if seed.host in attempted:
                continue
            attempted.add(seed.host)
            try:
                conn = self.connector(seed)
                prompt = conn.find_prompt().rstrip("#>").strip()
                version = conn.send_command("show version")
                cdp = conn.send_command("show cdp neighbors detail")
                lldp = conn.send_command("show lldp neighbors detail")
                conn.disconnect()
            except Exception as exc:
                errors.append(f"{seed.host}: {type(exc).__name__}: {exc}")
                continue
            node_id = slug(prompt or seed.host)
            nodes[node_id] = self._node(node_id, prompt or seed.host, seed.host, version)
            for neighbor in self._dedupe(parse_cdp(cdp) + parse_lldp(lldp)):
                observations.append((node_id, neighbor))
                remote_id = slug(neighbor["name"])
                nodes.setdefault(remote_id, self._node(remote_id, neighbor["name"], neighbor["managementIp"],
                                                       neighbor["platform"], classify(neighbor["platform"], neighbor["capabilities"])))
                if neighbor["managementIp"] and neighbor["managementIp"] not in attempted and creds:
                    queue.append(Seed(neighbor["managementIp"], creds.username, creds.password, creds.device_type, creds.port))
        local_id = slug(collector_id or socket.gethostname())
        nodes.setdefault(local_id, self._node(local_id, collector_id, "", "Linux collector", "collector"))
        observations.extend((local_id, n) for n in self._local_lldp(errors))
        for _, n in observations:
            nid = slug(n["name"])
            nodes.setdefault(nid, self._node(nid, n["name"], n["managementIp"], n["platform"], classify(n["platform"], n["capabilities"])))
        links = self._links(nodes, observations)
        self._positions(nodes, links, local_id)
        return {"site": site, "vantage": local_id, "collectorId": collector_id,
                "observedAt": datetime.now(timezone.utc).isoformat(), "nodes": list(nodes.values()),
                "links": links, "services": [], "errors": errors}

    @staticmethod
    def _dedupe(neighbors: list[dict]) -> list[dict]:
        out = {}
        for item in neighbors:
            out.setdefault((item["localPort"], slug(item["name"])), item)
        return list(out.values())

    @staticmethod
    def _node(node_id: str, label: str, ip: str, platform: str, kind: str | None = None) -> dict:
        value = platform.lower()
        vendor = "cisco" if "cisco" in value or "ios" in value else "linux" if "linux" in value else "unknown"
        return {"id": node_id, "type": kind or classify(platform, platform), "label": label,
                "vendor": vendor, "managementIp": ip, "platform": platform.splitlines()[0][:200] if platform else "",
                "interfaces": [], "position": {"x": 0, "y": 0}}

    @staticmethod
    def _local_lldp(errors: list[str]) -> list[dict]:
        try:
            result = subprocess.run(["lldpcli", "-f", "json", "show", "neighbors"], capture_output=True,
                                    text=True, timeout=5, check=True)
            interfaces = json.loads(result.stdout).get("lldp", {}).get("interface", [])
            if isinstance(interfaces, dict):
                interfaces = [interfaces]
            out = []
            for row in interfaces:
                for local_port, detail in row.items():
                    chassis = detail.get("chassis", {})
                    if isinstance(chassis, list):
                        chassis = chassis[0] if chassis else {}
                    name, chassis_data = next(iter(chassis.items()), ("unknown", {}))
                    remote_port, _ = next(iter(detail.get("port", {}).items()), ("unknown", {}))
                    out.append({"name": name, "localPort": local_port, "remotePort": remote_port,
                                "managementIp": "", "platform": str(chassis_data.get("descr", "")),
                                "capabilities": "", "protocol": "lldp"})
            return out
        except FileNotFoundError:
            errors.append("local LLDP unavailable: install and enable lldpd")
        except Exception as exc:
            errors.append(f"local LLDP failed: {type(exc).__name__}: {exc}")
        return []

    @staticmethod
    def _add_interface(node: dict, name: str, side: str):
        if not any(item["name"] == name for item in node["interfaces"]):
            node["interfaces"].append({"name": name, "side": side, "speedMbps": 0})

    def _links(self, nodes: dict[str, dict], observations: list[tuple[str, dict]]) -> list[dict]:
        links = {}
        for local_id, item in observations:
            remote_id = slug(item["name"])
            if local_id not in nodes or remote_id not in nodes or local_id == remote_id:
                continue
            endpoints = tuple(sorted(((local_id, normalize_port(item["localPort"])),
                                      (remote_id, normalize_port(item["remotePort"])))))
            if endpoints in links:
                continue
            self._add_interface(nodes[local_id], item["localPort"], "right")
            self._add_interface(nodes[remote_id], item["remotePort"], "left")
            (a, ap), (b, bp) = endpoints
            links[endpoints] = {"id": f"link-{a}-{slug(ap)}-{b}-{slug(bp)}", "source": local_id, "sourcePort": item["localPort"],
                             "target": remote_id, "targetPort": item["remotePort"], "role": "discovered",
                             "protocol": item["protocol"]}
        return list(links.values())

    @staticmethod
    def _positions(nodes: dict[str, dict], links: list[dict], vantage: str):
        adjacency = {nid: set() for nid in nodes}
        for link in links:
            adjacency[link["source"]].add(link["target"]); adjacency[link["target"]].add(link["source"])
        levels, queue = {vantage: 0}, [vantage]
        while queue:
            current = queue.pop(0)
            for neighbor in sorted(adjacency[current]):
                if neighbor not in levels:
                    levels[neighbor] = levels[current] + 1; queue.append(neighbor)
        fallback = max(levels.values(), default=0) + 1
        rows = {}
        for nid in nodes:
            rows.setdefault(levels.get(nid, fallback), []).append(nid)
        for level, ids in rows.items():
            for index, nid in enumerate(sorted(ids)):
                nodes[nid]["position"] = {"x": 140 + level * 260, "y": 100 + index * 180}
