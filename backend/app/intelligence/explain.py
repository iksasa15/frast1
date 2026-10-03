import json
import re

from app.llm import client as llm

TEMPLATES = {
    "link": {
        "en": (
            "Most likely cause: congestion on {label} ({conf}% confidence). Utilization reached {util}% of a "
            "{speed} Mbps link and latency rose from {lat0} ms to {lat} ms, starting {lead}s before the "
            "service symptoms. {n} affected service(s) sit downstream of this link."
        ),
        "ar": (
            "السبب الأرجح: ازدحام على الرابط {label} بثقة {conf}%. وصل الاستخدام إلى {util}% من سعة {speed} Mbps "
            "وارتفع زمن التأخير من {lat0} ms إلى {lat} ms، وبدأ ذلك قبل أعراض الخدمات بـ{lead} ثانية. "
            "عدد الخدمات المتأثرة الواقعة خلف هذا الرابط: {n}."
        ),
    },
    "svc-dns": {
        "en": (
            "Most likely cause: DNS failure on {label} ({conf}% confidence). Success rate dropped to {dns}% "
            "and latency rose to {dnsLat} ms. {n} dependent service(s) failed afterward."
        ),
        "ar": (
            "السبب الأرجح: فشل خدمة DNS على {label} بثقة {conf}%. انخفضت نسبة النجاح إلى {dns}% "
            "وارتفع زمن الاستجابة إلى {dnsLat} ms. عدد الخدمات المعتمدة التي فشلت لاحقًا: {n}."
        ),
    },
    "server": {
        "en": (
            "Most likely cause: resource pressure on {label} ({conf}% confidence). CPU reached {cpu}% "
            "and service latency rose to {http} ms. {n} service(s) hosted here are affected."
        ),
        "ar": (
            "السبب الأرجح: ضغط موارد على {label} بثقة {conf}%. وصل المعالج إلى {cpu}% "
            "وارتفع زمن الخدمة إلى {http} ms. عدد الخدمات المستضافة المتأثرة: {n}."
        ),
    },
}

NUM = re.compile(r"\d+(?:\.\d+)?")


def grounded(text: str, facts: dict) -> bool:
    """Reject any number in the text that is not in measured facts — anti-hallucination guard."""
    norm = lambda n: f"{float(n):g}"
    allowed = {norm(n) for n in NUM.findall(json.dumps(facts))}
    return all(norm(n) in allowed for n in NUM.findall(text))


def template(kind: str, facts: dict) -> dict:
    t = TEMPLATES[kind]
    return {"en": t["en"].format(**facts), "ar": t["ar"].format(**facts), "source": "template"}


SYSTEM = (
    "You rewrite incident explanations for a NOC engineer. Use ONLY the facts in the JSON. "
    "Never add a number that is not in the JSON. Use Western digits. Reply with 2 short sentences."
)


async def explain(kind: str, facts: dict) -> dict:
    base = template(kind, facts)
    if not llm.enabled():
        return base
    prompt = f"FACTS: {json.dumps(facts)}\nDRAFT: {base['en']}"
    text = await llm.complete(SYSTEM, prompt, max_tokens=120, timeout=4.0)
    if text and grounded(text, facts):
        return {**base, "en": text, "source": "llm"}
    return base
