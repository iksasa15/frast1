# RootIQ

RootIQ is a live infrastructure-observability and incident-analysis platform. It discovers the network from Cisco CDP and IEEE LLDP observations, renders the observed topology, ingests real telemetry and syslog, correlates symptoms into incidents, and keeps remediation behind explicit human approval.

There is no simulation mode in the production application. On a clean start the topology is empty and reports `waiting`; it becomes `live` only after an authenticated collector snapshot is accepted. The last observed snapshot is persisted at `data/topology-observed.json` so a backend restart does not invent or lose topology state.

## Runtime flow

1. `COLLECTOR-01` connects to one or more configured seed devices over SSH.
2. It runs `show version`, `show cdp neighbors detail`, and `show lldp neighbors detail`.
3. Management addresses found in neighbor output are followed recursively.
4. Local Linux LLDP observations are read from `lldpcli`, allowing the collector-to-switch edge to be identified.
5. The collector sends an authenticated full snapshot to `POST /api/topology/discovery`.
6. The backend validates every node, interface and link before atomically replacing the active graph.
7. The WebSocket pushes the new topology to the UI without a restart.

## Server deployment

```bash
cp .env.example .env
# Set a long random INGEST_TOKEN and production CORS_ORIGINS in .env.
docker compose up -d --build
curl http://127.0.0.1:8000/api/health
```

The UI is served on `http://SERVER_IP:8080` and the API on port `8000`. Until the collector reports, `/api/health` correctly returns a degraded discovery state.

## Collector deployment

On minimal Ubuntu:

```bash
sudo apt update
sudo apt install -y python3-venv lldpd iputils-ping
sudo systemctl enable --now lldpd

sudo python3 -m venv /opt/rootiq/collector-venv
sudo /opt/rootiq/collector-venv/bin/pip install -r /opt/rootiq/lab/collector/requirements.txt
sudo install -d -m 700 /etc/rootiq
sudo cp /opt/rootiq/lab/collector/collector.env.example /etc/rootiq/collector.env
sudo chmod 600 /etc/rootiq/collector.env
# Edit collector.env: backend URL, the shared token, seeds and device credentials.

sudo cp /opt/rootiq/lab/collector/rootiq-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now rootiq-collector
sudo journalctl -u rootiq-collector -f
```

Network-device credentials exist only in `/etc/rootiq/collector.env`; they are not stored in the repository or sent to the frontend.

## Required device behavior

- SSH reachable from the collector.
- CDP and/or LLDP enabled on participating links.
- A management IP advertised in discovery output for every device that should be recursively queried.
- Stable, unique hostnames.
- Linux endpoints should run `lldpd` if they need to appear as linked nodes.

For the current EVE-NG lab, use `10.10.20.1` (R1) and `10.10.20.2` (SW2) as redundant seeds after management SVIs and SSH are configured.

## Optional live services

Set `ROOTIQ_SERVICES_FILE=/etc/rootiq/services.json` on the collector. The file is a JSON array; each `host` must be an ID that was actually discovered:

```json
[
  {
    "id": "svc-web",
    "label": "Application HTTP",
    "host": "app-01",
    "port": 80,
    "dependsOn": []
  }
]
```

This is operator configuration, not generated topology. An unknown host causes discovery submission to fail instead of silently creating a fake node.

## Verification

```bash
cd backend
../.venv/bin/pytest -q

cd ../frontend
npm ci
npm test
npm run build
```

Test fixtures contain deterministic sample events, but they live under `backend/tests/` and are not copied into the production image.
