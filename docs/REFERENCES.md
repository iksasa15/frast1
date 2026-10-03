# المراجع: أوراق وكتب وبيانات فُحصت للمشروع

جُمعت قائمتها من حزمة `RootIQ_Resources.zip` التي أعدّها المستخدم (2026-09-30). **فُحصت كل أرقام arXiv أدناه مقابل عنوان الورقة في واجهة arXiv نفسها**؛ ولم تُنسخ الملخصات ولا ملفات PDF إلى المستودع، فقط العنوان والرابط وصلة الورقة بالمشروع بكلماتنا.

## الأوراق

| # | الورقة | الرابط | صلتها بالمشروع |
|---|---|---|---|
| 1 | QLoRA: Efficient Finetuning of Quantized LLMs | [2305.14314](https://arxiv.org/abs/2305.14314) | طريقة الضبط الدقيق في الخلية C2 (نموذج 4-bit وLoRA فوقه) |
| 2 | A Survey of AIOps in the Era of Large Language Models | [2507.12472](https://arxiv.org/abs/2507.12472) | خلفية: موقع LLM من عمليات الأعطال والحوادث |
| 3 | A Survey of AIOps for Failure Management in the Era of Large Language Models | [2406.11213](https://arxiv.org/abs/2406.11213) | خلفية: كشف العطل وتحديد سببه وإصلاحه، وهي مراحل RootIQ |
| 4 | A Survey on LLM-based Multi-Agent System: Recent Advances and New Frontiers in Application | [2412.17481](https://arxiv.org/abs/2412.17481) | خلفية لتصميم الوكلاء الـ16 (لكن 14 منهم عندنا حتمية بلا LLM، انظر `AGENTS.md`) |
| 5 | Multi-Agent Collaboration Mechanisms: A Survey of LLMs | [2501.06322](https://arxiv.org/abs/2501.06322) | خلفية: أنماط تعاون الوكلاء |
| 6 | Retrieval-Augmented Generation for Large Language Models: A Survey | [2312.10997](https://arxiv.org/abs/2312.10997) | خلفية وكيل `knowledge` والـCopilot (فهرسنا اليوم TF-IDF لا دلالي، وحدّه مذكور في `AGENTS.md` §10) |
| 7 | Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG | [2501.09136](https://arxiv.org/abs/2501.09136) | اتجاه مستقبلي للاسترجاع |
| 8 | GemmAr: Enhancing LLMs Through Arabic Instruction-Tuning (LlamAr & GemmAr) | [2407.02147](https://arxiv.org/abs/2407.02147) | منهج بناء بيانات تعليمات عربية، وصلته بالمهام العربية في تدريبنا |
| 9 | A Large and Diverse Arabic Corpus for Language Modeling | [2201.09227](https://arxiv.org/abs/2201.09227) | خلفية عن المتون العربية |
| 10 | Loghub: A Large Collection of System Log Datasets for AI-driven Log Analytics | [2008.06448](https://arxiv.org/abs/2008.06448) | مصدر عينات السجلات التي فُحصت (لا تدخل التدريب: [الأسباب](../training/catalog/OTHER_SOURCES.md)) |
| 11 | A Large-Scale Evaluation for Log Parsing Techniques: How Far Are We? (Loghub-2.0) | [2308.10828](https://arxiv.org/abs/2308.10828) | معايير تحليل السجلات، وللمقارنة مع محلّل syslog عندنا مستقبلًا |

## كتب للقراءة (لا ننسخ منها)

- [Site Reliability Engineering](https://sre.google/sre-book/table-of-contents/) (Google، مجاني على الإنترنت): الحوادث وما بعدها، وتتوافق مع وكيل `learning` وتقارير post-mortem.
- The Site Reliability Workbook و Observability Engineering (O'Reilly).

## ما فُحص من البيانات وما نتج

| المصدر | النتيجة |
|---|---|
| Loghub (8 أنظمة × 2000 سطر: Linux وOpenSSH وApache وHDFS وHadoop وZookeeper وOpenStack وBGL) | ترخيصها «للبحث أو العمل الأكاديمي» فقط، وهي سجلات خوادم وحواسيب فائقة **لا سجلات أجهزة شبكة**، وبعضها يحوي عناوين IP وأسماء مضيفين حقيقية غير مُنقّاة. **لا تدخل تدريب نموذج يُشحن ولا المستودع.** استُعملت مرة واحدة فقط كفحص محلي: مرّرنا الـ16,000 سطرًا إلى محلّل syslog (`kb.parse_syslog`) فلم يُصنَّف **أي** سطر كحدث شبكي (0 إيجابية كاذبة)، أي أن قاعدة «ما لا يُعرف يُعدّ unparsed ولا يُخمَّن» صمدت على سجلات حقيقية |
| بقية القرارات (CIDAR، NetBench، Juniper-Catalog-Abstracts، قوائم Kaggle) | في [`training/catalog/OTHER_SOURCES.md`](../training/catalog/OTHER_SOURCES.md) مع السبب |
