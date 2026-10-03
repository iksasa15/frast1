"""Generate docs/VENDORS.md from the knowledge base, so the numbers and tables in it cannot drift.

    python scripts/gen_vendors_doc.py           # rewrite docs/VENDORS.md
    python scripts/gen_vendors_doc.py --check   # exit 1 if docs/VENDORS.md is out of date (used by CI)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.knowledge import get_kb  # noqa: E402

kb = get_kb()
st = kb.stats()
rows = []
order = {"full": 0, "partial": 1, "profile-only": 2}
for vid, v in sorted(kb.vendors.items(), key=lambda kv: (order[kv[1]["coverage"]], kv[0])):
    n_cmd = len({cap for t in v["commands"].values() for cap in t})
    oses = ", ".join(o["id"] for o in v["os_families"]) or "-"
    rows.append(f"| `{vid}` | {v['name']} | {v['coverage']} | {v['confidence']} | {oses} | {len(v['series'])} | {n_cmd} | {len(v['syslog'])} |")
table = "\n".join(rows)
cov = st["coverage"]
syslog_vendors = [v for v in kb.vendors.values() if v["syslog"]]
syslog_names = "، ".join(v["name"].split(" (")[0] for v in syslog_vendors)

PRIORITY = [("cisco", "Cisco (المعمل الافتراضي)"), ("juniper", "Juniper"), ("fortinet", "Fortinet"), ("hpe-aruba", "Aruba"), ("arista", "Arista")]
cfg_rows = []
for vid, _ in PRIORITY:
    for o in kb.vendors[vid]["os_families"]:
        cm = kb.config_model(vid, o["id"])
        if not cm:
            continue
        j = lambda xs: " ; ".join(f"`{x}`" for x in xs) or "—"
        cfg_rows.append(f"| {kb.vendors[vid]['name'].split(' (')[0]} — {o['name']} | {cm['style']} | {j(cm['enter'])} | {j(cm['save'])} | {j(cm['safe_change'])} | {j(cm['rollback'])} |")
cfg_table = "\n".join(cfg_rows)

text = f"""# قاعدة معرفة المصنّعين (Vendor Knowledge Base)

> **الجواب المباشر على السؤال «هل يعرف كل الشركات والسوتشات والإصدارات والمشاكل؟»:** يعرف **{st['vendors']} مصنّعًا**، **{st['osFamilies']} عائلة نظام تشغيل**، **{st['seriesFamilies']} عائلة/سلسلة أجهزة**، و**{st['problems']} نمط مشكلة**، لكن **بمستويات تغطية معلنة**: {cov['full']} مصنّعين بتغطية كاملة، {cov['partial']} جزئية، و{cov['profile-only']} «تعريف فقط». **لا يدّعي الشمول**: الموديلات بمستوى السلسلة لا كل SKU، والأوامر وأنماط syslog كُتبت من المعرفة العامة (لم تُلتقط من أجهزة حقيقية) وتحمل علامة ثقة.

الكود: `backend/app/knowledge/` (المحمّل والمتحقق) · البيانات: `backend/app/knowledge/data/` · الوكلاء: `vendor` و`logs` (انظر [`AGENTS.md`](AGENTS.md) §4.15–4.16) · الاختبارات: `test_knowledge_base.py` `test_vendor_agents.py`.

## 1. ماذا في القاعدة

| الملف | المحتوى |
|---|---|
| `data/vendors/<id>.json` | ملف لكل مصنّع: الأسماء المستعارة (EN/AR)، الفئات، أرقام IANA PEN، عائلات أنظمة التشغيل (regex لـ`sysDescr` ولصيغة الإصدار، نوع Netmiko، مثال)، سلاسل الأجهزة (الاسم، الدور، النظام)، جداول الأوامر لكل قدرة، أنماط syslog، روابط النشرات الأمنية، `coverage` و`confidence` |
| `data/problems.json` | {st['problems']} نمط مشكلة: الأعراض والكلمات المفتاحية (EN/AR)، الأسباب، **فحوصات** (بأسماء قدرات)، **إصلاحات** (كلها تحتاج موافقة، مع التراجع)، معايير تحقق بمقاييس RootIQ، ونطاق الانطباق (`applies_to`) |
| `data/capabilities.json` | {st['capabilities']} «قدرة» موحّدة (عرض الإصدار، حالة المنافذ، أخطاء CRC، البصريات، VLAN، STP، MAC، الجيران، CPU، الذاكرة، البيئة، OSPF/BGP، LAG، PoE، QoS…) — هي ما يربط المشكلة بأمر كل مصنّع |

