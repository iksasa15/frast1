"""Local RAG index: chunker + redactor + TF-IDF retrieval.

No external service is needed (works offline in the lab). The retrieval API is small on
purpose (`add_text`, `search`) so the TF-IDF backend can later be swapped for pgvector / an
embedding model without touching the agents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from app.core.config import settings

MAX_CHARS = 900
MIN_CHARS = 40

# ---------------------------------------------------------------- safety
# Strict mode (device config files): any line mentioning a credential keyword is dropped.
_CRED_ANY = re.compile(r"(?i)(password|passwd|secret|community|token|api[-_ ]?key)")
# Soft mode (prose, docs, code samples): only credential-shaped values are masked.
_ASSIGN = re.compile(
    r"(?i)([\w-]*(?:password|passwd|secret|token|api[-_]?key|community)[\w-]*\s*[=:]\s*['\"]?)[^\s'\"]+"
)
_IOS_SECRET = re.compile(r"(?i)\b(secret|password|community)(\s+\d)?(\s+)([A-Za-z0-9]*[-_0-9][A-Za-z0-9_-]*)")
_SNMP_C = re.compile(r"(\s-c\s+)\S+")
_KEY_LIKE = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}|gsk_[A-Za-z0-9]{20,})")
_LEARN = re.compile(r"(?i)\b(?:secret|password|community)(?:\s+\d)?\s+([A-Za-z0-9]*[-_0-9][A-Za-z0-9_-]*)")
INJECTION_RE = re.compile(
    r"(?i)("
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)"
    r"|disregard (the |all )?(system|previous|prior)"
    r"|you are now\b"
    r"|new instructions\s*:"
    r"|reveal (the |your )?(system )?prompt"
    r"|approve (the )?(action|remediation|change)s? (automatically|immediately|without)"
    r"|تجاهل (كل |جميع )?(التعليمات|الأوامر|القواعد)"
    r"|تجاهل ما سبق"
    r")"
)


def learn_secrets(text: str) -> set[str]:
    """Credential literals found in device configs — masked everywhere else they appear."""
    return {m.group(1) for m in _LEARN.finditer(text)}


def redact(text: str, *, strict: bool = False, secrets=()) -> str:
    """Remove credentials from text before it is indexed or shown."""
    out = []
    for line in text.splitlines():
        if strict and _CRED_ANY.search(line):
            head = line.split()[0] if line.split() else ""
            out.append(f"{head} <redacted credential line>")
            continue
        if not strict:
            line = _ASSIGN.sub(r"\1<redacted>", line)
            line = _IOS_SECRET.sub(r"\1\2\3<redacted>", line)
            line = _SNMP_C.sub(r"\1<redacted>", line)
        out.append(_KEY_LIKE.sub("<redacted-key>", line))
    text = "\n".join(out)
    for sec in secrets:
        text = text.replace(sec, "<redacted>")
    return text


def looks_injected(text: str) -> bool:
    return bool(INJECTION_RE.search(text))


def clean(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)


# ---------------------------------------------------------------- arabic-aware normalisation
_TASHKEEL = re.compile(r"[ً-ٰٟـ]")
_AL = re.compile(r"\bال(?=\w{3,})")


def normalize(text: str) -> str:
    t = text.lower()
    t = _TASHKEEL.sub("", t)
    t = re.sub("[أإآٱ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("_", " ")
    return _AL.sub("", t)


_MD_NOISE = re.compile(r"(\*\*|__|`|^#{1,6}\s*|^\s*[-*]\s+|\|)", re.M)


def strip_md(text: str) -> str:
    t = _MD_NOISE.sub(" ", text)
    return re.sub(r"\s+", " ", t).strip()


_AR_STOP = "في من على الى إلى عن مع هذا هذه ذلك التي الذي هو هي ما ماذا كيف لماذا هل أن ان كان كل او أو ثم قد لا لم لن".split()
STOP_WORDS = sorted(set(ENGLISH_STOP_WORDS) | {normalize(w) for w in _AR_STOP})

METRIC_NAMES = {
    "cpu_percent": "CPU utilization (processor load)",
    "mem_percent": "memory utilization (RAM)",
    "link_utilization": "link utilization (bandwidth used)",
    "link_latency_ms": "link latency (delay)",
    "link_packet_loss": "link packet loss",
    "if_out_discards_rate": "interface output discards",
    "if_oper_status": "interface operational status (up/down)",
    "dns_success_rate": "DNS success rate",
    "dns_latency_ms": "DNS latency",
    "http_latency_ms": "web application HTTP latency",
    "http_ok": "web application HTTP health",
    "poll_timeout": "poll timeout (device did not answer)",
    "syslog_link_down": "syslog link-down message",
}

# down-weight very large, narrative sources so focused docs win ties
KIND_WEIGHT = {"plan": 0.6, "lab-config": 0.9, "vendor": 0.9, "vendor-cmd": 0.9, "problem": 0.9, "threshold": 1.2}  # short exact facts win ties against long narrative docs


# ---------------------------------------------------------------- model
@dataclass
class Chunk:
    id: str
    kind: str  # doc | plan | topology | threshold | playbook | lab-config | vendor | vendor-cmd | problem | incident | postmortem
    source: str
    title: str
    text: str
    suspicious: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def index_text(self) -> str:
        return f"{self.title}\n{self.text}"


def chunk_markdown(
    text: str, source: str, kind: str, max_chars: int = MAX_CHARS, *, strict: bool = False, secrets=()
) -> list[Chunk]:
    sections: list[tuple[str, list[str]]] = []
    stack: list[str] = []
    body: list[str] = []
    title = source

    def flush():
        if any(x.strip() for x in body):
            sections.append((title, body[:]))
        body.clear()

    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            flush()
            level = len(m.group(1))
            stack[:] = stack[: level - 1] + [m.group(2).strip()]
            title = " > ".join(stack)
        else:
            body.append(line)
    flush()

    chunks: list[Chunk] = []
    for sec_title, lines in sections:
        paras = re.split(r"\n\s*\n", "\n".join(lines).strip())
        pieces: list[str] = []
        for p in paras:
            if len(p) <= max_chars:
                pieces.append(p)
                continue
            cur = ""
            for ln in p.splitlines():
                while len(ln) > max_chars:
                    pieces.append(ln[:max_chars])
                    ln = ln[max_chars:]
                if len(cur) + len(ln) + 1 > max_chars and cur:
                    pieces.append(cur)
                    cur = ""
                cur = f"{cur}\n{ln}" if cur else ln
            if cur:
                pieces.append(cur)
        buf = ""
        for piece in pieces:
            if len(buf) + len(piece) + 2 > max_chars and buf:
                chunks.append(_mk(source, kind, sec_title, buf, len(chunks), strict, secrets))
                buf = ""
            buf = f"{buf}\n\n{piece}" if buf else piece
        if buf:
            chunks.append(_mk(source, kind, sec_title, buf, len(chunks), strict, secrets))
    return [c for c in chunks if len(c.text.strip()) >= MIN_CHARS]


def _mk(source: str, kind: str, title: str, text: str, n: int, strict: bool = False, secrets=()) -> Chunk:
    text = redact(clean(text), strict=strict, secrets=secrets).strip()
    return Chunk(
        id=f"{source}#{n}",
        kind=kind,
        source=source,
        title=title,
        text=text,
        suspicious=looks_injected(text),
    )


# ---------------------------------------------------------------- root discovery
def find_root() -> Path | None:
    here = Path(__file__).resolve()
    cands = []
    if settings.kb_root:
        cands.append(Path(settings.kb_root))
    cands += [here.parents[3], here.parents[2], Path.cwd(), Path.cwd().parent]
    for c in cands:
        if (c / "docs").is_dir():
            return c
    return None


# ---------------------------------------------------------------- sentence-level snippets
_SENT = re.compile(r"(?<=[.!?؟\n])\s+")


def snippet(text: str, query: str, max_chars: int = 380) -> str:
    q = set(re.findall(r"\w{3,}", normalize(query)))
    sents = [strip_md(s) for s in _SENT.split(text)]
    sents = [s for s in sents if len(s) > 8]
    if not sents:
        return strip_md(text)[:max_chars]
    scored = [
        (len(q & set(re.findall(r"\w{3,}", normalize(s)))), i, s) for i, s in enumerate(sents)
    ]
    best = sorted(scored, key=lambda x: (-x[0], x[1]))[:2]
    picked = [s for _, _, s in sorted(best, key=lambda x: x[1])]
    out = " ".join(picked)
    return out if len(out) <= max_chars else out[: max_chars - 1] + "…"


# ---------------------------------------------------------------- index
class KnowledgeIndex:
    def __init__(self):
        self.chunks: dict[str, Chunk] = {}
        self._vec = None
        self._mat = None
        self._ids: list[str] = []
        self._dirty = True
        self.root: Path | None = None
        self.secrets: set[str] = set()

    # ---- building
    def add(self, chunk: Chunk):
        self.chunks[chunk.id] = chunk
        self._dirty = True

    def remove_prefix(self, prefix: str):
        for k in [k for k in self.chunks if k.startswith(prefix)]:
            del self.chunks[k]
            self._dirty = True

    def add_text(self, id_: str, kind: str, source: str, title: str, text: str, **meta):
        text = redact(clean(text), secrets=self.secrets).strip()
        self.add(Chunk(id_, kind, source, title, text, looks_injected(text), meta))

    def load_static(self, topology_raw: dict | None = None, graph=None, playbooks: dict | None = None):
        self.chunks = {k: v for k, v in self.chunks.items() if v.kind in ("incident", "postmortem")}
        self.root = find_root()
        self.secrets = set()
        if self.root:
            cfg_dir = self.root / "lab" / "configs"
            cfg_files = sorted(cfg_dir.glob("*.cfg")) + sorted(cfg_dir.glob("*.yaml"))
            for p in cfg_files:  # learn credential literals first, so they are masked in every source
                self.secrets |= learn_secrets(p.read_text(encoding="utf-8", errors="ignore"))
            # Top-level docs/*.md plus curated packs under docs/** (e.g. docs/network/)
            docs_dir = self.root / "docs"
            md_files = sorted({*docs_dir.glob("*.md"), *docs_dir.glob("**/*.md")})
            for p in md_files:
                if p.is_file():
                    self._add_md(p, "doc")
            for name, kind in (("README.md", "doc"), ("RootIQ_Daily_Plan.md", "plan"), ("lab/eve/README.md", "doc")):
                p = self.root / name
                if p.exists():
                    self._add_md(p, kind)
            for p in cfg_files:
                rel = p.relative_to(self.root).as_posix()
                body = f"# {p.name}\n" + p.read_text(encoding="utf-8", errors="ignore")
                for c in chunk_markdown(body, rel, "lab-config", strict=True, secrets=self.secrets):
                    self.add(c)
        if topology_raw:
            self._add_topology(topology_raw, graph)
        self._add_thresholds()
        for pb in (playbooks or {}).values():
            self._add_playbook(pb)
        self._add_vendor_kb()
        self._dirty = True

    def _add_md(self, path: Path, kind: str):
        rel = path.relative_to(self.root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for c in chunk_markdown(text, rel, kind, secrets=self.secrets):
            self.add(c)

    def _add_topology(self, raw: dict, graph):
        for n in raw["nodes"]:
            ifs = "; ".join(
                f"{i['name']} ({i['speedMbps']} Mbps{', ' + i['description'] if i.get('description') else ''})"
                for i in n["interfaces"]
            )
            self.add_text(
                f"topology:node:{n['id']}", "topology", "live discovery snapshot", f"Device {n['label']}",
                f"Device {n['label']} ({n['type']}, {n.get('vendor', 'n/a')}) management IP {n['managementIp']}. Interfaces: {ifs}.",
            )
        for l in raw["links"]:
            self.add_text(
                f"topology:link:{l['id']}", "topology", "live discovery snapshot", f"Link {l['id']}",
                f"Link {l['id']} connects {l['source'].upper()} {l['sourcePort']} to {l['target'].upper()} {l['targetPort']} (role {l.get('role', 'n/a')}).",
            )
        for s in raw["services"]:
            deps = ", ".join(s.get("dependsOn", [])) or "nothing"
            chain = ""
            if graph is not None:
                try:
                    chain = " Dependency path from the vantage point: " + " -> ".join(graph.service_dependencies(s["id"])) + "."
                except Exception:
                    chain = ""
            self.add_text(
                f"topology:service:{s['id']}", "topology", "live discovery snapshot", f"Service {s['label']}",
                f"Service {s['id']} ({s['label']}) runs on {s['host']} port {s['port']} and depends on {deps}.{chain}",
            )

    def _add_thresholds(self):
        from app.intelligence.thresholds import THRESHOLDS

        # One short chunk per metric so "CPU thresholds" matches the CPU chunk, not a long list.
        for m, (w, c, d) in THRESHOLDS.items():
            human = METRIC_NAMES.get(m, m.replace("_", " "))
            if d == "up":
                rule = f"warning when value >= {w}, critical when value >= {c}"
            else:
                rule = f"warning when value < {w}, critical when value <= {c}"
            self.add_text(
                f"threshold:{m}", "threshold", "app/intelligence/thresholds.py", f"Threshold: {human}",
                f"Detection threshold for {human} (metric {m}): {rule}.",
            )

    def _add_playbook(self, pb: dict):
        steps = "\n".join(f"{s['n']}. [{s['kind']}] {s['title']}" for s in pb["steps"])
        rb = "\n".join(f"- {r['title']}" for r in pb["rollback"])
        self.add_text(
            f"playbook:{pb['id']}", "playbook", "app/agents/playbooks.py", f"Playbook {pb['id']}: {pb['title']}",
            f"{pb['title']}. Risk {pb['risk']}. Blast radius: {pb['blastRadius']}.\nPreconditions: "
            + "; ".join(pb["preconditions"])
            + f"\nSteps:\n{steps}\nRollback:\n{rb}",
        )

    def _add_vendor_kb(self):
        """Vendor profiles, per-OS command tables and the problem catalogue (app/knowledge/data)."""
        from app.knowledge import get_kb

        kb = get_kb()
        for v in kb.vendors.values():
            oses = "; ".join(f"{o['name']} ({o.get('version_scheme', '')[:120]})" for o in v["os_families"])
            series = "; ".join(f"{s['name']} [{s.get('role', '')}]" for s in v["series"])
            pens = ", ".join(str(e["pen"]) for e in v["enterprise_oids"])
            self.add_text(
                f"vendor:{v['id']}", "vendor", f"knowledge/vendors/{v['id']}", f"Vendor {v['name']}",
                f"{v['name']} ({', '.join(v['categories'])}). Aliases: {', '.join(v['aliases'])}. Operating systems: {oses or 'n/a'}. "
                f"Device families: {series or 'n/a'}. IANA enterprise number(s): {pens or 'n/a'}. "
                f"Coverage {v['coverage']}, confidence {v['confidence']}.",
            )
            for os_id, table in v.get("commands", {}).items():
                rows = "\n".join(
                    f"{cap}: " + " | ".join(entry.get("read") or entry.get("change") or []) for cap, entry in table.items()
                )
                if rows:
                    scope = "default commands" if os_id == "default" else f"{os_id} commands"
                    self.add_text(
                        f"vendor:{v['id']}:cmd:{os_id}", "vendor-cmd", f"knowledge/vendors/{v['id']}", f"{v['name']} {scope}",
                        f"{v['name']} CLI {scope} (read-only inspection unless marked change):\n{rows}",
                    )
        for p in kb.problems.values():
            checks = "; ".join(f"{c['capability']} ({c['why']})" for c in p["checks"])
            fixes = "; ".join(f"{f['title']} [risk {f['risk']}, needs approval]" for f in p["fixes"])
            self.add_text(
                f"problem:{p['id']}", "problem", "knowledge/problems.json", f"Problem: {p['title']}",
                f"{p['title']} ({p['category']}, severity {p['severity']}). {p['summary']} Common causes: {'; '.join(p['causes'])}. "
                f"Checks: {checks}. Fixes: {fixes}. Arabic: {p['title_ar']} — {p['summary_ar']}",
            )

    def upsert_incident(self, inc: dict):
        rc = inc.get("rootCause") or {}
        ex = inc.get("explanation") or {}
        act = inc.get("action") or {}
        ev = "; ".join(e.get("text", "") for e in (inc.get("evidence") or [])[:8])
        text = (
            f"Incident {inc['id']}: {inc['title']} (status {inc['status']}, severity {inc.get('severity')}). "
            f"Root cause: {rc.get('label', 'unknown')} ({rc.get('entityId', '')}) with confidence "
            f"{round(float(rc.get('confidence', 0)) * 100)}%. Affected services: {', '.join(inc.get('affectedServices') or []) or 'none'}. "
            f"Evidence: {ev}. Explanation: {ex.get('en', '')} {ex.get('ar', '')} "
            f"Action: {act.get('description', 'none')} ({act.get('approvalStatus', 'n/a')})."
        )
        self.remove_prefix(f"incident:{inc['id']}")
        self.add_text(
            f"incident:{inc['id']}", "incident", f"incident/{inc['id']}", f"Incident {inc['id']}", text,
            entityId=rc.get("entityId"), status=inc["status"],
        )

    # ---- retrieval
    def _build(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._ids = list(self.chunks)
        if not self._ids:
            self._vec, self._mat = None, None
        else:
            self._vec = TfidfVectorizer(
                stop_words=STOP_WORDS,
                preprocessor=normalize,
                token_pattern=r"(?u)\b\w\w+\b",
                ngram_range=(1, 2),
                sublinear_tf=True,
            )
            self._mat = self._vec.fit_transform([self.chunks[i].index_text for i in self._ids])
        self._dirty = False

    def warm(self):
        if self._dirty:
            self._build()

    def search(self, query: str, k: int = 5, kinds: set[str] | None = None, min_score: float | None = None) -> list[dict]:
        if self._dirty:
            self._build()
        if self._vec is None or not query.strip():
            return []
        thr = settings.rag_min_score if min_score is None else min_score
        q = self._vec.transform([query])
        sims = (self._mat @ q.T).toarray().ravel()
        sims = sims * [KIND_WEIGHT.get(self.chunks[i].kind, 1.0) for i in self._ids]
        order = sims.argsort()[::-1]
        hits: list[dict] = []
        for idx in order:
            score = float(sims[idx])
            if score < thr:
                break
            c = self.chunks[self._ids[idx]]
            if kinds and c.kind not in kinds:
                continue
            hits.append(
                {
                    "id": c.id,
                    "kind": c.kind,
                    "source": c.source,
                    "title": c.title,
                    "score": round(score, 3),
                    "snippet": snippet(c.text, query),
                    "text": c.text,
                    "suspicious": c.suspicious,
                }
            )
            if len(hits) >= k:
                break
        return hits

    def stats(self) -> dict:
        by_kind: dict[str, int] = {}
        for c in self.chunks.values():
            by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
        return {
            "chunks": len(self.chunks),
            "byKind": by_kind,
            "suspicious": sum(1 for c in self.chunks.values() if c.suspicious),
            "root": str(self.root) if self.root else None,
            "backend": "tfidf",
            "minScore": settings.rag_min_score,
        }
