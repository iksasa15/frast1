# Network troubleshooting playbooks (RootIQ)

These guides match the offline simulator scenarios and the vendor problem catalogue patterns.

## Uplink congestion / ازدحام الرابط الصاعد

**Symptoms:** high `link_utilization` on the edge uplink (`link-r1-sw1`), rising latency and discards; web latency and partial DNS failure appear **downstream**.

**Check:**

1. Confirm the root candidate is the uplink, not the web service (dependency suppression).
2. Inspect uplink metrics: utilization, latency_ms, packet_loss, if_out_discards_rate.
3. Confirm blast radius: access switches and app hosts behind the core.

**Remediation (human-approved):** shape/clear congestion playbook for the uplink scenario; never auto-execute on production without Approve.

**Arabic cues:** ازدحام، uplink، الرابط الصاعد، discards، استخدام الرابط.

## DNS failure / فشل DNS

**Symptoms:** `svc-dns` success rate near 0%, high DNS latency; `svc-web` may show HTTP failure as a **dependent** of DNS.

**Check:**

1. Prefer DNS as root when web is suppressed by `svc-dns`.
2. Verify DNS service host (`app01` in the sim campus).
3. Confirm other services that `dependsOn` DNS.

**Remediation:** restart/recover DNS service per playbook after engineer Approve.

**Arabic cues:** فشل DNS، name resolution، dns_success_rate.

## Server spike / ارتفاع حمل الخادم

**Symptoms:** `app01` (or similar) `cpu_percent` / `mem_percent` critical; web latency rises; DNS may show secondary latency.

**Check:**

1. Host metrics vs service metrics — root should be the server when CPU is the earliest strong signal.
2. Confirm which services are hosted on that server.

**Remediation:** host remediation playbook (process/cgroup/restart) after Approve.

**Arabic cues:** ارتفاع الحمل، CPU، ذاكرة، server spike.

## General RCA tips

- Prefer earlier, more severe anomalies on dependency **roots**.
- Services that depend on a failing dependency are often **symptoms**, not causes.
- Always require human Approve before execution; Copilot is read-only.