الأرقام المولَّدة من الكود: {st['commandEntries']} مدخل أمر، {st['syslogPatterns']} نمط syslog لـ{len(syslog_vendors)} مصنّعين ({syslog_names}).

## 2. جدول التغطية (مولَّد من القاعدة)

| المعرّف | المصنّع | التغطية | الثقة | أنظمة التشغيل | عائلات الأجهزة | قدرات لها أوامر | أنماط syslog |
|---|---|---|---|---|---|---|---|
{table}

معنى التغطية:
* **full** — أوامر فحص لمعظم القدرات + regex للهوية والإصدار (وأنماط syslog لبعضهم فقط: انظر العمود الأخير؛ HPE/Aruba بلا أنماط syslog بعد).
* **partial** — بعض ما سبق (مثلًا H3C: هوية وسلاسل بلا أوامر)؛ راجع وثائق المصنّع قبل الاعتماد.
* **profile-only** — يُعرَّف المصنّع ونظامه وسلاسله (ورقم PEN والاسم) فقط، **بلا أوامر**؛ وكيل `vendor` يقول «لا توجد أوامر مُعدّة» ولا يخترع.

معنى الثقة (`confidence`): مدى الوثوق بما كُتب، وليس بحجمه. **لا شيء هنا مؤكَّد بالتقاط من جهاز حقيقي**؛ الاستثناء الوحيد أرقام IANA PEN التي فُحصت مقابل سجل IANA (التاريخ داخل كل ملف في `pen_verification`).

## 3. كيف يُستخدم (التكامل)

```mermaid
flowchart LR
  KB[(vendor KB JSON)] --> VEN[vendor agent]
  KB --> LOG[logs agent]
  KB --> RAG[knowledge: vendor / vendor-cmd / problem chunks]
  KB --> TRN[training/build_dataset.py]
  LOG -->|syslog_link_down| PIPE[pipeline] --> INC[incident]
  INC --> ORC[orchestrator] --> VEN -->|vendorContext| REM[remediation: plan.vendorCommands]
  REM --> GR[guardrail: vendor_commands_read_only]
  RAG --> COP[copilot: vendor_help]
```

1. **هوية الجهاز:** `POST /api/vendors/identify` أو حقول العقدة في `configs/topology.json` (`vendor` نص حر، و`sysDescr`، و`sysObjectId`، و`os`). الأولوية: `sysObjectId` (رقم المؤسسة) ثم `sysDescr` (regex) ثم التلميح. يُرجع المصنّع والنظام والإصدار (مع توحيده: `17.09.04a` = `17.9.4a`) والموديل ونوع Netmiko و`confidence`.
2. **إثراء الحادثة:** بعد RCA يحدد `vendor` الجهاز/المنفذ (رابط ← طرفاه) ويطابق المقاييس مع الأنماط ويبني `incident.vendorContext`. يظهر في الخطة (`plan.vendorCommands`) وفي لوحة الحادثة («Vendor diagnostics»).
3. **Syslog:** `POST /api/syslog` (رمز الإدخال نفسه). سطر «المنفذ Gi0/0 سقط» بصيغة أي مصنّع مدعوم ← حدث `syslog_link_down` على الرابط ← الـpipeline.
4. **الـCopilot:** «ما أمر فحص أخطاء CRC على Juniper؟» ← جواب حرفي من القاعدة (لا يعاد صياغته بالـLLM) مع «RootIQ لا ينفّذها».
5. **الـRAG:** ملف لكل مصنّع وجدول أوامر لكل نظام وملف لكل مشكلة (بوزن 0.9 كي لا تطغى على وثائق المشروع).
6. **التدريب:** `training/build_dataset.py` يحوّلها إلى بيانات (انظر [`../training/README.md`](../training/README.md)).

