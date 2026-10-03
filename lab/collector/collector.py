"""RootIQ live collector: discovers topology and sends observed telemetry."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone

import httpx

from discovery import Discoverer, Seed, interface_is_up

BACKEND = os.environ["ROOTIQ_BACKEND"].rstrip("/")
TOKEN = os.environ["ROOTIQ_INGEST_TOKEN"]
SITE = os.environ.get("ROOTIQ_SITE", "eve-ng-lab")
COLLECTOR_ID = os.environ.get("ROOTIQ_COLLECTOR_ID", os.uname().nodename)
DISCOVERY_INTERVAL = float(os.environ.get("ROOTIQ_DISCOVERY_INTERVAL", "60"))
POLL_INTERVAL = float(os.environ.get("ROOTIQ_POLL_INTERVAL", "5"))


def load_services(node_ids: set[str]) -> list[dict]:
    """Load real monitored services declared by the operator, never sample defaults."""
    path = os.environ.get("ROOTIQ_SERVICES_FILE", "")
    if not path:
        return []
    with open(path, encoding="utf-8") as handle:
        services = json.load(handle)
    if not isinstance(services, list):
        raise ValueError("ROOTIQ_SERVICES_FILE must contain a JSON array")
    unknown = {item.get("host") for item in services} - node_ids
    if unknown:
        raise ValueError(f"service hosts were not discovered: {sorted(unknown)}")
    return services


def load_seeds() -> list[Seed]:
    raw = os.environ.get("ROOTIQ_SEEDS", "")
    if not raw:
        raise RuntimeError("ROOTIQ_SEEDS is required (comma-separated management IPs)")
    username = os.environ["ROOTIQ_DEVICE_USERNAME"]
    password = os.environ["ROOTIQ_DEVICE_PASSWORD"]
    device_type = os.environ.get("ROOTIQ_DEVICE_TYPE", "cisco_ios")
    port = int(os.environ.get("ROOTIQ_DEVICE_PORT", "22"))
    return [Seed(host.strip(), username, password, device_type, port) for host in raw.split(",") if host.strip()]


def event(source_id: str, source_type: str, metric: str, value: float, unit: str, **metadata):
    return {"sourceId": source_id, "sourceType": source_type, "metric": metric, "value": value,
            "unit": unit, "timestamp": datetime.now(timezone.utc).isoformat(), "metadata": metadata}


def ping(ip: str) -> tuple[float, float]:
    result = subprocess.run(["ping", "-n", "-q", "-c", "3", "-W", "1", ip], capture_output=True,
                            text=True, timeout=5)
    loss_match = re.search(r"([\d.]+)% packet loss", result.stdout)
    timing_match = re.search(r"= [\d.]+/([\d.]+)/", result.stdout)
    return (float(timing_match.group(1)) if timing_match else 1000.0,
            float(loss_match.group(1)) if loss_match else 100.0)


def poll_nodes(topology: dict) -> list[dict]:
    events = []
    for node in topology.get("nodes", []):
        ip = node.get("managementIp")
        if not ip:
            continue
        try:
            latency, loss = ping(ip)
        except Exception:
            latency, loss = 1000.0, 100.0
        events.extend([
            event(node["id"], node["type"], "reachability", 0 if loss == 100 else 1, "bool", collector="icmp"),
            event(node["id"], node["type"], "icmp_latency_ms", latency, "ms", collector="icmp"),
            event(node["id"], node["type"], "icmp_packet_loss", loss, "percent", collector="icmp"),
        ])
    return events


def poll_link_oper(topology: dict, seeds: list[Seed]) -> list[dict]:
    """Poll the observed source port of every link.

    A failed SSH poll is skipped rather than reported as a down interface, so a
    collector/connectivity problem cannot manufacture a link-down incident.
    Credentials stay on COLLECTOR-01.
    """
    if not seeds:
        return []
    out = []
    for link in topology.get("links", []):
        node = next((n for n in topology.get("nodes", []) if n["id"] == link["source"]), None)
        if not node or node.get("type") not in ("router", "switch") or not node.get("managementIp"):
            continue
        seed = Seed(node["managementIp"], seeds[0].username, seeds[0].password, seeds[0].device_type, seeds[0].port)
        try:
            conn = Discoverer._netmiko_connect(seed)
            raw = conn.send_command(f"show interfaces {link['sourcePort']}")
            conn.disconnect()
            value = interface_is_up(raw)
        except Exception:
            continue
        out.append(event(node["id"], node["type"], "if_oper_status", value, "bool", interface=link["sourcePort"], collector="netmiko"))
    return out


async def push_discovery(client: httpx.AsyncClient, discoverer: Discoverer) -> dict:
    topology = await asyncio.to_thread(discoverer.run, SITE, COLLECTOR_ID)
    if not any(node["type"] in ("router", "switch") for node in topology["nodes"]):
        raise RuntimeError("no network seed was reachable; keeping the backend's last observed topology")
    topology["services"] = load_services({node["id"] for node in topology["nodes"]})
    response = await client.post(f"{BACKEND}/api/topology/discovery", json=topology,
                                 headers={"x-rootiq-token": TOKEN})
    response.raise_for_status()
    return topology


async def main():
    seeds = load_seeds()
    discoverer = Discoverer(seeds)
    topology: dict = {"nodes": []}
    next_discovery = 0.0
    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            started = time.monotonic()
            if started >= next_discovery:
                try:
                    topology = await push_discovery(client, discoverer)
                    print(json.dumps({"event": "topology_discovered", "nodes": len(topology["nodes"]),
                                      "links": len(topology["links"]), "errors": topology["errors"]}))
                except Exception as exc:
                    print(json.dumps({"event": "discovery_failed", "error": str(exc)}))
                next_discovery = started + DISCOVERY_INTERVAL
            events = await asyncio.to_thread(poll_nodes, topology)
            events.extend(await asyncio.to_thread(poll_link_oper, topology, seeds))
            if events:
                try:
                    response = await client.post(f"{BACKEND}/api/events/batch", json={"events": events},
                                                 headers={"x-rootiq-token": TOKEN})
                    response.raise_for_status()
                except Exception as exc:
                    print(json.dumps({"event": "telemetry_push_failed", "error": str(exc)}))
            await asyncio.sleep(max(0.0, POLL_INTERVAL - (time.monotonic() - started)))


if __name__ == "__main__":
    asyncio.run(main())
