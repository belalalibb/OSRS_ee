# OSRS_ee — أساس موحد + نواة محلية مختبرة

**PUBLISHED_TO_BRANCH / PR_OPEN — نواة محلية فقط؛ النظام المتكامل (JVM/GUI/عميل) غير منفذ.** الفرع `genspark_ai_developer` منشور على GitHub وPR #1 مفتوح إلى `main`؛ قد يتقدم آخر commit محلي/حزمة على الـremote عند فقد التفويض (انظر PROGRESS). لا تشغيل حسابات، لا نشر ويب، لا أفعال مالية. **309 اختبارًا offline تمر + 8 اختبارات هدف تُتخطى بصدق** (تحتاج جهازًا/مفاتيح)؛ متحقق من استنساخ نظيف في venv جديد (`evidence/clean_env_2026-10-24.md`).

**ابدأ من هنا:** [docs/RUNBOOK.md](docs/RUNBOOK.md) (التثبيت والتشغيل الصادق: ما يعمل/ما هو محاكى/ما هو ناقص) ثم [docs/ROADMAP.md](docs/ROADMAP.md) (الخطة الهندسية المرتبة بالاعتماديات مع ملفات/اختبارات/معايير قبول لكل مرحلة).

## النواة المنجزة محليًا (Python 3.13، stdlib + jsonschema)

| شريحة | الوحدة | ما تثبته (منطق القرار فقط) | الأدلة |
|---|---|---|---|
| S01 | `contracts/schemas/*.json`، `osrs_ee/contracts.py`، `canonical.py`، `guards.py` | 5 عقود JSON Schema 2020-12 صارمة، 48 fixtures، تجزئة canonical، guards deny-by-default | `evidence/s01_tests.md` |
| S02 | `osrs_ee/store.py` + `store_schema.sql` | SQLite (ADR-003): آلة حالات CAS، lease واحد/epochs، command journal، dedupe، موافقات أحادية، recovery → RECOVERY_REQUIRED لا READY | `evidence/s02_tests.md` |
| S03 | `osrs_ee/worker.py` | worker مالك واحد، FakeAdapter، PREPARED قبل الإرسال، UNKNOWN بعد الإرسال، abort/drain، health/قاطع دائرة | `evidence/s03_tests.md` |
| S06 | `osrs_ee/telegram.py` | RBAC default-deny، redaction/canary، outbox محدود بأولوية وretry محدود، approval callbacks مقيّدة | `evidence/s06_tests.md` |
| S07 | `osrs_ee/advisor.py` | AI استشاري فقط: consent، تنقيح، ميزانيات/مهلة، AIProposal فقط، الحقن لا يمنح سلطة | `evidence/s07_tests.md` |
| S08 | `osrs_ee/release.py` | registry quarantine، خط إصدار صارم مع rollback متوافق/STOP، كاش محدود بلا هوية، admission بقياس، شبكة بلا fallback محظور | `evidence/s08_tests.md` |
| S04a | `osrs_ee/adapters/` (recording/replay/conformance)، `target_check.py` | تسجيل منقّح، إعادة صارمة، امتثال C1–C7، جرد الهدف بلا تشغيل | `evidence/s04a_tests.md` |
| S04c-local + SUP-02 | `config.py`, `supervisor.py`, `service.py` | TOML fail-closed، `FakeSupervisor` + **`ProcessSupervisor` عام** (عملية ابنة حقيقية: جاهزية/SIGTERM→SIGKILL/دليل خروج/قياس)، **بوابة جاهزية** STARTING→RUNNING بدليل فقط، إيقاف منظم، إعادة تشغيل محدودة | `evidence/s04c_local_tests.md`, `evidence/s04b_prep_wire01_tests.md` |
| S04b-prep | `adapters/loopback_readonly.py`, `measure.py`, `egress.py` | قراءة فقط عبر 127.0.0.1 و`dispatch()` مرفوض دائمًا؛ قياس /proc صادق؛ egress allowlist يرفض قبل `connect()` | `evidence/s04b_prep_wire01_tests.md` |
| S06b/S07b-local + WIRE-01 | `transports/`, `providers/`, `wiring.py` | نقل Telegram ومزوّد AI بـurllib ضد خادم وهمي؛ `wiring.py` يبنيهما REAL فقط بشروط opt-in أربعة وإلا FAKE/DISABLED | `evidence/s06b_local_tests.md`, `evidence/s07b_local_tests.md`, `evidence/s04b_prep_wire01_tests.md` |
| TEST-FAIL / TEST-TARGET | `tests/test_failures.py`, `tests/target/` | فقد طاقة محاكى، DB تالف/للقراءة فقط، حدود موارد، نقل فاشل محدود؛ اختبارات هدف/حية جاهزة تُتخطى بصدق (NOT_RUN) | `evidence/s04b_prep_wire01_tests.md` |

التثبيت والتشغيل: `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"` ثم `python -m pytest` (توقع **309 passed, 8 skipped**؛ الشبكة محجوبة في `tests/conftest.py`؛ لا يلزم أي خدمة) ثم `osrs-ee config-check --config config.example.toml` و`osrs-ee doctor --config config.example.toml`. نقطة الدخول الوحيدة `osrs-ee` (`osrs_ee/cli.py`) تقدم `status | validate | store init|show | demo | target-check | conformance | replay | service [--allow-real-network] | config-check | doctor | secret-scan` فقط (و`python -m osrs_ee` مكافئ)؛ `demo` و`service --config` محاكاة كاملة افتراضيًا (وضع `device` مرفوض؛ Telegram/AI حقيقيان فقط بـopt-in رباعي صريح) ولا يوجد أمر «تشغيل بوت». التفاصيل في RUNBOOK §1–§2. مقارنة هندسية قائمة على الأدلة مع المرجع Engine-Docs (ما اعتُمد كفكرة وأُعيد تنفيذه، وما رُفض ولماذا، وما لا يمكن التحقق منه هنا): `docs/ENGINE_DOCS_COMPARISON.md`.

