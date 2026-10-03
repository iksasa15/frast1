# Network operations FAQ (RootIQ)

## How many devices are there? / كم عدد الأجهزة؟

Ask Copilot: “how many devices”, “كم جهاز”, “كم سويتش”.
The authoritative count comes from the **live topology snapshot** (or the sim campus fixture when `ROOTIQ_MODE=sim`), not from this document.
Typical campus layers: edge routers/firewall, core switches, distribution, ToR access switches, servers, collector.

## How many switches / servers / services?

- Switches = nodes with `type=switch` (core, dist, ToR).
- Servers = nodes with `type=server` (apps, DB, storage, compute, jump).
- Services = topology `services[]` (DNS, web, DB, cache, API…).
Copilot should answer with numbers from the current graph and cite **topology**.

## Buildings / zones / المباني

Sim campus zones:

- Edge / DMZ — firewall, edge router, collector, jump
- Core — core switches
- Building 1 (Apps) — app ToRs and application servers
- Building 2 (Data) — DB/storage ToRs and data servers
- Building 3 (Compute) — batch/ML servers

Zone labels appear on the Operations map as colored panels.

## What does healthy / warning / critical mean?

Device and link status comes from live metrics vs thresholds:

- healthy — within baseline
- warning — elevated (e.g. rising latency or util)
- critical — threshold breach (e.g. uplink util near saturation, DNS success ~0%)

## Open incidents / الحوادث المفتوحة

“Are there open incidents?” / “هل فيه حوادث؟” — answered from the incident store, not from static docs.

## Demo scenarios (simulation mode)

When Simulation is active, Demo Controls can inject:

1. **Uplink congestion** — edge uplink `link-r1-sw1` saturates; web/DNS degrade as symptoms.
2. **DNS failure** — `svc-dns` success collapses; web may fail as a dependent.
3. **Server spike** — `app01` CPU/memory spike; web latency rises.

Always **Reset Demo** before injecting another scenario.
