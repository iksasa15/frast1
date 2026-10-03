# Isolated uplink-down demo

This control is for the named EVE-NG demo lab only. It is disabled by default and must never be pointed at a production device.

## One-time lab setup

1. On `COLLECTOR-01`, deploy the collector from this revision. It polls each observed Cisco link source port and posts `if_oper_status`; a down port becomes a real RootIQ alert.
2. On the host running `lab_agent.py`, install its existing collector dependency: `pip install -r /opt/rootiq/lab/collector/requirements.txt`.
3. Configure the lab-agent environment from `lab/agent/lab-agent.env.example`. The only accepted lab id is `rootiq-eve-lab`; the network target must be a private address. Set `ROOTIQ_NETWORK_HOST=10.10.20.1` and `ROOTIQ_NETWORK_INTERFACE=Ethernet0/0` only when those are the EVE-NG R1 test uplink.
4. On the RootIQ backend, set `DEMO_ENABLED=1`, `DEMO_LAB_ID=rootiq-eve-lab`, and keep `ROOTIQ_EXECUTION_ENABLED=0` until the basic fault/restore rehearsal has passed.

## Recording flow

1. Wait for live discovery and at least two healthy collector polls.
2. On Operations, press **Trigger lab uplink fault**. The agent sends only `shutdown` to the configured EVE-NG interface.
3. Wait for `if_oper_status=0`; RootIQ maps it to the observed link, opens an incident and offers **Restore the isolated lab uplink**.
4. Use **Restore uplink** for the recording, or approve the remediation card to demonstrate the human gate. Both invoke only the fixed `no shutdown` endpoint.
5. Confirm a subsequent collector poll shows `if_oper_status=1` and the incident resolves.

If any precondition is not true, leave `DEMO_ENABLED=0`; the controls stay hidden and no fault endpoint can be called.
