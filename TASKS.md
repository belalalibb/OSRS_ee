# المهام الحالية

| ID | الحالة | المخرج / بوابة الإغلاق |
|---|---|---|
| DOC-01 | RECOVERED_FROM_RECORD | مصادر وبصمات وأدلة تاريخية موثقة؛ لم يُعد تدقيق upstream |
| DOC-02 | DONE_LOCAL | FOUNDATION موحدة: 35 قضية و35 اختبارًا مقترحًا وcrosswalk لـ29F و13R1 و16R2 والعقود والقرارات والخطة |
| DOC-03 | VALIDATED_LOCAL | فحص التغطية/JSON/أنماط الأسرار/ignore؛ evidence/validation.json |
| DOC-04 | DONE_LOCAL | RESUME_PROTOCOL 0.3 + ADR-013 + سجل الحزم؛ مسار الحفظ مختبر على مستودع تجريبي |
| SAVE-xx | RECURRING | بعد كل شريحة: commit → tests → bundle → verify+sha256 → رفع → تسجيل في PROGRESS/evidence/bundles.md |
| AUTH-01 | INTERMITTENT | OAuth نجح مرة 2026-10-23 ~21:30 (نشر + PR #1) ثم أُبطل؛ كل جلسة: محاولة واحدة ثم حزم. إبطال المفتاحين المكشوفين: NOT_CONFIRMED من المالك |
| PUB-01 | SUPERSEDED | «نشر الأساس قبل الكود» أُلغي بقرار المالك؛ انظر PUB-02 |
| PUB-02 | DONE 2026-10-23 | remote كان فارغًا (isEmpty=true، فُحص قبل أي push)؛ push عادي: `main`=`3740096f`، `genspark_ai_developer`=`790ec2e`؛ PR #1 https://github.com/belalalibb/OSRS_ee/pull/1 (20 commits)؛ تحقق من clone جديد: شجرة `3b091a89…` مطابقة، 91 ملفًا، 156 اختبارًا تمر من الـ clone |
| VERIFY-01 | BLOCKED_AUTH | V01–V08 عند source revisions مثبتة؛ تسبق التكاملات المتأثرة لا pure contracts |
| DEC-STORE | DECIDED | ADR-003 = SQLite (قرار المالك 2026-10-23) |
| DEC-OS/AUTH | OPEN | ADR-007/008 قبل process/GUI/auth integration |
| S01 | DONE_LOCAL | 5 عقود JSON Schema 2020-12 + validator صارم + canonical hashing + guards خالصة؛ 48 fixtures؛ 43 اختبارًا offline تمر (evidence/s01_tests.md) |
| S02 | DONE_LOCAL | Store SQLite: accounts/sessions/leases/commands/events/approvals + journal + dedupe + recovery؛ اختبارات T04/T07/T08/T09 الخالصة مع persistent fake |
| S03 | DONE_LOCAL | worker/scheduler + fake adapter + cancellation + health (الأجزاء الخالصة من T16/T17/T21/T29) فوق Store؛ concurrency=1؛ لا game I/O؛ 20 اختبارًا (evidence/s03_tests.md) |
| S04/S05 | GATED_OWNER + OUT_OF_SANDBOX | read-only target ثم pilot مراقب؛ تحتاج JVM/GUI/عميل على جهاز المالك |
| S06 | DONE_LOCAL | Telegram fake-first: RBAC default-deny، redaction/canary، outbox محدود، approval callbacks مقيّدة (T02/T03/T29 الخالصة)؛ 22 اختبارًا (evidence/s06_tests.md) |
| S07 | DONE_LOCAL | AI advisory fake-first: consent/redaction/حدود حجم-عمر-ميزانية-مهلة، مخرجات AIProposal فقط بلا سلطة تنفيذ، الحقن لا يمنح سلطة؛ 14 اختبارًا (evidence/s07_tests.md) |
| S08 | DONE_LOCAL | registry quarantine، manifest ثابت + خط إصدار صارم مع rollback متوافق أو STOP، كاش محدود بلا مسارات هوية، admission بقياس/احتياطي، سياسة شبكة بلا fallback محظور (T14/T15/T18/T19/T32 الخالصة)؛ 23 اختبارًا (evidence/s08_tests.md)؛ canary حي غير مُنمذج |
| OOS-01 | DONE_LOCAL | docs/OUT_OF_SANDBOX.md: القرارات المفتوحة، V01–V08، S04/S05، مصفوفة T01–T35، متطلبات النشر |
| FINAL-01 | SUPERSEDED_BY_OWNER_REVIEW | المالك رفض اعتبار المنشور كافيًا (2026-10-23): طُلبت خطة هندسية عملية، دليل تثبيت/تشغيل صادق، فصل النواة/المحاكاة/التكامل، تصحيح التناقضات، فحص ملفات المستودع، وتحديث S04/S05. النتائج في DOC-05..DOC-08 أدناه. الوصف السابق: | كل الشرائح الممكنة محليًا منجزة ومنشورة على الفرع + PR #1. المتبقي يخص المالك: مراجعة/دمج PR، إبطال المفاتيح، ADR-007/008، S04/S05 على جهاز حقيقي |
| DOC-05 | DONE_LOCAL | تغليف ونقطة دخول: `pyproject.toml`، `requirements(-dev).txt`، CLI `osrs-ee` (status/validate/store/demo فقط — لا «run bot» وهمي)، `tests/test_cli.py` (5)؛ تثبيت من venv جديد متحقق (commit `7a63ebc`) |
| DOC-06 | DONE_LOCAL | `docs/RUNBOOK.md`: تثبيت/تشغيل، الأنماط A (نواة) / B (محاكاة) / C (متكامل غير منفذ)، جدول REAL/FAKE/MISSING، انتقالات A→B→C (commit `dc51bea`) |
| DOC-07 | DONE_LOCAL | `docs/ROADMAP.md`: خطة مرتبة بالاعتماديات D0→S04a→S04b→S04c→S05 + S06b/S07b/S08b مع ملفات/اختبارات/معايير قبول لكل مرحلة (commit `dc51bea`) |
| DOC-08 | DONE_LOCAL | تصحيح التناقضات (NOT_PUSHED/«OAuth غير متاح»/156) في README/PROGRESS/TASKS/FOUNDATION/OUT_OF_SANDBOX/RESUME_PROTOCOL 0.4؛ متطلبات جهاز الهدف والاختبارات التشغيلية المرتبة في OUT_OF_SANDBOX §3 |
| PUSH-02 | BLOCKED_AUTH | دفع `7a63ebc`/`dc51bea`/تصحيح الوثائق إلى `genspark_ai_developer` وتحديث وصف PR #1؛ يتم تلقائيًا عند أول جلسة بتفويض ناجح (fetch → تأكيد `6552b84` سلف → push عادي → تحقق SHA) |
| S04a | DONE_LOCAL | `osrs_ee/adapters/` (RecordingAdapter بتنقيح fail-closed، ReplayAdapter صارم، conformance C1–C7) + `target_check` (لا يشغّل شيئًا) + CLI target-check/conformance/replay؛ 20 اختبارًا؛ المجموع 181 (evidence/s04a_tests.md) |
| S04c-local | DONE_LOCAL | `config.py` (TOML fail-closed، مراجع فقط، auth_mode مقفول) + `supervisor.py` (Protocol + FakeSupervisor) + `service.py` (قبول→بدء→إيقاف منظم؛ UNKNOWN/لا exit proof→RECOVERY_REQUIRED؛ إعادة تشغيل محدودة→CIRCUIT_OPEN؛ ضغط→إيقاف؛ تنبيهات منقّحة) + CLI `service` (simulated فقط) + `config.example.toml`؛ 22 اختبارًا؛ المجموع 203 (evidence/s04c_local_tests.md)؛ المشرف الحقيقي يبقى على الجهاز |
| S06b-local | DONE_LOCAL | `osrs_ee/transports/` TelegramHttpTransport (urllib، `ref:env:` → canary، allowlist، 429/5xx/4xx) + TelegramPoller/parse_update صارم؛ `tests/fake_http.py`؛ 14 اختبارًا؛ المجموع 217 (evidence/s06b_local_tests.md)؛ الربط بالخدمة وT02/T03 على دردشة حقيقية يحتاجان مفتاح اختبار من المالك |
| S07b-local | DONE_LOCAL | `osrs_ee/providers/openai_compat.py` (urllib، `ref:env:` → canary، allowlist، مهلة مقيدة بالـdeadline، حد حجم)؛ 9 اختبارات مع تكامل Advisor؛ المجموع 226 (evidence/s07b_local_tests.md)؛ لم يُتصل بأي مزوّد حقيقي |
| PKG-01 | DONE_LOCAL | `5c4716c`: إعلان الحزم الفرعية adapters/transports/providers في pyproject (خطأ حقيقي وُجد في تثبيت نظيف) + `tests/test_packaging.py` (2) |
| S04b-prep | DONE_LOCAL | `d47eebb`: `adapters/loopback_readonly.py` (قراءة فقط عبر 127.0.0.1، `dispatch()` دائمًا `NEVER_DISPATCH`)، `measure.py` (/proc، None بصدق)، `egress.py` (allowlist + `guarded_opener` يرفض قبل `connect()`)؛ 15 اختبارًا؛ **لا نقطة قراءة حقيقية بعد (ADR-008)** — evidence/s04b_prep_wire01_tests.md |
| SUP-02 | DONE_LOCAL | `1ff58e7` بوابة الجاهزية في الخدمة (`LEASED→STARTING→RUNNING` فقط بدليل جاهزية؛ `ready_timeout_seconds`؛ فشل البدء → RECOVERY_REQUIRED) + `e68c75e` `ProcessSupervisor` عام (subprocess، ready_file، SIGTERM→SIGKILL، دليل خروج، قياس /proc) و`host_measure` للقبول؛ 16 اختبارًا بعملية python ابنة؛ **لم يُشغَّل JVM/GUI قط (ADR-007)** |
| WIRE-01 | DONE_LOCAL (التشغيل الحي GATED_OWNER) | `fd3a4d3` إعداد `[telegram]`/`[ai]`؛ `7f40c1d` `wiring.py` يبني REAL/FAKE/DISABLED؛ شبكة حقيقية = `--allow-real-network` + `OSRS_EE_ALLOW_NETWORK=1` + allowlist + سر في البيئة وإلا `WiringError`؛ 7 اختبارات ضد خادم وهمي. **لم يُرسل أي طلب إلى Telegram/AI فعلي**؛ T02/T03/T35 في tests/target تحتاج مفاتيح المالك |
| CLI-02 | DONE_LOCAL | `b32222b`: `osrs-ee config-check` (ملخص منقّح + أوضاع المكوّنات)، `osrs-ee doctor` (REAL/SIMULATED/TARGET_ONLY/PRESENCE_ONLY/REAL_UNVERIFIED_LIVE، `ready_local`)، `service --allow-real-network`؛ 5 اختبارات |
| TEST-TARGET | DONE_LOCAL (التنفيذ NOT_RUN) | `f6d84c4`: `tests/target/` بوابات `OSRS_EE_TARGET=1`/`OSRS_EE_ALLOW_NETWORK=1`؛ T10/T30/T06/T31 عملية، S04b/T33 محوّل، T02/T03/T35 حية؛ 8 تُتخطى بصدق هنا؛ RUNBOOK §4 |
| TEST-FAIL | DONE_LOCAL | `95533ab`: `tests/test_failures.py` (11) — استعادة فقد طاقة محاكى، DB تالف/للقراءة فقط/مجلد غير قابل للكتابة، حدود RSS/FD/قرص، نقل تنبيهات فاشل محدود، `restart_budget=0`، حساب RECOVERY_REQUIRED لا يُلمس، canary مرفوض |
| CLEAN-ENV | DONE | `1daf93a`: استنساخ نظيف من bundle + venv جديد → كشف خطأ ترتيب استيراد `ssl` في conftest وأُصلح → 282 passed, 8 skipped؛ evidence/clean_env_2026-10-24.md |
| DOC-09 | DONE_LOCAL | `e42f52e` RUNBOOK (بوابة الجاهزية، opt-in، config-check/doctor، جدول المكوّنات المحلية غير المُثبتة، §4 tests/target) + هذا الـcommit: TASKS/ROADMAP/OUT_OF_SANDBOX (بدائل ADR-007/008 وتوصية فنية)/README/PROGRESS/bundles |
| S04b/S04c-target/S05 | GATED_OWNER + OUT_OF_SANDBOX | **المتبقي على الهدف فقط**: نقطة قراءة حقيقية + `ProcessSpec` لعميل حقيقي (ADR-007/008)، تشغيل `tests/target -m target`، pilot مراقب بإذن؛ الكود المحلي المساند جاهز (S04b-prep/SUP-02/TEST-TARGET)؛ ROADMAP |
| S06b/S07b/S08b-live | GATED_OWNER | الكود مكتمل محليًا ومربوط (WIRE-01)؛ المتبقي حصرًا: تشغيل حي بمفتاح Telegram/دردشة اختبار (T02/T03)، مفتاح AI اختياري (T35)، قياسات على OS الهدف (S08b) — بإذن صريح |
| S09 | DEFERRED | الاقتصاد/البيع/النقل بتفويض مستقل |

كل T01–T35 NOT_RUN على OSRS_ee حتى يُنفَّذ اختبار الهدف بدليل؛ V01–V08 REPORTED_UNVERIFIED؛ الاختبارات المحلية (282 تمر + 8 تُتخطى) تغطي منطق القرار والمكوّنات المحلية ضد عمليات/خوادم وهمية فقط ولا تُعد قبولًا للنظام — المصفوفة في docs/OUT_OF_SANDBOX.md §4.

## إعادة تدقيق TASKS (2026-10-24، بعد DOC-09) — ما الذي يمكن تنفيذه بعد بلا المالك؟
| بند | هل يمكن محليًا؟ | السبب |
|---|---|---|
| محوّل لعبة حقيقي / `ProcessSpec` لعميل | **لا** | يحتاج ADR-007 (OS/عميل) وADR-008 (مصدر الحالة/auth) وجهازًا بعميل مرخص؛ أي تنفيذ هنا سيكون تخمينًا غير قابل للاختبار |
| تشغيل T02/T03/T35 الحية | **لا** | تحتاج token/دردشة/مفتاح من المالك؛ الشبكة محجوبة بالتصميم؛ الكود والاختبارات جاهزة للتشغيل بأمر واحد (RUNBOOK §4) |
| V01–V08 | **لا** | تحتاج source revisions مثبتة وجهاز تحقق |
| daemon طويل العمر بلا `--max-ticks` | **لا (مرفوض عمدًا)** | قرار تصميم: لا تشغيل غير محدود قبل S04b على الهدف وإذن S05 |
| PUSH-02 / تحديث PR #1 | **لا** | يحتاج تفويض GitHub؛ مؤجل للنهاية بقرار المالك |
| تحسينات محلية إضافية (مزيد من الاختبارات، إعادة هيكلة) | ممكنة لكن **غير مطلوبة** | التغطية الحالية تغطي كل مسارات الفشل المحددة في التوجيه؛ إضافة كود بلا هدف حقيقي تزيد السطح دون دليل — تُؤجَّل إلى ما بعد قرارات المالك |
النتيجة: **لم يتبقَّ عمل قابل للتنفيذ محليًا بدليل**؛ كل المتبقي مُدرج أعلاه بسببه.

عند «تابع»: الاستئناف من آخر حزمة في evidence/bundles.md (التفويض لا يُطلب أثناء التطوير بقرار المالك)؛ وإلا من GitHub (`git clone` + checkout `genspark_ai_developer`) إن كان التفويض متاحًا، وإلا من آخر حزمة في PROGRESS (RESUME_PROTOCOL §1). كل عمل جديد: commit → push للفرع (أو bundle عند فقد التفويض) → تحديث PR #1 أو فتح PR جديد.
