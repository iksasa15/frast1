"""Wiring audit: starts the real application on the multi-vendor example topology, calls its API, and checks that the
numbers and files stated in the docs, the notebook, the GitHub automation and the frontend agree with the code.

    python scripts/audit_wiring.py            # from the repository root, with the backend requirements installed

Exit code 1 if anything is out of step. Runs headless with explicit test fixtures and is part of CI.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("INGEST_TOKEN", "audit-only-ingest-token")
os.environ.setdefault("LAB_AGENT_TOKEN", "audit-only-agent-token")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((bool(ok), name, detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ------------------------------------------------------------------ 1) the live application
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import settings  # noqa: E402

settings.topology_path = str(ROOT / "configs" / "topology.multivendor.example.json")
from app.knowledge import get_kb  # noqa: E402
from app.main import app  # noqa: E402

kb = get_kb()
stats = kb.stats()
with TestClient(app) as c:
    check("GET /api/health", c.get("/api/health").status_code == 200)

    ag = c.get("/api/agents").json()
    ids = [a["id"] for a in ag["agents"]]
    n_agents = len(ids)
    check("vendor and logs agents are in the roster and in the flow", {"vendor", "logs"} <= set(ids) and all(k in json.dumps(ag["flow"]) for k in ("vendor", "logs")), f"{n_agents} agents")

    v = c.get("/api/vendors").json()
    check("/api/vendors lists every vendor of the knowledge base", v["stats"]["vendors"] == stats["vendors"] == len(v["vendors"]), f"{stats['vendors']} vendors")

    inv = {d["id"]: d for d in c.get("/api/vendors/inventory").json()}
    want = {"r1": "cisco", "swjun": "juniper", "swarista": "arista", "fw1": "fortinet", "swaruba": "hpe-aruba"}
    got = {k: inv.get(k, {}).get("vendor") for k in want}
    check("inventory identifies the five lab vendors", got == want, str(got))
    check("every identified device carries its config model", all(inv[k].get("configModel") for k in want))

    for label, sys_descr, vendor, os_id in (
        ("FortiOS", "FortiGate-VM64-KVM v7.4.3,build2573,240226 (GA.M)", "fortinet", "fortios"),
        ("Junos", "Juniper Networks, Inc. vqfx-10000 internet router, kernel JUNOS 19.4R1.10, Build date: 2019-12-19", "juniper", "junos"),
        ("Arista EOS", "Arista Networks EOS version 4.30.5M running on an Arista Networks vEOS-lab", "arista", "eos"),
        ("Aruba AOS-CX 6300M", "Aruba JL659A 6300M 48SR CL6 PoE 4SFP56 Swch FL.10.09.1020", "hpe-aruba", "aos-cx"),
        ("Aruba AOS-CX 8325", "Aruba JL627A 8325-48Y8C Swch GL.10.09.1020", "hpe-aruba", "aos-cx"),
        ("ArubaOS-Switch 3810M", "Aruba JL071A 3810M-48G-1QSFP+ Switch, revision KB.16.10.0009, ROM KB.16.01.0006", "hpe-aruba", "arubaos-switch"),
    ):
        r = c.post("/api/vendors/identify", json={"sysDescr": sys_descr})
        body = r.json() if r.status_code == 200 else {}
        check(f"identify {label}", (body.get("vendor"), body.get("os")) == (vendor, os_id), f"{r.status_code} -> {body.get('vendor')}/{body.get('os')}")

    # syslog: real formats from the knowledge base, and the one format two vendors share
    hdr = {"x-rootiq-token": settings.ingest_token}
    fortios = kb.vendor("fortinet")["syslog"][0]["example"]
    junos = next(p["example"] for p in kb.vendor("juniper")["syslog"] if p.get("example"))
    shared = "Sep 29 12:00:02 sw1 Cli: %SYS-5-CONFIG_I: Configured from console by admin"

    def post(lines, device=None):
        r = c.post("/api/syslog", json={"lines": lines, **({"device": device} if device else {})}, headers=hdr)
        return r, (r.json()["results"] if r.status_code == 202 else [])

    r, res = post([fortios], "fw1")
    check("FortiOS syslog line is normalized for fw1", r.status_code == 202 and res and res[0]["parsed"] and res[0]["vendor"] == "fortinet", str(res[0].get("pattern") if res else r.text[:80]))
    r, res = post([junos], "swjun")
    check("Junos syslog line is normalized for swjun", r.status_code == 202 and res and res[0]["parsed"] and res[0]["vendor"] == "juniper")
    r, res = post([shared])
    check("shared Cisco/Arista format without a device: Cisco is chosen and Arista is listed in alsoMatches",
          res and res[0]["vendor"] == "cisco" and "arista" in res[0].get("alsoMatches", []), str(res[0].get("alsoMatches") if res else ""))
    r, res = post([shared], "swarista")
    check("the same line sent for the Arista switch is attributed to Arista", res and res[0]["vendor"] == "arista", str(res[0].get("vendor") if res else ""))
    r, res = post(["this is not a syslog format anyone knows"])
    check("an unknown line is counted as unparsed, never guessed", res and res[0]["parsed"] is False)

    q = c.post("/api/copilot/ask", json={"question": "How do I save the configuration on Juniper, Fortinet and Aruba?", "lang": "en"})
    txt = (q.json().get("answer", "") if q.status_code == 200 else "").lower()
    check("Copilot answers the save-config question for three vendors", all(k in txt for k in ("commit", "fortios", "write memory")) or all(k in txt for k in ("commit", "fortinet", "aruba")), txt[:100].replace("\n", " "))
    qa = c.post("/api/copilot/ask", json={"question": "كيف أحفظ الإعدادات في جونيبر وفورتينت؟", "lang": "ar"})
    ta = qa.json().get("answer", "") if qa.status_code == 200 else ""
    check("Copilot answers the same question in Arabic", re.search(r"[؀-ۿ]", ta) is not None and "commit" in ta.lower())
    check("RAG knowledge index is up", c.get("/api/knowledge/stats").status_code == 200)

# ------------------------------------------------------------------ 2) numbers stated in the docs vs the code
proc = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], capture_output=True, text=True, cwd=ROOT / "backend")
m = re.search(r"(\d+) tests? collected", proc.stdout)
n_tests = int(m.group(1)) if m else -1
claims = {
    "README.md": [r"(\d+) backend tests", r"الاختبارات:\*\* (\d+)", r"# (\d+) tests"],
    ".github/copilot-instructions.md": [r"(\d+) tests must pass"],
    "training/VSCODE_AGENT_PROMPT.md": [r"expected: (\d+) passed"],
    "docs/GITHUB_AGENTS_PROMPT.md": [r"(\d+) tests\)"],
}
for f, pats in claims.items():
    text = read(f)
    said = [int(x) for p in pats for x in re.findall(p, text)]
    check(f"{f}: test count says {n_tests}", bool(said) and all(x == n_tests for x in said), f"states {said}; update it if tests were added or removed")
readme = read("README.md")
said_agents = [int(a or b) for a, b in re.findall(r"Agents: (\d+)|(\d+) agents", readme.replace("**", ""))]
check("README agent count matches the roster", bool(said_agents) and all(x == n_agents for x in said_agents), f"README {sorted(set(said_agents))}, roster {n_agents}")
said_vendors = [int(x) for x in re.findall(r"(\d+) vendors(?= in the knowledge base| ·)", readme)]   # not "up to 4 vendors side by side"
check("README vendor count matches the knowledge base", bool(said_vendors) and all(x == stats["vendors"] for x in said_vendors), f"README {sorted(set(said_vendors))}, KB {stats['vendors']}")

# ------------------------------------------------------------------ 3) every relative link in the markdown files resolves
bad = []
for md in [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "training").rglob("*.md"), *(ROOT / ".github").rglob("*.md")]:
    for link in re.finditer(r"\]\((?!https?:|mailto:|#)([^)\s]+)\)", md.read_text(encoding="utf-8")):
        target = link.group(1).split("#")[0]
        if target and not (md.parent / target).exists():
            bad.append(f"{md.relative_to(ROOT)} -> {target}")
check("all relative markdown links resolve", not bad, "; ".join(bad[:6]))

# ------------------------------------------------------------------ 4) training notebook and GitHub automation
nb = json.loads(read("training/RootIQ_Training.ipynb"))
cells = ["".join(x["source"]) for x in nb["cells"]]
c3 = next(s for s in cells if s.startswith("#@title 3)"))
c2 = next(s for s in cells if s.startswith("#@title C2)"))
check("notebook clones the user's fork (branch main), never the original repository", 'Muath477/frast1.git", "main"' in c3 and "iksasa15/frast1" not in "".join(cells))
check("notebook has 29 cells (with Stage F) and is committed without outputs", len(cells) == 29 and all(not x.get("outputs") for x in nb["cells"] if x["cell_type"] == "code"))
check("notebook C2 uses warmup_steps (newer transformers removed warmup_ratio)", "warmup_steps=WARMUP" in c2 and "warmup_ratio=" not in c2)
manifest = json.loads(read("training/data/generated/manifest.json"))
check("training data manifest carries the knowledge-base fingerprint", bool(manifest.get("kb_fingerprint")))

try:
    import yaml
except ImportError:  # pyyaml comes with uvicorn[standard]; do not fail the audit if it is missing
    yaml = None
    print("SKIP yaml checks (PyYAML not installed)")
if yaml:
    for wf in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        data = yaml.safe_load(wf.read_text(encoding="utf-8"))
        check(f"workflow parses: {wf.name}", isinstance(data, dict) and "jobs" in data, ",".join(data["jobs"]))
    check("copilot-setup-steps job is named copilot-setup-steps", "copilot-setup-steps" in yaml.safe_load(read(".github/workflows/copilot-setup-steps.yml"))["jobs"])
    for agent in sorted((ROOT / ".github" / "agents").glob("*.agent.md")):
        meta = yaml.safe_load(agent.read_text(encoding="utf-8").split("---")[1])
        check(f"custom agent has a description: {agent.name}", bool(meta.get("description")))

# ------------------------------------------------------------------ 5) the frontend receives the vendor data (through the incident plan, not /api/vendors)
fe = ROOT / "frontend" / "src"
src = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in fe.rglob("*.ts*"))
check("frontend types carry vendorContext and configModel; the plan view renders vendor commands",
      all(k in src for k in ("vendorContext", "configModel", "plan.vendorCommands")) and (fe / "components" / "incidents" / "VendorCommands.tsx").exists())

failed = [r for r in results if not r[0]]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