ما لا يمكن إنجازه هنا (S04/S05، ADR-007/008، V01–V08، T01–T35 كاختبارات هدف) موثق في [docs/OUT_OF_SANDBOX.md](docs/OUT_OF_SANDBOX.md).

## المنجز

[FOUNDATION.md](docs/FOUNDATION.md) يجمع سجل الأدلة،35 قضية مفتوحة و35 اختبار قبول مقترحًا،ربط جميع بنود التقارير،القرارات والخلافات،المعمارية والعقود والأمن وخطة التنفيذ والترحيل. هذه نسخة مكثفة لاستعادة العمل الذي فقد مرارًا،وليست نسخًا بايتية للملفات السابقة.

[PROGRESS.md](PROGRESS.md) نقطة الاستئناف؛[TASKS.md](TASKS.md) المهام؛[RESUME_PROTOCOL.md](docs/RESUME_PROTOCOL.md) طريقة الفحص والاستعادة؛[RUNBOOK.md](docs/RUNBOOK.md) التثبيت/التشغيل والأنماط A/B/C؛[ROADMAP.md](docs/ROADMAP.md) خطة S04/S05 والمراحل المتبقية.

## المصدر والوجهة

الوجهة المختارة: https://github.com/belalalibb/OSRS_ee.git،الفرع main. **منشور**: `main`=`3740096f` (الأساس)، `genspark_ai_developer` مدفوع وPR #1 مفتوح (https://github.com/belalalibb/OSRS_ee/pull/1)؛ آخر commits قد تكون في حزمة الاستعادة فقط إلى حين عودة تفويض GitHub (التفويض متقطع؛ PROGRESS يحدد الـSHA البعيد والمحلي). بقية المستودعات مصادر فقط،وتفاصيلها وبصماتها في FOUNDATION.

Production URL: لا يوجد. Functional API/URIs: لا توجد. مسارات Agent Server المذكورة مراجع upstream وليست خدمات يقدمها هذا المستودع.

هذا نظام محلي مقترح حول JVM/GUI/عمليات طويلة العمر،وليس تطبيق Cloudflare Pages. لا npm build أو تشغيل عميل مطلوب الآن.

## البيانات والاستخدام

النماذج Account/Session/Lease/Command/Event/Approval/Artifact/Outbox منفذة في `osrs_ee/`. التخزين: SQLite معتمد (ADR-003، قرار المالك). لا بيانات حسابات أو أسرار في المستودع؛ credential/proxy كمراجع `ref:` فقط.

نتائج فحص الوثائق في [validation.json](evidence/validation.json). T01–T35 كلها NOT_RUN كاختبارات هدف؛ الاختبارات المحلية تغطي منطق القرار الخالص فقط. الـ44 اختبارًا التاريخية تخص المصدر وكانت mocked وسجلاتها الخام مفقودة.

## الحالة التشغيلية والخطوة التالية

- **يعمل الآن (محليًا، بلا هدف):** النواة A (contracts/store/guards) ومحاكاة B (`osrs-ee demo`: Worker+FakeAdapter، Outbox+FakeTransport، Advisor+FakeProvider). الاختبارات المحلية تثبت منطق القرار فقط وليست قبولًا للنظام.
- **غير منفذ (C):** نقطة قراءة حقيقية من عميل اللعبة و`ProcessSpec` لعميل حقيقي (المساند جاهز: `LoopbackReadOnlyAdapter`، `ProcessSupervisor`، `measure`، `egress`، `tests/target`؛ التنفيذ على الجهاز لا). نقل Telegram ومزوّد AI الحقيقيان **مكتوبان ومربوطان بالخدمة (`wiring.py`) ومختبران ضد خادم وهمي محلي فقط**؛ **لم يُشغَّلا حيًا قط** — يحتاجان مفاتيح اختبار وإذنًا من المالك (T02/T03/T35 جاهزة في `tests/target`). يحتاج قرارات المالك ADR-007/008 (البدائل والتوصية في OUT_OF_SANDBOX §1.1/§1.2) وجهاز هدف (RUNBOOK §3–§4، ROADMAP D0→S04b→S05).
- **النشر:** تفويض GitHub مؤجل إلى نهاية العمل بقرار المالك؛ عند منحه يُدفع الفرع عاديًا (الـremote عند `6552b84` سلف مباشر) ويُحدّث PR #1، وإلى ذلك تُحفظ الحزم الموثقة بالبصمة (`evidence/bundles.md`، ADR-013). لا force push ولا حذف تاريخ. المفاتيح الشخصية المنشورة في المحادثة مكشوفة ويجب إبطالها؛ لن تُستخدم.

غير المنفذ: V01–V08 للتحقق من ادعاءات المصدر؛قراراتstorage/OS/auth؛جميع شرائح التطبيق والاختبارات التشغيلية. لا ضمان anti-ban أوأرباح أوعدد نوافذ من أرقام التقارير.