## 3b. الأجهزة ذات الأولوية: Cisco وJuniper وFortinet وAruba وArista

ملاحظة من مهندسي الميدان: هذه أغلب المصنّعين غير Cisco، والمعمل الافتراضي (EVE-NG) أجهزته Cisco. **الفرق الحقيقي بينها غالبًا في أمرين:** صيغة كتابة الأوامر، وطريقة حفظ الإعداد (NVRAM / commit). لذلك أضافت القاعدة لكل نظام تشغيل من هذه الخمسة:

* **نموذج الإعداد `config_model`:** هل التغيير يسري فورًا ويحتاج حفظًا (`running-startup`: Cisco وArista وAruba)، أم يمر بإعداد مرشّح ويحتاج `commit` (`candidate-commit`: Junos وIOS-XR)، أم يُطبَّق ويُحفظ تلقائيًا (`auto-save`: FortiOS)؟ مع أوامر الدخول والحفظ ونقطة الاسترجاع والتغيير الآمن والتراجع.
* **أسلوب الأوامر `cli_style`** (EN/AR): أوضاع الـCLI، الاختصارات، الفلاتر، أسماء الواجهات (`Gi0/1` مقابل `ge-0/0/1` مقابل `1/1/1` مقابل `port1`).

| النظام | النمط | الدخول | الحفظ / التفعيل | تغيير أكثر أمانًا | التراجع |
|---|---|---|---|---|---|
{cfg_table}

* يظهر هذا في **لوحة الحادثة** («Applying a change») وفي `plan.vendorCommands.devices[].configModel`، ويجيب عنه الـCopilot («كيف أحفظ الإعداد على Juniper وArista؟» — حتى 4 مصنّعين جنبًا إلى جنب).
* **مصنّعو المعمل المختلط:** `configs/topology.multivendor.example.json` مثال جاهز فيه Cisco IOS وJuniper vQFX وArista vEOS وFortiGate-VM وAruba AOS-CX بحقول `sysDescr`/`vendor`؛ انسخه فوق `configs/topology.json` (أو `TOPOLOGY_PATH`) وعدّل الأسماء والمنافذ. صور EVE-NG الشائعة لهذه المصنّعين موجودة عادةً (تحقق من قائمة الصور والتراخيص عندك).
* أسماء الصور الافتراضية معروفة للقاعدة (`vQFX`, `vMX`, `vSRX`, `vEOS`, `cEOS`, `FortiGate-VM`, `AOS-CX`).
* **أضعفها ثقةً: Fortinet** (ثقة `low`): أوامر FortiOS وFortiSwitchOS كُتبت من المعرفة العامة. التقط مخرجات FortiGate-VM (`get system status`، سطور syslog) وأضفها لأمثلة `fortinet.json` لرفع الثقة. وAruba: أنماط syslog لـArubaOS-Switch فقط (صيغة `port X is now off-line`)؛ صيغة AOS-CX غير مضافة بعد.

## 4. الأمان

* أوامر «القراءة» تمر بقائمة سماح لأفعال الفحص (`show`, `display`, `get`, `diagnose`…) وقائمة منع لأفعال التغيير (`reload`, `write`, `set`, `clear`, `shutdown`…) **عند التحقق من البيانات وعند حكم الـGuardrail** (`vendor_commands_read_only`).
* أوامر التغيير مسموحة لقدرتين فقط: `clear_counters` و`bounce_interface`، وكل إصلاح يحمل `needsApproval: true`.
* `plan.vendorCommands.executable = false` دائمًا: RootIQ **يعرض** الأوامر ولا يدفعها؛ ما يُنفَّذ بعد موافقة المهندس يبقى الـplaybook الأبيض فقط. (منفّذ Netmiko متعدد المصنّعين عمل مستقبلي: انظر §7.)
* اسم المنفذ الذي يدخل في الأمر يُتحقق منه بنمط آمن (`[A-Za-z0-9/:._-]{{1,40}}`)؛ `Gi0/0; reload` مرفوض.
* جدول `default` لكل مصنّع صالح فقط لعائلات النظام المذكورة في `default_for` (مثلًا IOS-XE وIOS وNX-OS لدى Cisco، **لا IOS-XR**) — نظام آخر يحصل على «لا توجد أوامر مُعدّة» بدل صيغة نظام مختلف.

