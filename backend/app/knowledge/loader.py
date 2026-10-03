"""Vendor knowledge base: load, validate, identify devices, parse syslog, look up checks and problems.

The data lives in ``data/vendors/*.json``, ``data/problems.json`` and ``data/capabilities.json`` and is
the single source of truth for the Vendor agent, the Logs agent, the RAG index and the training-data builder.
Coverage and confidence are stated per vendor: nothing here claims to be exhaustive.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
COVERAGE = ("full", "partial", "profile-only")
CONFIDENCE = ("high", "medium", "low")
CHANGE_CAPABILITIES = {"clear_counters", "bounce_interface"}
CONFIG_STYLES = ("running-startup", "candidate-commit", "auto-save")
ROOTIQ_KINDS = {None, "link", "svc-dns", "server"}
SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}

# Commands in a "read" list may only inspect; these verbs mean a change and must never appear there.
DENY_IN_READ = re.compile(
    r"(?i)(^|[\s;|&])(shutdown|no shutdown|reload|reboot|write|commit|delete|set|clear|reset|erase|copy|format|configure|undo|"
    r"disable|enable|kill|pkill|rm|mv|restart|start|stop)\b"
)
# ...and every read command must start with one of these inspection verbs / tools.
READ_PREFIX = re.compile(
    r"^(show|display|get|diagnose|execute log display|uname|cat|ip|ethtool|journalctl|systemctl status|dig|top|free|timedatectl|"
    r"bridge|nv show|lldpctl|vtysh -c 'show|/[\w\- /]+ (print|once)|/tool profile|/interface (print|ethernet monitor)|/system (resource|health|routerboard|ntp)|/snmp print)\b"
)


SAFE_INTERFACE = re.compile(r"^[A-Za-z0-9/:._\-]{1,40}$")


_AR_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ـ": ""})
_AR_MARKS = re.compile(r"[ً-ْ]")


def _norm(text: str) -> str:
    """Lower-case and fold Arabic spelling variants (alef forms, ya/alef-maqsura, diacritics) so أروبا == اروبا."""
    return _AR_MARKS.sub("", (text or "").lower().translate(_AR_MAP))


def _vendor_alias_re(alias: str) -> re.Pattern:
    alias = _norm(alias)
    tail = "" if alias.endswith("-") else r"(?![a-z0-9])"
    return re.compile(r"(?<![a-z0-9])" + re.escape(alias) + tail)


class KnowledgeBase:
    def __init__(self, data_dir: Path | None = None):
        self.dir = Path(data_dir or DATA_DIR)
        self.vendors: dict[str, dict] = {}
        for p in sorted((self.dir / "vendors").glob("*.json")):
            v = json.loads(p.read_text(encoding="utf-8"))
            self.vendors[v["id"]] = v
        self.problems: dict[str, dict] = {
            p["id"]: p for p in json.loads((self.dir / "problems.json").read_text(encoding="utf-8"))["problems"]
        }
        self.capabilities: dict[str, str] = json.loads((self.dir / "capabilities.json").read_text(encoding="utf-8"))
        self._pen_to_vendor: dict[int, str] = {}
        for vid, v in self.vendors.items():
            for e in v.get("enterprise_oids", []):
                self._pen_to_vendor.setdefault(int(e["pen"]), vid)
        self._alias_res: list[tuple[re.Pattern, str, int]] = sorted(
            ((_vendor_alias_re(a), vid, len(a)) for vid, v in self.vendors.items() for a in v.get("aliases", [])),
            key=lambda t: -t[2],
        )
        self._os_res: dict[str, list[tuple[re.Pattern, str, int]]] = {
            vid: sorted(
                ((_vendor_alias_re(a), o["id"], len(a)) for o in v.get("os_families", []) for a in o.get("aliases", [])),
                key=lambda t: -t[2],
            )
            for vid, v in self.vendors.items()
        }

    # ------------------------------------------------------------------ lookups
    def vendor(self, vendor_id: str | None) -> dict | None:
        return self.vendors.get(vendor_id or "")

    def os_family(self, vendor_id: str, os_id: str | None) -> dict | None:
        v = self.vendor(vendor_id)
        return next((o for o in (v or {}).get("os_families", []) if o["id"] == os_id), None)

    def find_vendor(self, text: str) -> tuple[str | None, int]:
        """Vendor named in free text (alias match, longest alias wins). Returns (vendor_id, alias_length)."""
        t = _norm(text)
        for rx, vid, n in self._alias_res:
            if rx.search(t):
                return vid, n
        return None, 0

    def find_vendors(self, text: str, limit: int = 4) -> list[str]:
        """Every distinct vendor named in the text (longest aliases first), for questions that compare vendors."""
        t = _norm(text)
        first: dict[str, int] = {}
        for rx, vid, _ in self._alias_res:
            m = rx.search(t)
            if m and (vid not in first or m.start() < first[vid]):
                first[vid] = m.start()
        return sorted(first, key=first.get)[:limit]  # in the order the user mentioned them

    def config_model(self, vendor_id: str, os_id: str | None) -> dict | None:
        """How a change is applied, saved and rolled back on this OS (reference text, never executed by RootIQ)."""
        o = self.os_family(vendor_id, os_id) if os_id else None
        return (o or {}).get("config_model")

    def cli_style(self, vendor_id: str, os_id: str | None) -> tuple[str, str] | None:
        o = self.os_family(vendor_id, os_id) if os_id else None
        return (o["cli_style"], o.get("cli_style_ar", o["cli_style"])) if o and o.get("cli_style") else None

    CONFIG_PARTS = ("summary", "enter", "save", "snapshot", "safe_change", "rollback")

    def describe_config(self, vendor_id: str, os_id: str | None, ar: bool = False, parts=None, with_style: bool = False) -> str:
        """Plain-text description of how a change is applied / saved / rolled back on one OS (used by the Copilot and the training data)."""
        v, o = self.vendor(vendor_id), self.os_family(vendor_id, os_id)
        head = f"{v['name']} ({o['name'] if o else os_id})"
        cm = self.config_model(vendor_id, os_id)
        if not cm:
            return (f"{head}: لا توجد أوامر مُعدّة أو ملاحظات إعداد بعد؛ راجع وثائق المصنّع." if ar
                    else f"{head}: no curated command or configuration notes yet; check the vendor documentation.")
        want = set(parts or self.CONFIG_PARTS)
        cmds = lambda key: " ; ".join(f"`{c}`" for c in cm[key])
        out = []
        if "summary" in want:
            out.append(cm["summary_ar" if ar else "summary"])
        if "enter" in want and cm["enter"]:
            out.append(("الدخول إلى وضع الإعداد: " if ar else "Enter configuration mode: ") + cmds("enter") + ".")
        if "save" in want:
            if cm["save"]:
                out.append(("للحفظ أو التفعيل: " if ar else "To save / activate: ") + cmds("save") + ".")
            elif cm["style"] == "auto-save":
                out.append("لا توجد خطوة حفظ منفصلة." if ar else "There is no separate save step.")
        if "snapshot" in want and cm["snapshot"]:
            out.append(("نقطة استرجاع قبل التغيير: " if ar else "Restore point before a change: ") + cmds("snapshot") + ".")
        if "safe_change" in want and cm["safe_change"]:
            out.append(("تغيير أكثر أمانًا: " if ar else "Safer change: ") + cmds("safe_change") + ".")
        if "rollback" in want and cm["rollback"]:
            out.append(("للتراجع: " if ar else "To roll back: ") + cmds("rollback") + ".")
        style = self.cli_style(vendor_id, os_id) if with_style else None
        if style:
            out.append(("أسلوب الأوامر: " if ar else "CLI style: ") + style[1 if ar else 0])
        return f"{head}: " + " ".join(out)

    def find_os(self, vendor_id: str, text: str) -> str | None:
        t = _norm(text)
        for rx, oid, _ in self._os_res.get(vendor_id, []):
            if rx.search(t):
                return oid
        return None

    # ------------------------------------------------------------------ identification
    def identify(self, sys_descr: str | None = None, sys_object_id: str | None = None, hint: str | None = None) -> dict:
        """Best-effort vendor / OS / version / model from SNMP sysObjectID, sysDescr and/or a free-text hint."""
        signals: list[str] = []
        vendor_id = os_id = None
        groups: dict[str, str] = {}

        if sys_object_id:
            m = re.match(r"^\.?1\.3\.6\.1\.4\.1\.(\d+)", sys_object_id.strip())
            if m and int(m.group(1)) in self._pen_to_vendor:
                vendor_id = self._pen_to_vendor[int(m.group(1))]
                signals.append(f"sysObjectID enterprise {m.group(1)}")

        if sys_descr:
            order = ([vendor_id] if vendor_id else []) + [v for v in self.vendors if v != vendor_id]
            for vid in order:
                for o in self.vendors[vid].get("os_families", []):
                    for rx in o.get("sysdescr_regex", []):
                        m = re.search(rx, sys_descr, re.S | re.I)
                        if m:
                            vendor_id, os_id = vid, o["id"]
                            groups = {k: v for k, v in m.groupdict().items() if v}
                            signals.append(f"sysDescr matched {vid}/{os_id}")
                            break
                    if os_id:
                        break
                if os_id:
                    break
            if not vendor_id:
                vid, _ = self.find_vendor(sys_descr)
                if vid:
                    vendor_id = vid
                    signals.append("vendor name found in sysDescr")

        if hint:
            hv, _ = self.find_vendor(hint)
            if vendor_id is None and hv:
                vendor_id = hv
                signals.append("vendor name found in hint")
            if vendor_id and os_id is None:
                ho = self.find_os(vendor_id, hint)
                if ho:
                    os_id = ho
                    signals.append(f"OS '{ho}' inferred from hint")

        if vendor_id and os_id is None and sys_descr:
            ho = self.find_os(vendor_id, sys_descr)
            if ho:
                os_id = ho
                signals.append(f"OS '{ho}' inferred from sysDescr text")

        v = self.vendor(vendor_id)
        o = self.os_family(vendor_id, os_id) if vendor_id else None
        version_raw = groups.get("version")
        if version_raw is None and o and o.get("version_regex") and sys_descr:
            m = re.search(o["version_regex"], sys_descr, re.S | re.I)
            if m and m.groupdict().get("version"):
                version_raw = m.group("version")
        strong_descr = any(s.startswith("sysDescr matched") for s in signals)
        strong_oid = any(s.startswith("sysObjectID") for s in signals)
        confidence = "none"
        if vendor_id:
            confidence = "high" if (strong_oid and strong_descr) or (strong_descr and v.get("confidence") == "high") else "medium" if (strong_oid or strong_descr) else "low"
        return {
            "vendor": vendor_id,
            "vendorName": (v or {}).get("name"),
            "os": os_id,
            "osName": (o or {}).get("name"),
            "version": self.normalize_version(os_id, version_raw) if version_raw else None,
            "versionRaw": version_raw,
            "versionScheme": (o or {}).get("version_scheme"),
            "model": groups.get("model") or groups.get("platform") or groups.get("family"),
            "sku": groups.get("sku"),
            "codename": groups.get("codename"),
            "netmiko": (o or {}).get("netmiko"),
            "coverage": (v or {}).get("coverage"),
            "confidence": confidence,
            "signals": signals,
        }

    @staticmethod
    def normalize_version(os_id: str | None, version: str | None) -> str | None:
        if not version:
            return None
        if os_id == "ios-xe":  # 'show version' zero-pads (17.09.04a) while sysDescr does not (17.9.4a)
            return re.sub(r"(?<![\d])0+(?=\d)", "", version)
        return version

    @staticmethod
    def version_tuple(version: str | None) -> tuple[int, ...]:
        """Numeric parts for ordering releases of the SAME OS family (e.g. 4.30.5M < 4.32.1F). Not comparable across vendors."""
        return tuple(int(x) for x in re.findall(r"\d+", version or ""))

    # ------------------------------------------------------------------ commands & checks
    def commands(self, vendor_id: str, os_id: str | None, capability: str, interface: str | None = None) -> dict | None:
        v = self.vendor(vendor_id)
        if not v:
            return None
        table = v.get("commands", {})
        entry = (table.get(os_id or "", {}) or {}).get(capability)
        # The 'default' table is only verified for the OS families listed in default_for: another OS of the same
        # vendor (e.g. IOS-XR next to IOS-XE) gets "no curated command" instead of another OS's syntax.
        if not entry and (os_id is None or not v.get("default_for") or os_id in v["default_for"]):
            entry = (table.get("default", {}) or {}).get(capability)
        if not entry:
            return None
        if interface is not None and not SAFE_INTERFACE.match(interface):
            raise ValueError(f"unsafe interface name: {interface!r}")
        sub = lambda cmd: cmd.replace("<if>", interface) if interface else cmd
        return {kind: [sub(c) for c in cmds] for kind, cmds in entry.items()}

    @staticmethod
    def is_read_only(command: str) -> bool:
        """True only for an inspection command: starts with a known read verb and contains no change verb."""
        c = (command or "").strip()
        return bool(c) and bool(READ_PREFIX.search(c)) and not DENY_IN_READ.search(c)

    def vendor_summary(self, vendor_id: str) -> dict | None:
        v = self.vendor(vendor_id)
        if not v:
            return None
        return {
            "id": v["id"], "name": v["name"], "categories": v["categories"], "coverage": v["coverage"],
            "confidence": v["confidence"], "osFamilies": [o["id"] for o in v["os_families"]],
            "series": len(v["series"]), "pens": [e["pen"] for e in v["enterprise_oids"]],
            "hasCommands": bool(v.get("commands")), "hasSyslog": bool(v.get("syslog")),
        }

    def checks_for(self, problem_id: str, vendor_id: str, os_id: str | None = None, interface: str | None = None) -> list[dict]:
        p = self.problems.get(problem_id)
        if not p:
            return []
        out = []
        for chk in p["checks"]:
            entry = self.commands(vendor_id, os_id, chk["capability"], interface)
            out.append({
                "capability": chk["capability"], "why": chk["why"],
                "commands": (entry or {}).get("read", []), "available": bool(entry and entry.get("read")),
            })
        return out

    def fix_commands(self, problem_id: str, vendor_id: str, os_id: str | None = None, interface: str | None = None) -> list[dict]:
        p = self.problems.get(problem_id)
        if not p:
            return []
        out = []
        for f in p["fixes"]:
            cmds = []
            for cap in f.get("change_capabilities", []):
                entry = self.commands(vendor_id, os_id, cap, interface)
                if entry and entry.get("change"):
                    cmds.append({"capability": cap, "commands": entry["change"]})
            out.append({"id": f["id"], "title": f["title"], "risk": f["risk"], "rollback": f["rollback"],
                        "needsApproval": True, "commands": cmds})
        return out

    # ------------------------------------------------------------------ problems
    def find_problem(self, text: str) -> str | None:
        t = (text or "").lower()
        best, best_score = None, 0
        for pid, p in self.problems.items():
            score = sum(len(k) for k in p["keywords"] if k.lower() in t)
            if score > best_score:
                best, best_score = pid, score
        return best

    def problems_for(self, metrics=(), events=(), kind: str | None = None, limit: int = 3) -> list[dict]:
        metrics, events = set(metrics), set(events)
        scored = []
        for pid, p in self.problems.items():
            if kind and p.get("applies_to") and kind not in p["applies_to"]:
                continue
            score = 3 * len(events & set(p["signals"]["events"])) + 2 * len(metrics & set(p["signals"]["metrics"]))
            if score and kind and p.get("rootiq_kind") == kind:  # the kind only breaks ties between signal matches
                score += 5
            if score:
                scored.append((score, SEVERITY_ORDER.get(p["severity"], 0), pid))
        scored.sort(key=lambda t: (-t[0], -t[1], t[2]))
        return [self.problems[pid] for _, _, pid in scored[:limit]]

    # ------------------------------------------------------------------ syslog
    def parse_syslog(self, line: str, vendor_hint: str | None = None) -> dict | None:
        """Normalize one syslog line to {event, vendor, interface, state, ...} or None if no pattern matches.

        Some formats are shared by several vendors (e.g. %LINEPROTO-5-UPDOWN on Cisco and Arista). The hint wins;
        otherwise the most common vendor is preferred and the others are listed in `alsoMatches`.
        """
        hits = []
        for vid in self._syslog_order(vendor_hint):
            for pat in self.vendors[vid].get("syslog", []):
                m = re.search(pat["regex"], line, re.I)
                if m:
                    hits.append((vid, pat, m))
                    break
        if not hits:
            return None
        vid, pat, m = hits[0]
        g = {k: v for k, v in m.groupdict().items() if v}
        state = (pat.get("state") or g.get("state") or "").lower() or None
        state = (pat.get("state_map") or {}).get(state, state)  # e.g. Aruba "off-line" -> "down"
        return {
            "event": pat["event"], "vendor": vid, "pattern": pat["id"], "severity": pat.get("severity", "info"),
            "interface": g.get("interface"), "state": state,
            "details": {k: v for k, v in g.items() if k not in ("interface", "state")},
            "alsoMatches": [h[0] for h in hits[1:]],
        }

    SYSLOG_PRIORITY = ("cisco", "juniper", "arista", "huawei", "hpe-aruba", "mikrotik", "extreme", "linux")

    def _syslog_order(self, hint: str | None) -> list[str]:
        head = [hint] if hint in self.vendors else []
        pri = [v for v in self.SYSLOG_PRIORITY if v in self.vendors and v not in head]
        return head + pri + [v for v in self.vendors if v not in head and v not in pri]

    # ------------------------------------------------------------------ stats & validation
    def stats(self) -> dict:
        cov = {c: 0 for c in COVERAGE}
        series = os_n = cmds = pats = 0
        for v in self.vendors.values():
            cov[v["coverage"]] += 1
            series += len(v.get("series", []))
            os_n += len(v.get("os_families", []))
            cmds += sum(len(t) for t in v.get("commands", {}).values())
            pats += len(v.get("syslog", []))
        return {"vendors": len(self.vendors), "coverage": cov, "osFamilies": os_n, "seriesFamilies": series,
                "commandEntries": cmds, "syslogPatterns": pats, "problems": len(self.problems), "capabilities": len(self.capabilities)}

    def validate(self) -> list[str]:
        from app.intelligence.thresholds import THRESHOLDS

        errs: list[str] = []
        seen_pens: dict[int, str] = {}
        for vid, v in self.vendors.items():
            for key in ("id", "name", "aliases", "categories", "enterprise_oids", "coverage", "confidence", "os_families", "series", "commands", "syslog"):
                if key not in v:
                    errs.append(f"{vid}: missing '{key}'")
            if v.get("coverage") not in COVERAGE:
                errs.append(f"{vid}: bad coverage {v.get('coverage')}")
            if v.get("confidence") not in CONFIDENCE:
                errs.append(f"{vid}: bad confidence {v.get('confidence')}")
            for e in v.get("enterprise_oids", []):
                if e["pen"] in seen_pens and seen_pens[e["pen"]] != vid:
                    errs.append(f"{vid}: PEN {e['pen']} also used by {seen_pens[e['pen']]}")
                seen_pens[e["pen"]] = vid
            os_ids = [o["id"] for o in v.get("os_families", [])]
            if len(os_ids) != len(set(os_ids)):
                errs.append(f"{vid}: duplicate OS ids")
            for o_id in v.get("default_for", []):
                if o_id not in os_ids:
                    errs.append(f"{vid}: default_for references unknown OS '{o_id}'")
                elif v.get("coverage") == "full" and not self.config_model(vid, o_id):
                    errs.append(f"{vid}/{o_id}: full-coverage vendors need a config_model for every default OS")
            for o in v.get("os_families", []):
                cm = o.get("config_model")
                if cm is not None:
                    for key in ("style", "summary", "summary_ar", "enter", "save", "snapshot", "safe_change", "rollback"):
                        if key not in cm:
                            errs.append(f"{vid}/{o['id']}: config_model missing '{key}'")
                    if cm.get("style") not in CONFIG_STYLES:
                        errs.append(f"{vid}/{o['id']}: bad config_model style {cm.get('style')!r}")
                    for key in ("enter", "save", "snapshot", "safe_change", "rollback"):
                        if not all(isinstance(c, str) and c.strip() for c in cm.get(key, [])):
                            errs.append(f"{vid}/{o['id']}: config_model.{key} must be a list of non-empty strings")
                    if cm.get("style") == "running-startup" and not cm.get("save"):
                        errs.append(f"{vid}/{o['id']}: a running-startup OS needs a save command")
                if o.get("cli_style") and not o.get("cli_style_ar"):
                    errs.append(f"{vid}/{o['id']}: cli_style needs an Arabic cli_style_ar")
            if v.get("commands", {}).get("default") and not v.get("default_for"):
                errs.append(f"{vid}: has a default command table but no default_for")
            for o in v.get("os_families", []):
                for rx in o.get("sysdescr_regex", []) + ([o["version_regex"]] if o.get("version_regex") else []):
                    try:
                        re.compile(rx)
                    except re.error as e:
                        errs.append(f"{vid}/{o['id']}: bad regex {rx!r}: {e}")
                for ex in o.get("examples", {}).get("sysdescr", []):
                    if not any(re.search(rx, ex, re.S | re.I) for rx in o.get("sysdescr_regex", [])):
                        errs.append(f"{vid}/{o['id']}: sysdescr example does not match its regex")
            for s in v.get("series", []):
                if s.get("os") is not None and s["os"] not in os_ids:
                    errs.append(f"{vid}: series '{s['name']}' references unknown OS '{s['os']}'")
            for table_os, table in v.get("commands", {}).items():
                if table_os != "default" and table_os not in os_ids:
                    errs.append(f"{vid}: commands for unknown OS '{table_os}'")
                for cap, entry in table.items():
                    if cap not in self.capabilities:
                        errs.append(f"{vid}: unknown capability '{cap}'")
                    for c in entry.get("read", []):
                        if DENY_IN_READ.search(c) or not READ_PREFIX.search(c):
                            errs.append(f"{vid}/{cap}: read command not read-only or unknown verb: {c!r}")
                    if entry.get("change") and cap not in CHANGE_CAPABILITIES:
                        errs.append(f"{vid}/{cap}: change commands are only allowed for {sorted(CHANGE_CAPABILITIES)}")
                    if cap in CHANGE_CAPABILITIES and entry.get("read"):
                        errs.append(f"{vid}/{cap}: change capability must not have read commands")
            for pat in v.get("syslog", []):
                try:
                    rx = re.compile(pat["regex"], re.I)
                except re.error as e:
                    errs.append(f"{vid}/{pat['id']}: bad syslog regex: {e}")
                    continue
                if not rx.search(pat["example"]):
                    errs.append(f"{vid}/{pat['id']}: syslog example does not match")
        for pid, p in self.problems.items():
            for k in ("title", "title_ar", "summary", "summary_ar", "keywords", "checks", "fixes", "causes"):
                if not p.get(k):
                    errs.append(f"problem {pid}: empty '{k}'")
            if p.get("rootiq_kind") not in ROOTIQ_KINDS:
                errs.append(f"problem {pid}: bad rootiq_kind")
            if not set(p.get("applies_to", [])) <= (ROOTIQ_KINDS - {None}):
                errs.append(f"problem {pid}: bad applies_to {p.get('applies_to')}")
            for chk in p["checks"]:
                if chk["capability"] not in self.capabilities:
                    errs.append(f"problem {pid}: unknown capability {chk['capability']}")
            for f in p["fixes"]:
                bad = set(f.get("change_capabilities", [])) - CHANGE_CAPABILITIES
                if bad:
                    errs.append(f"problem {pid}: fix {f['id']} uses non-change capabilities {sorted(bad)}")
                if not f.get("needs_approval"):
                    errs.append(f"problem {pid}: fix {f['id']} must require approval")
            for vf in p["verify"]:
                if vf["metric"] not in THRESHOLDS:
                    errs.append(f"problem {pid}: verify metric {vf['metric']} is not a RootIQ metric")
            for m in p["signals"]["metrics"]:
                if m not in THRESHOLDS:
                    errs.append(f"problem {pid}: signal metric {m} is not a RootIQ metric")
        return errs


@lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    return KnowledgeBase()
