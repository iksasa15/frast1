"""Real device output for many vendors, from Network to Code's ntc-templates (Apache-2.0), as extra training rows.

Why this source: the generated knowledge-base data knows every vendor's commands, but it has no *captured* device output.
ntc-templates ships, for 50+ platforms, a raw `show ...` / `display ...` / `get ...` output next to the fields its parser extracts
from it, so the model can learn what a FortiGate, a Junos box, an Aruba switch or a VRP router really prints, in the vendor's own
field names. It is a GitHub repository, not a Hugging Face dataset, so it is loaded here and gated the same way `external.py` is:

  * the licence file must be Apache-2.0 (otherwise nothing is loaded),
  * only platforms that map to a vendor / OS of the RootIQ knowledge base,
  * only read-only commands, no secrets, capped in size and in rows per platform and per command,
  * train-only rows: the vendor-knowledge test files never change, so scores stay comparable between runs.

    rows = load_ntc(Path("/content/ntc-templates"), per_platform=120)      # clones the repository (shallow) when it is not there yet
"""
from __future__ import annotations

import json
import random
import re
import subprocess
from pathlib import Path

import external

REPO_URL = "https://github.com/networktocode/ntc-templates.git"
TASK = "ext_cli_parse"
MAX_RAW, MAX_ANSWER = 1400, 1000     # characters: user + answer stay well inside the 1024-token training length

# ntc-templates platform folder -> (RootIQ vendor id, OS id, display name). Platforms that do not map are not used.
PLATFORMS = {
    "cisco_ios": ("cisco", "ios", "Cisco IOS"),
    "cisco_nxos": ("cisco", "nx-os", "Cisco NX-OS"),
    "cisco_xr": ("cisco", "ios-xr", "Cisco IOS-XR"),
    "juniper_junos": ("juniper", "junos", "Juniper Junos"),
    "arista_eos": ("arista", "eos", "Arista EOS"),
    "aruba_aoscx": ("hpe-aruba", "aos-cx", "HPE Aruba AOS-CX"),
    "hp_procurve": ("hpe-aruba", "arubaos-switch", "HP ProCurve / ArubaOS-Switch"),
    "huawei_vrp": ("huawei", "vrp", "Huawei VRP"),
    "fortinet": ("fortinet", "fortios", "Fortinet FortiOS"),
    "mikrotik_routeros": ("mikrotik", "routeros", "MikroTik RouterOS"),
    "extreme_exos": ("extreme", "exos", "Extreme EXOS"),
    "paloalto_panos": ("paloalto", "pan-os", "Palo Alto PAN-OS"),
    "dell_force10": ("dell", "os9", "Dell Force10 / OS9"),
    "dell_powerconnect": ("dell", "dnos6", "Dell PowerConnect / DNOS6"),
}
READ_FIRST = {"show", "sh", "display", "get", "diagnose", "dir"}
DENY = re.compile(r"(?i)(^|[\s;|&])(shutdown|reload|reboot|write|commit|delete|set|clear|reset|erase|copy|format|configure|undo|disable|enable|kill|restart|start|stop|debug)\b")
EXTRA_SECRET = re.compile(r"(?i)(snmp-server community|community string|key-string|private-key|BEGIN [A-Z ]*PRIVATE KEY|secret \d|password \S+|enable password)")


def command_from_folder(name: str) -> str:
    """ntc-templates names a test folder after its command with underscores: show_ip_route -> show ip route."""
    return name.replace("_", " ").strip()


def is_read_only(command: str) -> bool:
    words = command.split()
    if not words or DENY.search(command):
        return False
    return words[0].lower() in READ_FIRST or words[-1].lower() == "print"     # RouterOS: "ip route print"


def licence_ok(repo: Path) -> bool:
    """Only Apache-2.0 is accepted; the notebook must never train on a repository whose licence changed."""
    lic = repo / "LICENSE"
    if not lic.exists():
        return False
    text = lic.read_text(encoding="utf-8", errors="ignore")
    return "Apache License, Version 2.0" in text or ("Apache License" in text and "Version 2.0" in text)


def clone(dest: Path) -> str:
    """Shallow clone of the public repository; returns the commit hash used (print it next to the training data)."""
    if not dest.exists():
        subprocess.run(["git", "clone", "--depth", "1", REPO_URL, str(dest)], check=True)
    return subprocess.run(["git", "-C", str(dest), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip() or "unknown"


def _load_yaml(path: Path):
    import yaml    # PyYAML: present in Colab and in the backend requirements (uvicorn[standard])

    return yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore"))


def _sample(platform: str, command: str, raw_path: Path) -> dict | None:
    yml = raw_path.with_suffix(".yml")
    if not yml.exists():
        return None
    raw = raw_path.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n").strip("\n")
    try:
        parsed = (_load_yaml(yml) or {}).get("parsed_sample")
    except Exception:  # noqa: BLE001  (a malformed community test file is skipped, never fatal)
        return None
    if not raw or not parsed or not isinstance(parsed, list):
        return None
    answer = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    for text in (raw, answer):
        if len(text) > (MAX_RAW if text is raw else MAX_ANSWER) or EXTRA_SECRET.search(text) or external.SECRET.search(text):
            return None
    vendor, os_id, name = PLATFORMS[platform]
    user = (f"Vendor: {name}. Command: `{command}`.\nDevice output:\n```\n{raw}\n```\n"
            "Parse this output into JSON: a list with one record per item, using the field names the platform's parser produces.")
    row = external._row(TASK, vendor, user, answer, f"ntc-templates/{platform}")
    row["meta"]["gold"] = {"vendor": vendor, "os": os_id, "command": command}
    return row


def convert(repo: Path, per_platform: int = 120, per_command: int = 3, seed: int = 7) -> list[dict]:
    """Pure function over a checkout (no network): licence gate, map, filter, de-duplicate, cap, shuffle deterministically."""
    repo = Path(repo)
    if not licence_ok(repo):
        raise PermissionError(f"{repo} does not carry the Apache-2.0 licence file: ntc-templates data is not used for training")
    rnd = random.Random(seed)
    out: list[dict] = []
    for platform in PLATFORMS:
        base = repo / "tests" / platform
        if not base.is_dir():
            continue
        rows, seen = [], set()
        for folder in sorted(p for p in base.iterdir() if p.is_dir()):
            command = command_from_folder(folder.name)
            if not is_read_only(command):
                continue
            kept = 0
            for raw_path in sorted(folder.glob("*.raw")):
                if kept >= per_command:
                    break
                row = _sample(platform, command, raw_path)
                if row and row["messages"][1]["content"] not in seen:
                    seen.add(row["messages"][1]["content"])
                    rows.append(row)
                    kept += 1
        rnd.shuffle(rows)
        out += rows[:per_platform]
    rnd.shuffle(out)
    return out


def load_ntc(repo_dir: Path, per_platform: int = 120, per_command: int = 3, seed: int = 7) -> list[dict]:
    """Clone (if needed) and convert. Returns train rows tagged `ext_cli_parse`."""
    repo_dir = Path(repo_dir)
    clone(repo_dir)
    return convert(repo_dir, per_platform, per_command, seed)
