"""Whitelist-only lab agent. No free-form command execution."""
import os
import subprocess
import ipaddress

from fastapi import FastAPI, Header, HTTPException

TOKEN = os.environ["LAB_AGENT_TOKEN"]
APP = os.environ["ROOTIQ_APP_SSH_TARGET"]
IPERF_TARGET = os.environ["ROOTIQ_IPERF_TARGET"]
DEMO_ENABLED = os.environ.get("ROOTIQ_DEMO_ENABLED") == "1"
LAB_ID = os.environ.get("ROOTIQ_DEMO_LAB_ID", "")
NETWORK_HOST = os.environ.get("ROOTIQ_NETWORK_HOST", "")
NETWORK_USER = os.environ.get("ROOTIQ_NETWORK_USERNAME", "")
NETWORK_PASSWORD = os.environ.get("ROOTIQ_NETWORK_PASSWORD", "")
NETWORK_INTERFACE = os.environ.get("ROOTIQ_NETWORK_INTERFACE", "Ethernet0/0")
app = FastAPI(title="RootIQ Lab Agent")
procs: dict[str, subprocess.Popen] = {}


def auth(token: str | None):
    if token != TOKEN:
        raise HTTPException(status_code=401)


def start_iperf():
    stop_iperf()
    procs["iperf"] = subprocess.Popen(
        ["iperf3", "-c", IPERF_TARGET, "-u", "-b", "15M", "-t", "900"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_iperf():
    p = procs.pop("iperf", None)
    if p and p.poll() is None:
        p.terminate()


def ssh_app(cmd: str) -> str:
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=3", APP, cmd],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if r.returncode not in (0, 1):
        raise RuntimeError(r.stderr.strip())
    return r.stdout


def require_isolated_demo():
    if not DEMO_ENABLED or LAB_ID != "rootiq-eve-lab":
        raise HTTPException(status_code=403, detail="uplink-down is disabled outside the named EVE-NG demo lab")
    try:
        if not ipaddress.ip_address(NETWORK_HOST).is_private:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=403, detail="demo network target must be a private lab address")
    if not (NETWORK_USER and NETWORK_PASSWORD):
        raise HTTPException(status_code=503, detail="demo network credentials are not configured")


def set_uplink(admin_up: bool):
    require_isolated_demo()
    from netmiko import ConnectHandler
    with ConnectHandler(device_type="cisco_ios", host=NETWORK_HOST, username=NETWORK_USER, password=NETWORK_PASSWORD) as conn:
        conn.send_config_set([f"interface {NETWORK_INTERFACE}", "no shutdown" if admin_up else "shutdown"])


INJECT = {
    "uplink-congestion": start_iperf,
    "dns-failure": lambda: ssh_app("sudo /usr/bin/systemctl stop named"),
    "server-spike": lambda: ssh_app(
        "nohup stress-ng --cpu 2 --cpu-load 100 --timeout 900s >/dev/null 2>&1 &"
    ),
    "uplink-down": lambda: set_uplink(False),
}

REMEDIATE = {
    "dns-failure": lambda: ssh_app("sudo /usr/bin/systemctl start named"),
    "server-spike": lambda: ssh_app("pkill -f stress-ng || true"),
    "uplink-congestion": stop_iperf,
    "uplink-down": lambda: set_uplink(True),
}


@app.post("/inject/{scenario}")
def inject(scenario: str, x_agent_token: str | None = Header(None)):
    auth(x_agent_token)
    if scenario not in INJECT:
        raise HTTPException(status_code=404)
    INJECT[scenario]()
    return {"ok": True, "scenario": scenario}


@app.post("/remediate/{scenario}")
def remediate(scenario: str, x_agent_token: str | None = Header(None)):
    auth(x_agent_token)
    if scenario not in REMEDIATE:
        raise HTTPException(status_code=404)
    out = REMEDIATE[scenario]()
    return {"ok": True, "output": str(out)[-500:] if out else ""}


@app.post("/reset")
def reset(x_agent_token: str | None = Header(None)):
    auth(x_agent_token)
    stop_iperf()
    try:
        ssh_app("sudo /usr/bin/systemctl start named")
    except Exception:
        pass
    try:
        ssh_app("pkill -f stress-ng || true")
    except Exception:
        pass
    return {"ok": True}


@app.get("/health")
def health():
    return {
        "ok": True,
        "iperfRunning": bool(procs.get("iperf") and procs["iperf"].poll() is None),
    }
