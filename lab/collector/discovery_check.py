"""Run a one-shot live topology discovery from COLLECTOR-01."""
from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path

from discovery import Discoverer, Seed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Cisco SSH and CDP/LLDP discovery")
    parser.add_argument(
        "--seeds",
        default="10.10.20.1,10.10.20.2,10.10.10.2",
        help="Comma-separated management IPs",
    )
    parser.add_argument("--username", default="rootiq")
    parser.add_argument("--device-type", default="cisco_ios")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--site", default="eve-ng-lab")
    parser.add_argument("--collector-id", default="COLLECTOR-01")
    parser.add_argument("--output", default="/tmp/rootiq-discovery.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = getpass.getpass("Cisco SSH password: ")
    hosts = [host.strip() for host in args.seeds.split(",") if host.strip()]
    seeds = [
        Seed(host, args.username, password, args.device_type, args.port)
        for host in hosts
    ]
    result = Discoverer(seeds).run(args.site, args.collector_id)
    output = Path(args.output)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"Discovered {len(result['nodes'])} nodes and {len(result['links'])} links")
    for node in result["nodes"]:
        print(
            f"NODE {node['id']:<20} type={node['type']:<10} "
            f"ip={node.get('managementIp') or '-'}"
        )
    for link in result["links"]:
        print(
            f"LINK {link['source']}:{link['sourcePort']} -> "
            f"{link['target']}:{link['targetPort']} ({link['protocol']})"
        )
    for error in result["errors"]:
        print(f"ERROR {error}")
    print(f"Full JSON: {output}")
    return 0 if any(node["type"] in ("router", "switch") for node in result["nodes"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