## 5. إضافة مصنّع أو أمر أو نمط (بدون تعديل كود)

1. أنشئ/عدّل `backend/app/knowledge/data/vendors/<id>.json` (انسخ بنية مصنّع قريب).
2. من `backend/`: `python -c "from app.knowledge import get_kb; print(get_kb().validate())"` — يجب أن تكون القائمة فارغة. يفحص: الحقول المطلوبة، أنواع التغطية/الثقة، تكرار PEN، أن كل regex يُترجم وأن **أمثلته تطابقه**، أن أوامر القراءة للقراءة فقط، أن القدرات موجودة، وأن مقاييس المشاكل من مقاييس RootIQ.
3. `python training/build_dataset.py` ثم `pytest` (اختبار يطلب إعادة توليد بيانات التدريب إن تغيّرت القاعدة).
4. ارفع مثالًا حقيقيًا (`sysDescr` وسطور syslog من جهازك) في `examples` لرفع `confidence` — هذا أفضل تحسين ممكن.

## 6. ما اختُبر (وما لا)

* ✅ سلامة البيانات (`validate()` = 0 أخطاء)، كل أمثلة `sysDescr` تُعرَّف على مصنّعها ونظامها، كل أمثلة syslog تطابق أنماطها، أن كل أوامر القراءة للقراءة فقط، أن الـvalidator يرفض بيانات فاسدة (أمر تغيير داخل قائمة القراءة، PEN مكرر، regex خاطئ، إصلاح بلا موافقة).
* ✅ التكامل: السيناريوهات الثلاثة تحصل على `vendorContext` و`plan.vendorCommands` وحكم Guardrail؛ تبديل مصنّع الجهاز يغيّر الأوامر دون تغيير المنطق؛ مصنّع مجهول يُذكر «غير معروف»؛ تعطيل `vendor` لا يعطّل الحادثة؛ سطر syslog لـCisco يفتح حادثة ويُنتج سببًا جذريًا على الرابط الصحيح.
* ⚠️ **لم يُختبر على أجهزة حقيقية.** الأوامر والـregex كُتبت من المعرفة العامة؛ قد تختلف عبارة أمر بين إصدارين أو موديلين. لذلك: `confidence`، والأوامر «مرجعية للمهندس» لا تُنفَّذ.
* ⚠️ المجمّع (`collectors/`) ووكيل المختبر ما زالا يعملان على مختبر Cisco فقط ولا يشغّلان مستمع syslog؛ الدخول حاليًا عبر `POST /api/syslog` (ضبط الأجهزة لإرسال syslog إلى مجمّع/سكربت يستدعيه عمل تشغيلي).

## 7. وكلاء مقترحون لاحقًا (لم يُنفَّذوا)

| الوكيل | ماذا يفعل | لماذا لم يُبنَ الآن |
|---|---|---|
| `lifecycle` | نهاية الدعم (EoL) والثغرات (CVE) للإصدار المكتشف من نشرات المصنّعين | يحتاج مصادر خارجية حيّة (روابط النشرات مسجلة في `advisories`) وتحققًا من كل مصدر |
| `config` | نسخ احتياطي/مقارنة للإعدادات + **منفّذ Netmiko متعدد المصنّعين** (`netmiko` device type مخزّن لكل نظام) | تنفيذ حقيقي على أجهزة؛ يحتاج مختبرًا لكل مصنّع وبوابة موافقة جديدة |
| `capacity` | توقّع التشبع من التاريخ | يحتاج تخزين قياسات طويل الأمد (BLUEPRINT §9) |
"""
OUT = ROOT / "docs" / "VENDORS.md"
norm = lambda t: t.replace("\r\n", "\n")
if "--check" in sys.argv:
    if not OUT.exists() or norm(OUT.read_text(encoding="utf-8")) != norm(text):
        print("docs/VENDORS.md is out of date: run `python scripts/gen_vendors_doc.py` and commit the result.")
        raise SystemExit(1)
    print("docs/VENDORS.md is up to date")
else:
    OUT.write_bytes(norm(text).encode("utf-8"))
    print("written", OUT, len(text))
