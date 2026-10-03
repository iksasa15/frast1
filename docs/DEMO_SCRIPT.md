# Demo script — 5 minutes

> Presenter speaks; **Ahmed (FE)** on keyboard. Bracket numbers = measured (`docs/RESULTS.md`) or scenario design (evidence targets). Full day clock: `docs/RUNBOOK.md`.

**Roles:** Presenter (voice) · FE Ahmed (hotkeys) · BE standby · INFRA (EVE)

| Time | Presenter | Action (Ahmed) |
|---|---|---|
| 0:00 | «هذي شبكة حقيقية تشتغل الحين داخل EVE-NG: راوتر، سويتشين، سيرفر DNS وتطبيق، وكولكتر RootIQ. كل شي أخضر.» | Presenter Mode (`Shift+P`), full map healthy |
| 0:20 | «كل خط هنا مو رسمة — هو رابط بين منفذين حقيقيين. هذا R1 Gi0/0 إلى SW1 Gi0/1: السرعة، الاستخدام، التأخير، الفقد — مباشر من SNMP.» | Click link `r1–sw1` → LinkInspector |
| 0:45 | «الحين بنسوي اللي يصير كل يوم في مراكز العمليات: حركة كثيفة غير مهمة تخنق الرابط الرئيسي.» | `Shift+1` — stopwatch starts |
| 1:00 | «شوفوا اليسار: هذا اللي تعرضه أدوات المراقبة التقليدية — **[~33]** تنبيه من الراوتر والتطبيق والـDNS، كل واحد لحاله. المهندس لازم يربطها بمخه.» | AlertStorm fills |
| 1:25 | «RootIQ جمّعها في حادثة **وحدة**، ورتّب الأسباب، وحدد: ازدحام على R1 Gi0/0 — شوفوا الثقة على الشاشة. الساعة وقفت عند **[~11]** ثانية — هدفنا كان أقل من 60.» | Link pulses red; root-cause fills |
| 1:55 | «ليش نثق فيه؟ لأنه ما يعطيك جواب صندوق أسود. هذي الأدلة المقاسة: الاستخدام **[~97]%**، التأخير من **[~2]** إلى **[~86] ms**، وبدأ قبل أعراض الخدمات بـ**[~6]** ثواني.» | Point EvidenceList |
| 2:20 | «وهذي المرشحات الثانية: DNS كان شاذ — لكن النظام عرف إنه **عَرَض** لأنه واقع خلف الرابط المزدحم، فخفّض درجته. هذا فهم الطوبولوجيا، مو مجرد أرقام.» | CandidateRanking + `suppressedBy` |
| 2:45 | «التوصية: تطبيق سياسة QoS تحد الحركة الكبيرة. مخاطرة منخفضة. لكن RootIQ **ما ينفذ شي بدون موافقة المهندس**.» | ActionCard |
| 3:00 | «نفترض المهندس رفض لأننا خارج نافذة التغيير.» | Reject → `Outside change window` → Confirm reject |
| 3:15 | «ما تغير شي في الشبكة، والقرار انسجل بالسبب والاسم والوقت.» | Timeline shows **Rejected** |
| 3:30 | «الحين يعتمد.» | Approve Remediation |
| 3:40 | «RootIQ دخل على الراوتر وطبّق السياسة فعليًا — شوفوا التأخير ينزل والخط يرجع أخضر.» | Map recovers |
| 4:05 | «الحادثة انحلت: الاكتشاف **[&lt;1]** ث، السبب **[~11]** ث، التعافي **[~27]** ث. وكل خطوة في سجل تدقيق.» | Timeline + KPI |
| 4:25 | «وجربناه **[9]** مرات على 3 أنواع أعطال — شبكة، DNS، وموارد سيرفر — والسبب الأول كان صحيح **[9/9]**، وتقليل الضجيج **[~96]%**.» | Analytics page |
| 4:45 | «RootIQ: Find the cause before it becomes an outage.» | Back to green map |

## Optional add-on — vendor awareness (90 seconds, after 4:25 or as the answer to «بس Cisco؟»)

| Time | Presenter | Action |
|---|---|---|
| +0:00 | «RootIQ مو مربوط بـCisco. كل جهاز يُعرَّف بمصنّعه ونظامه وإصداره، وكل مصنّع له لغته.» | Open the incident plan → **Vendor diagnostics** (R1 and SW1: Cisco IOS, read-only commands with the real port) |
| +0:25 | «والفرق الحقيقي بين المصنّعين في طريقة حفظ الإعداد: عند Cisco تحفظ، وعند Juniper تعمل commit، وعند Fortinet يُحفظ تلقائيًا.» | Expand **Applying a change** (running → startup, safer change, roll back) |
| +0:45 | «واسألوا المساعد بالعربي — الجواب من قاعدة المعرفة حرفيًا وبدون تخمين.» | Agents → Copilot: «كيف أحفظ الإعداد على Juniper وCisco وFortinet؟» |
| +1:10 | «حتى لو الجهاز ما نعرفه، نقول لكم ما عندنا أوامر له بدل ما نخترع. ولا شي من هذا يُنفَّذ بدون موافقة مهندس.» | Ask about a profile-only vendor (e.g. TP-Link) → «no curated command» |

Backup if the UI is slow: `curl -X POST localhost:8000/api/copilot/ask -H 'content-type: application/json' -d '{"question":"How do I save the config on Junos vs Cisco vs Fortigate?"}'`.
Mixed-vendor lab to show on a slide: `configs/topology.multivendor.example.json`.

## Golden rules

- Do not read the screen · never say «إن شاء الله يشتغل»
- Unexpected: «This is live — let me show you» → `docs/REHEARSAL.md` failover
- Judges should see numbers more than talk
- After pitch: leave stack running (`docs/RUNBOOK.md` T+)

## Pre-demo

```bash
./scripts/preflight.sh
./scripts/demo-reset.sh
# then wait baseline warm (T−15) — no inject
```
