# Judge Q&A bank

Short answers for the pitch. Pair with `docs/ARCHITECTURE.md` and `docs/RESULTS.md`.

| Question | Answer |
|---|---|
| Is this real AI or just rules? | Hybrid on purpose: statistical baseline + optional multivariate Isolation Forest + graph reasoning + weighted ranking you can explain. Rules alone don’t generalize; pure ML needs labeled outages we don’t have — hybrid gives explainability, reliability, and a growth path. |
| How do you scale to thousands of devices? | Analysis runs on the **correlated symptom set**, not the whole fabric; graph path ops scale with the incident. Collectors are distributed and push a normalized schema. Auto-discovery via CDP/LLDP is in the Pilot roadmap. |
| What if RCA is wrong? | We show confidence, evidence, and candidates. If confidence &lt; 55% we say it needs investigation. **Nothing executes without human approval.** |
| Why not use an LLM for analysis? | LLM is for wording only and is grounded: any number not in measured evidence is rejected and we fall back to the template. Ranking itself is deterministic and auditable. |
| vs Datadog / Dynatrace / Splunk ITSI? | Vendor-neutral, light, hybrid + classic networks (SNMP/Syslog)—not cloud APM only—ties physical ports to services, with an approval loop built in. Private deploy fits data-sovereignty needs (e.g. KSA). |
| How do you learn over time? | Resolved, approved incidents bump `historical_support` for that root — confidence rises on later runs. Later: learn weights from closed incidents. |
| Security? | Read-only SNMP where possible, lab agent runs a **fixed whitelist** only, secrets in env, every decision in the audit log, full simulation mode. |
| Business model? | Subscription by monitored assets + enterprise integration + private deploy. First customers: enterprise NOCs, MSPs, DC/cloud ops. |
| What’s next? | Pilot with a real NOC: auto-discovery, broad SNMP, RBAC, ITSM hooks, then capacity foresight and change-impact analysis. |
| Is the data real or fake? | Live path uses a real EVE-NG lab (virtual Cisco + real iperf3). Sim mode is the backup and is **labeled on screen** when used. Measured numbers in `RESULTS.md` are from sim lab runs on this build (live lab fills the same table when available). |
| Is it really a multi-agent system? | Yes — 16 agents, each with one job, explicit inputs/outputs, limited tools and a traceable step (Agents page → Live trace). Fourteen are deterministic; only Explanation and the Copilot can use an LLM, optionally. |
| Can the AI act on its own? | No. Advisors only recommend. The Execution agent refuses without a named human approval **and** a fresh Guardrail verdict; `system` / `agent:*` approvals get HTTP 403 and are audited. |
| What if the LLM hallucinates? | Any number not present in the measured facts rejects the answer and we fall back to the template; Copilot answers must also cite sources. Everything works with the LLM off. |
| Can someone poison the docs to hijack the assistant? | Retrieved text is treated as data, injection-looking passages are excluded and flagged, and the Copilot has no tool that can approve, reject or execute. |
| Does it only work with Cisco? | No. A knowledge base of 43 vendors (5 with full coverage: Cisco, Juniper, Arista, Huawei, HPE/Aruba; Fortinet and 6 others partial; the rest identification-only) feeds the `vendor` and `logs` agents. The demo lab is Cisco because that is what EVE-NG runs; `configs/topology.multivendor.example.json` shows a Cisco + Juniper + Arista + Fortinet + Aruba network. |
| Does it know every switch model and OS version? | No, and it says so. It knows **families/series** (103) and OS version schemes, not every SKU; each vendor carries `coverage` and `confidence`, and an unknown vendor gets «no curated command», never an invented one. |
| How do you handle vendors that save configuration differently? | Each OS has a `config_model`: running→startup (`write memory`), candidate→`commit` (Junos, `commit confirmed`), or auto-save (FortiOS), plus restore point and rollback. Shown to the engineer in the plan and answered by the Copilot. |
| Will RootIQ run vendor commands on my devices? | No. Diagnostic commands are shown as reference text and are validated as read-only (allow-list + deny-list, re-checked by the Guardrail); fixes need approval and are never pushed. Only the whitelisted playbook runs after a named engineer approves. |
| Where do the vendor commands come from? Are they verified? | Written from general public knowledge, checked by tests for internal consistency (regex examples, read-only rules, IANA enterprise numbers). **Not captured from real devices yet**: confidence is stated per vendor (Fortinet is the weakest). Adding real captures is a JSON edit. |
| What does fine-tuning add? | A private/offline model that already speaks the output formats (device identity JSON, normalized syslog, vendor commands) and refuses to act. Ship rule: no regression on the base model, zero unsafe commands, no more invented commands than the base model. The knowledge base stays the source of truth. |
| Why 16 agents and not one big model? | Small units are testable, auditable and degrade independently (a slow LLM never blocks an incident); a single model would be a black box with execution risk. |
| How do the agents learn? | The Learning agent records confirmed root causes (raising confidence next time), writes a postmortem and feeds it back into the knowledge index. Weights and thresholds are never changed automatically. |

## Who answers what

| Topic | Owner |
|---|---|
| Demo keyboard / UI | FE (Ahmed) |
| Ingest, actions, audit | BE |
| Ranking / evidence / LLM grounding | AI |
| EVE / collector / agent | INFRA |
| Story + business | Presenter |
