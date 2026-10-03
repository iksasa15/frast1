"""Vendor Intelligence Agent: who is this device, and what does *its* CLI say about this problem?

It never talks to a device. It reads the vendor knowledge base (`app/knowledge`) and the topology, and
attaches vendor-specific *reference* diagnostics to an incident. Diagnostic commands are read-only by
construction (validated in the KB and re-checked by the Guardrail); fix commands are shown for the engineer
and are never executed by RootIQ.
"""
from __future__ import annotations

import re

from app.knowledge import get_kb
from app.rag.index import normalize

from .base import Agent
from .playbooks import kind_for_entity
from .roster import SPECS

MAX_PROBLEMS = 2
# question words -> KB capability (checked in order; latin words match on word boundaries, Arabic as substrings)
CAPABILITY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("show_mac_table", ("mac table", "mac address", "mac-address", "جدول mac", "جدول ماك")),
    ("show_optics", ("optic", "transceiver", "sfp", "dom", "light level", "بصري", "ضوء")),
    ("show_interface_errors", ("crc", "error counter", "input error", "fcs", "أخطاء", "اخطاء")),
    ("show_stp", ("spanning", "stp")),
    ("show_trunk", ("trunk",)),
    ("show_vlan", ("vlan",)),
    ("show_neighbors", ("neighbor", "neighbour", "lldp", "cdp")),
    ("show_cpu", ("cpu", "المعالج")),
    ("show_memory", ("memory", "الذاكرة")),
    ("show_environment", ("fan", "power supply", "temperature", "environment")),
    ("show_ospf", ("ospf",)),
    ("show_bgp", ("bgp",)),
    ("show_lag", ("lacp", "port-channel", "port channel", "lag")),
    ("show_poe", ("poe",)),
    ("show_arp", ("arp",)),
    ("show_logging", ("log", "syslog", "السجل")),
    ("show_ntp", ("ntp",)),
    ("show_snmp", ("snmp",)),
    ("show_version", ("version", "الاصدار", "الإصدار")),
    ("show_interface_status", ("interface status", "interface brief", "port status", "interfaces")),
]


def _has_word(text: str, word: str) -> bool:
    if word.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", text) is not None
    return word in text


def find_capability(text: str) -> str | None:
    t = (text or "").lower()
    for cap, words in CAPABILITY_KEYWORDS:
        if any(_has_word(t, w) for w in words):
            return cap
    return None
COVERAGE_NOTE = {
    "full": "Curated commands and syslog patterns for this vendor.",
    "partial": "Some commands / patterns curated; verify against the vendor's own documentation.",
    "profile-only": "Vendor is identified, but no command table is curated yet — use the vendor documentation.",
}


CONFIG_WORDS = [normalize(k) for k in (
    "save config", "save the config", "saving config", "save configuration", "save my config", "write memory", "startup-config", "startup config",
    "nvram", "vram", "commit", "rollback", "roll back", "roll-back", "persist", "config mode", "configuration mode", "enter config",
    "احفظ", "حفظ", "الحفظ", "تراجع", "استرجاع", "وضع الاعداد", "وضع الإعداد",
)]
STYLE_WORDS = [normalize(k) for k in (
    "cli style", "command style", "syntax", "differ", "difference", "different", "compare",
    "صيغه", "صيغة", "اسلوب", "أسلوب", "طريقه كتابه", "طريقة كتابة", "كتابه الاوامر", "كتابة الأوامر", "الفرق", "يختلف", "قارن",
)]


def find_config_topic(text: str) -> bool:
    q = normalize(text or "")
    return any(w in q for w in CONFIG_WORDS)


def wants_style(text: str) -> bool:
    q = normalize(text or "")
    return any(w in q for w in STYLE_WORDS)


def _config_brief(vendor: str | None, os_id: str | None) -> dict | None:
    """How a change is applied / saved / rolled back on this device's OS (reference text for the engineer)."""
    if not vendor:
        return None
    kb = get_kb()
    cm = kb.config_model(vendor, os_id)
    if not cm:
        return None
    style = kb.cli_style(vendor, os_id)
    return {
        "style": cm["style"], "summary": cm["summary"], "summaryAr": cm["summary_ar"], "enter": cm["enter"], "save": cm["save"],
        "snapshot": cm["snapshot"], "safeChange": cm["safe_change"], "rollback": cm["rollback"], "notes": cm.get("notes"),
        "cliStyle": style[0] if style else None, "cliStyleAr": style[1] if style else None,
    }


