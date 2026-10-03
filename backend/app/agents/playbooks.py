"""Whitelisted remediation playbooks — the ONLY things RootIQ can ever propose or run.

Each root-cause kind maps to exactly one playbook. Commands here are documentation of what a
change looks like; what the lab agent really executes is a fixed endpoint per scenario
(`/remediate/<scenario>`), noted in `labImplementation`.
"""
from __future__ import annotations

PLAYBOOKS: dict[str, dict] = {
    "link-down": {
        "id": "PB-LINK-RESTORE",
        "actionType": "restore_lab_uplink",
        "scenario": "uplink-down",
        "risk": "low",
        "title": "Restore the isolated lab uplink",
        "description": "Re-enable the pre-approved EVE-NG lab interface after verifying the incident.",
        "alternatives": ["Keep the fault for further diagnosis", "Restore through the lab console"],
        "blastRadius": "Only the named EVE-NG lab uplink; no production target is accepted by the lab agent.",
        "preconditions": ["Observed if_oper_status is down", "Isolated EVE-NG lab only", "A named human engineer approves"],
        "steps": [{"n": 1, "kind": "read", "title": "Verify the affected lab interface is administratively down"}, {"n": 2, "kind": "change", "title": "Restore the pre-approved lab uplink", "command": "interface Ethernet0/0 ; no shutdown"}, {"n": 3, "kind": "verify", "title": "Confirm interface operational status is up within 60 s"}],
        "rollback": [{"title": "Reapply the demo fault only if the recording must be repeated", "command": "interface Ethernet0/0 ; shutdown"}],
        "verification": [{"entity": "{root}", "metric": "if_oper_status", "op": ">", "value": 0.5}],
        "expectedEffect": "The link returns to healthy and RootIQ records verified recovery.",
        "labImplementation": "The isolated lab agent runs only its fixed /remediate/uplink-down endpoint.",
    },
    "link": {
        "id": "PB-LINK-QOS",
        "actionType": "apply_qos_policy",
        "scenario": "uplink-congestion",
        "risk": "low",
        "title": "Relieve a congested uplink with QoS",
        "description": (
            "Apply UPLINK-QOS on R1 Gi0/0: police bulk traffic (port 5201) to 2 Mbps "
            "and fair-queue critical flows."
        ),
        "alternatives": ["Activate an alternate path", "Increase uplink capacity"],
        "blastRadius": "Only traffic leaving R1 Gi0/0; bulk flows on port 5201 are policed, all other flows are fair-queued.",
        "preconditions": [
            "Root cause is a link with sustained utilization above the critical threshold",
            "Policy UPLINK-QOS is defined on the router (see lab/configs/r1.cfg)",
            "Isolated live lab only (never a production device)",
        ],
        "steps": [
            {"n": 1, "kind": "read", "title": "Snapshot interface counters and current service-policy on {label}"},
            {
                "n": 2,
                "kind": "change",
                "title": "Attach policy UPLINK-QOS to the congested interface (output)",
                "command": "interface Gi0/0 ; service-policy output UPLINK-QOS",
            },
            {"n": 3, "kind": "verify", "title": "Confirm utilization < 70%, latency < 30 ms and packet loss < 1% within 60 s"},
        ],
        "rollback": [
            {
                "title": "Restore the previous shaping policy",
                "command": "interface Gi0/0 ; service-policy output UPLINK-SHAPE",
            }
        ],
        "verification": [
            {"entity": "{root}", "metric": "link_utilization", "op": "<", "value": 70},
            {"entity": "{root}", "metric": "link_latency_ms", "op": "<", "value": 30},
            {"entity": "{root}", "metric": "link_packet_loss", "op": "<", "value": 1},
        ],
        "expectedEffect": "Bulk traffic is capped; latency and loss return to baseline while critical flows keep their share.",
        "labImplementation": "Demo lab agent stops the injected iperf3 load generator (/remediate/uplink-congestion); applying QoS via Netmiko is the production path after governance review.",
    },
    "svc-dns": {
        "id": "PB-DNS-RESTART",
        "actionType": "restart_dns_service",
        "scenario": "dns-failure",
        "risk": "low",
        "title": "Restore the internal DNS service",
        "description": "Restart the 'named' DNS service on APP-01.",
        "alternatives": ["Fail over to secondary DNS"],
        "blastRadius": "DNS resolution on APP-01 for a few seconds during the restart; the web service depends on it.",
        "preconditions": [
            "DNS success rate is failing while APP-01 itself is reachable",
            "Service 'named' is installed on APP-01",
        ],
        "steps": [
            {"n": 1, "kind": "read", "title": "Check 'named' status and last log lines on APP-01"},
            {"n": 2, "kind": "change", "title": "Start the DNS service", "command": "sudo systemctl start named"},
            {"n": 3, "kind": "verify", "title": "Confirm DNS success rate > 95% and DNS latency < 100 ms"},
        ],
        "rollback": [{"title": "Stop the DNS service again if it flaps", "command": "sudo systemctl stop named"}],
        "verification": [
            {"entity": "{root}", "metric": "dns_success_rate", "op": ">", "value": 95},
            {"entity": "{root}", "metric": "dns_latency_ms", "op": "<", "value": 100},
        ],
        "expectedEffect": "Name resolution recovers and the web service stops failing on hostname lookups.",
        "labImplementation": "Lab agent runs the fixed command: ssh app01 'sudo /usr/bin/systemctl start named'.",
    },
    "server": {
        "id": "PB-SERVER-KILL-RUNAWAY",
        "actionType": "stop_runaway_process",
        "scenario": "server-spike",
        "risk": "medium",
        "title": "Stop a runaway process on the application server",
        "description": "Terminate the runaway CPU process on APP-01 (stress-ng).",
        "alternatives": ["Scale out the web tier", "Move workload to standby node"],
        "blastRadius": "Only the offending process on APP-01; legitimate services are untouched.",
        "preconditions": [
            "CPU is above the critical threshold and the top process is not a known service",
            "Operator confirms the process is not business critical",
        ],
        "steps": [
            {"n": 1, "kind": "read", "title": "List top CPU processes on APP-01"},
            {"n": 2, "kind": "change", "title": "Terminate the runaway process", "command": "pkill -f stress-ng"},
            {"n": 3, "kind": "verify", "title": "Confirm CPU < 80% and web latency < 300 ms"},
        ],
        "rollback": [{"title": "Restart the terminated job if it was legitimate", "command": "(re-run the original job)"}],
        "verification": [
            {"entity": "{root}", "metric": "cpu_percent", "op": "<", "value": 80},
            {"entity": "svc-web", "metric": "http_latency_ms", "op": "<", "value": 300},
        ],
        "expectedEffect": "CPU returns to baseline and the web service latency drops.",
        "labImplementation": "Lab agent runs the fixed command: ssh app01 'pkill -f stress-ng'.",
    },
}

WIDE_BLAST_ELEMENTS = 7  # more downstream elements than this counts as a wide blast radius
ALLOWED_ACTIONS = {p["actionType"] for p in PLAYBOOKS.values()}


def kind_for_entity(entity_id: str) -> str:
    if entity_id.startswith("link-"):
        return "link"
    if entity_id == "svc-dns" or entity_id.startswith("svc-dns"):
        return "svc-dns"
    return "server"