def _identity_brief(node: dict, ident: dict, *, role: str | None = None, interface: str | None = None) -> dict:
    return {
        "id": node["id"],
        "label": node.get("label", node["id"]),
        "type": node.get("type"),
        "role": role,
        "interface": interface,
        "vendor": ident["vendor"],
        "vendorName": ident["vendorName"],
        "os": ident["os"],
        "osName": ident["osName"],
        "version": ident["version"],
        "model": ident["model"],
        "netmiko": ident["netmiko"],
        "coverage": ident["coverage"],
        "confidence": ident["confidence"],
        "configModel": _config_brief(ident["vendor"], ident["os"]),
    }


class VendorAgent(Agent):
    spec = SPECS["vendor"]

    def __init__(self, runtime):
        super().__init__(runtime)
        self.kb = get_kb()
        self._identities: dict[str, dict] = {}

    # ------------------------------------------------------------------ identification
    def identify(self, sys_descr: str | None = None, sys_object_id: str | None = None, hint: str | None = None) -> dict:
        self.stats.runs += 1
        return self.kb.identify(sys_descr, sys_object_id, hint)

    def node_identity(self, node_id: str) -> dict | None:
        """Identity of a topology node from its optional sysDescr / sysObjectId / vendor hint fields (cached)."""
        if node_id in self._identities:
            return self._identities[node_id]
        topo = self.rt.topology
        node = topo.nodes.get(node_id) if topo is not None else None
        if node is None:
            return None
        ident = self.kb.identify(node.get("sysDescr"), node.get("sysObjectId"), node.get("vendor"))
        if node.get("os") and ident["vendor"] and self.kb.os_family(ident["vendor"], node["os"]):
            ident["os"] = node["os"]
            ident["osName"] = self.kb.os_family(ident["vendor"], node["os"])["name"]
            ident["netmiko"] = self.kb.os_family(ident["vendor"], node["os"]).get("netmiko")
            ident["signals"].append("OS set in topology")
        self._identities[node_id] = ident
        return ident

    def inventory(self) -> list[dict]:
        topo = self.rt.topology
        if topo is None:
            return []
        out = []
        for n in topo.nodes.values():
            ident = self.node_identity(n["id"])
            out.append({**_identity_brief(n, ident), "managementIp": n.get("managementIp"), "hint": n.get("vendor")})
        return out

    def forget(self, node_id: str | None = None):
        (self._identities.pop(node_id, None) if node_id else self._identities.clear())

    # ------------------------------------------------------------------ which devices does an entity involve?
    def devices_for(self, entity_id: str) -> list[dict]:
        """Devices (and the interface on each) that a root-cause entity touches."""
        topo = self.rt.topology
        if topo is None:
            return []
        out: list[dict] = []

        def add(node_id: str, role: str, interface: str | None):
            node = topo.nodes.get(node_id)
            ident = self.node_identity(node_id)
            if node is not None and ident is not None:
                out.append(_identity_brief(node, ident, role=role, interface=interface))

        if entity_id in topo.links:
            l = topo.links[entity_id]
            add(l["source"], "link-end-a", l["sourcePort"])
            add(l["target"], "link-end-b", l["targetPort"])
        elif entity_id in topo.services:
            add(topo.services[entity_id]["host"], "service-host", None)
        elif entity_id in topo.nodes:
            add(entity_id, "device", None)
        return out

    # ------------------------------------------------------------------ problem + command assembly
    def _problem_view(self, problem: dict, devices: list[dict]) -> dict:
        kb = self.kb
        diagnose, fixes = [], []
        for d in devices:
            if not d["vendor"]:
                diagnose.append({"device": d["id"], "vendor": None, "os": None, "interface": d["interface"], "checks": [],
                                 "note": "vendor not identified — set 'vendor' or 'sysDescr' on the topology node"})
                continue
            checks = kb.checks_for(problem["id"], d["vendor"], d["os"], d["interface"])
            diagnose.append({"device": d["id"], "vendor": d["vendor"], "os": d["os"], "interface": d["interface"],
                             "coverage": d["coverage"], "checks": checks,
                             "note": COVERAGE_NOTE.get(d["coverage"], "")})
        for f in problem["fixes"]:
            cmds = []
            for d in devices:
                if not d["vendor"]:
                    continue
                for cap in f.get("change_capabilities", []):
                    entry = kb.commands(d["vendor"], d["os"], cap, d["interface"])
                    if entry and entry.get("change"):
                        cmds.append({"device": d["id"], "capability": cap, "commands": entry["change"]})
            fixes.append({"id": f["id"], "title": f["title"], "risk": f["risk"], "rollback": f["rollback"],
                          "needsApproval": True, "commands": cmds})
        return {
            "id": problem["id"], "title": problem["title"], "titleAr": problem["title_ar"], "severity": problem["severity"],
            "summary": problem["summary"], "summaryAr": problem["summary_ar"], "causes": problem["causes"],
            "verify": problem["verify"], "diagnose": diagnose, "fixes": fixes,
        }

    def build_context(self, root_id: str, metrics: list[str]) -> dict:
        """Pure function: root cause + observed metrics -> vendor context (no trace step, unit-testable)."""
        kind = kind_for_entity(root_id)
        devices = self.devices_for(root_id)
        problems = self.kb.problems_for(metrics=metrics, kind=kind, limit=MAX_PROBLEMS)
        return {
            "rootEntity": root_id,
            "kind": kind,
            "devices": devices,
            "problems": [self._problem_view(p, devices) for p in problems],
            "known": sum(1 for d in devices if d["vendor"]),
        }

    async def enrich(self, inc, root_id: str) -> dict:
        """After RCA: attach vendor identity, matched problems and per-vendor diagnostics to the incident."""
        async with self.step("enrich_incident", inc.id) as st:
            metrics = sorted({a.metric for a in inc.anomalies})
            ctx = self.build_context(root_id, metrics)
            st.data = {
                "devices": [f"{d['id']}:{d['vendor'] or '?'}/{d['os'] or '?'}" for d in ctx["devices"]],
                "problems": [p["id"] for p in ctx["problems"]],
            }
            st.decision = ctx["problems"][0]["id"] if ctx["problems"] else "no_known_problem"
            st.summary = (
                f"{ctx['known']}/{len(ctx['devices'])} device(s) identified, "
                f"{len(ctx['problems'])} known problem pattern(s) matched"
                + (f" — top: {ctx['problems'][0]['title']}" if ctx["problems"] else "")
            )
        return ctx

    # ------------------------------------------------------------------ Copilot support
    def overview(self, ar: bool) -> tuple[str, dict]:
        kb = self.kb
        st = kb.stats()
        full = sorted(v["name"] for v in kb.vendors.values() if v["coverage"] == "full")
        cov = st["coverage"]
        text = (
            f"قاعدة المعرفة تغطي {st['vendors']} مصنّعًا ({cov['full']} تغطية كاملة، {cov['partial']} جزئية، {cov['profile-only']} تعريف فقط)، "
            f"{st['osFamilies']} نظام تشغيل، {st['seriesFamilies']} عائلة أجهزة، و{st['problems']} نمط مشكلة. التغطية الكاملة: {', '.join(full)}. "
            "هذه عائلات وسلاسل وليست كل رقم SKU."
            if ar else
            f"The knowledge base covers {st['vendors']} vendors ({cov['full']} full, {cov['partial']} partial, {cov['profile-only']} identification-only), "
            f"{st['osFamilies']} OS families, {st['seriesFamilies']} device families and {st['problems']} problem patterns. Full coverage: {', '.join(full)}. "
            "These are families and series, not every individual SKU."
        )
        return text, {"vendors": st["vendors"], "coverage": cov, "problems": st["problems"]}

    def _os_for(self, vid: str, question: str, need_config: bool = False) -> str | None:
        kb = self.kb
        os_id = kb.find_os(vid, question)
        if os_id:
            return os_id
        oses = [o["id"] for o in kb.vendor(vid)["os_families"]]
        if need_config:
            return next((o for o in oses if kb.config_model(vid, o)), oses[0] if oses else None)
        return oses[0] if oses else None

    def config_answer(self, vid: str, os_id: str | None, ar: bool, with_style: bool = False) -> str:
        """One vendor's answer to 'how do I save / commit / roll back a change' (reference text; RootIQ never runs it)."""
        return self.kb.describe_config(vid, os_id, ar, with_style=with_style)

    def _capability_sentence(self, vid: str, os_id: str | None, cap: str, ar: bool) -> tuple[str, int]:
        kb = self.kb
        v, desc = kb.vendor(vid), kb.capabilities[cap]
        entry = kb.commands(vid, os_id, cap)
        if entry and entry.get("read"):
            cmds = " ; ".join(entry["read"][:3]).replace("<if>", "<interface>")
            return (f"{desc} على {v['name']} ({os_id}): {cmds}." if ar else f"{desc} on {v['name']} ({os_id}): {cmds}."), len(entry["read"])
        return (
            (f"لا توجد أوامر مُعدّة لـ«{desc}» على {v['name']} بعد (التغطية: {v['coverage']}). راجع وثائق المصنّع." if ar
             else f"No curated command for '{desc}' on {v['name']} yet (coverage: {v['coverage']}). Check the vendor documentation."), 0)

    def answer_help(self, question: str, ar: bool, overview: bool = False) -> tuple[str, dict] | None:
        """Answer 'which command / how do I save / what is the difference' questions from the KB. None if not resolvable.

        Several vendors named in one question are answered side by side (Cisco vs Junos vs FortiGate ...).
        """
        kb = self.kb
        vids = kb.find_vendors(question, limit=4)
        pid = kb.find_problem(question)
        if overview and not vids:
            return self.overview(ar)
        if not vids and pid is None:
            return None
        footer = " هذه أوامر مرجعية للمهندس؛ RootIQ لا ينفّذها." if ar else " These are reference commands for the engineer; RootIQ does not run them."

        if vids and find_config_topic(question):
            texts = [self.config_answer(v, self._os_for(v, question, True), ar, wants_style(question)) for v in vids]
            return " ".join(texts) + footer, {"vendors": vids, "topic": "config_model"}

        cap = find_capability(question) if vids and pid is None else None
        if vids and cap:
            sentences, n = [], 0
            for v in vids:
                sent, k = self._capability_sentence(v, self._os_for(v, question), cap, ar)
                sentences.append(sent)
                n += k
            tail = (" أوامر فحص فقط؛ RootIQ لا ينفّذها." if ar else " Inspection commands only; RootIQ does not run them.") if n else ""
            return " ".join(sentences) + tail, {"vendors": vids, "capability": cap, "commands": n}

        vid = vids[0] if vids else None
        v = kb.vendor(vid) if vid else None
        if v and pid is None:
            os_list = ", ".join(o["name"] for o in v["os_families"]) or "-"
            series = "; ".join(s["name"] for s in v["series"][:6])
            text = (
                f"{v['name']}: نظم التشغيل {os_list}. عائلات الأجهزة (أمثلة): {series or '—'}. التغطية: {v['coverage']}، الثقة: {v['confidence']}."
                if ar else
                f"{v['name']}: operating systems {os_list}. Device families (examples): {series or 'n/a'}. Coverage: {v['coverage']}, confidence: {v['confidence']}."
            )
            return text, {"vendor": vid, "coverage": v["coverage"], "confidence": v["confidence"]}
        p = kb.problems[pid]
        title = p["title_ar"] if ar else p["title"]
        if v is None:
            causes = "; ".join(p["causes"][:3])
            text = (f"{title}: {p['summary_ar']} أسباب شائعة: {causes}." if ar else f"{title}: {p['summary']} Common causes: {causes}.")
            return text, {"problem": pid}
        os_id = self._os_for(vid, question)
        checks = [c for c in kb.checks_for(pid, vid, os_id) if c["available"]][:4]
        if not checks:
            text = (
                f"{title} على {v['name']}: لا توجد أوامر مُعدّة لهذا المصنّع بعد (التغطية: {v['coverage']}). راجع وثائق المصنّع."
                if ar else
                f"{title} on {v['name']}: no curated commands for this vendor yet (coverage: {v['coverage']}). Check the vendor documentation."
            )
            return text, {"vendor": vid, "problem": pid, "commands": 0}
        lines = "; ".join(f"{c['commands'][0]}" for c in checks).replace("<if>", "<interface>")
        text = (
            f"{title} على {v['name']} ({os_id}) — أوامر القراءة: {lines}. هذه أوامر فحص فقط؛ RootIQ لا ينفّذها."
            if ar else
            f"{title} on {v['name']} ({os_id}) — read-only checks: {lines}. These are inspection commands only; RootIQ does not run them."
        )
        return text, {"vendor": vid, "os": os_id, "problem": pid, "commands": len(checks)}


_UNSAFE = re.compile(r"[^\w./:\- ]")


def sanitize_hint(text: str | None, limit: int = 200) -> str | None:
    """Trim/limit free text supplied through the API before it is fed into regex matching."""
    if not text:
        return None
    return _UNSAFE.sub("", text)[:limit] or None
