# S04b-prep + SUP-02 + WIRE-01 + CLI-02 + TEST-TARGET + TEST-FAIL — أدلة الاختبار المحلية

التاريخ: 2026-10-24 (UTC). البيئة: Python 3.13.14، pytest 9.1.1، SQLite 3.46.1، jsonschema 4.26.0، sandbox Linux بلا root (uid 1000)، `/tmp` tmpfs ≈ 493 MB (لذلك اختبارات الخدمة مع عملية حقيقية تضبط `disk_reserve_bytes = 0`). لا إنترنت، لا مفاتيح، لا عميل لعبة، لا JVM. كل ما يلي **كود حقيقي مُختبر محليًا** ولا يُعد قبولًا للنظام على الهدف.

## ما أُضيف (بترتيب الـcommits بعد `2763c2e`)
| commit | ملفات | اختبارات | ما يثبته محليًا | ما لا يثبته |
|---|---|---|---|---|
| `5c4716c` | `pyproject.toml` (packages: adapters/transports/providers)، `tests/test_packaging.py` | 2 | كل مجلد حزمة مُعلن؛ تثبيت غير editable لا يفقد الحزم الفرعية (الخطأ وُجد فعليًا في venv نظيف) | — |
| `d47eebb` | `osrs_ee/adapters/loopback_readonly.py`، `osrs_ee/measure.py`، `osrs_ee/egress.py`، `tests/test_s04b_prep.py` | 15 | endpoint loopback فقط (regex)؛ `observe()` GET `/observe` بحدود حجم/مهلة/انحراف زمني؛ أخطاء صادقة في `last_error` (http N / network / too large / unparseable / contract / honesty)؛ `dispatch()` دائمًا `NEVER_DISPATCH` (`NOT_SENT`/`POLICY_DENIED`) حتى لأمر صالح؛ `measure()` يعيد None بصدق بلا /proc؛ egress allowlist `host:port[:purpose]` + loopback افتراضي + `guarded_opener` يرفع `EgressDenied` قبل `connect()` ويسجّل الجرد | وجود نقطة قراءة حقيقية (ADR-008)؛ OS الهدف |
| `1ff58e7` | `osrs_ee/service.py`، `osrs_ee/config.py` (`health.ready_timeout_seconds`)، `osrs_ee/worker.py`، `tests/test_service.py::Readiness` | 5 | `LEASED→STARTING` قبل `sup.start`؛ `STARTING→RUNNING` فقط عند `sup.ready()`؛ انقضاء المهلة → `RECOVERY_REQUIRED` بسبب `start.timeout`؛ خروج أثناء البدء → `start.exited`؛ لا إعادة محاولة تلقائية لبدء فاشل | جاهزية عميل حقيقي |
| `e68c75e` | `osrs_ee/supervisor.py` (`ProcessSpec`/`ProcessSupervisor`)، `measure.host_measurer`، `Service(host_measure=)`، `tests/test_process_supervisor.py` | 11 | عملية ابنة python حقيقية: `start_new_session`، جاهزية = وجود ready_file، tick من أول سطر، SIGTERM→مهلة→SIGKILL مع تسجيل الطريقة، دليل خروج (`poll()`)، قياس RSS/FD من /proc، spec يرفض argv[0] غير مطلق/غير موجود؛ الخدمة الكاملة مع هذا المشرف: بدء→جاهزية→RUNNING→إيقاف منظم→RESTING، وانهيار العملية → RECOVERY_REQUIRED | JVM/GUI (ADR-007) |
| `fd3a4d3` | `osrs_ee/config.py` (`[telegram]` حقول النقل، `[ai]` جديد)، `config.example.toml`، `tests/test_config.py` | +config | حدود/مضيفين/مراجع `ref:` فقط؛ `enabled=true` بلا `*_ref` مرفوض | — |
| `7f40c1d` | `osrs_ee/wiring.py`، `tests/test_wiring.py` | 7 | FAKE/DISABLED افتراضيًا؛ REAL غير loopback يتطلب **4 شروط** (opt-in برمجي + `OSRS_EE_ALLOW_NETWORK=1` + المضيف في allowlist + السر في البيئة) وإلا `WiringError`؛ مع خادم وهمي loopback تُبنى المكوّنات الحقيقية وتعمل عبر الفاتح المحروس | صلاحية token/مفتاح حقيقي |
| `b32222b` | `osrs_ee/cli.py` (`config-check`, `doctor`, `service --allow-real-network`)، `tests/test_cli.py::CLIWire01` | 5 | ملخص منقّح (الأسرار كوجود/غياب فقط)، جدول المكوّنات، أنواع فحوص doctor، رفض `telegram.enabled=true` بلا opt-in برسالة تذكر `--allow-real-network` | — |
| `f6d84c4` | `tests/target/` (conftest + 3 ملفات) | 8 (skipped) | التخطي الصادق مع سبب واضح؛ البوابات بيئية فقط؛ `iter_markers()` لتمييز `live` عن `target` | **كلها NOT_RUN** حتى الهدف/المفاتيح |
| `95533ab` | `tests/test_failures.py` | 11 | استعادة بعد «فقد طاقة» محاكى (in-flight → UNKNOWN + RECOVERY_REQUIRED)؛ ملف DB تالف مرفوض؛ مجلد غير قابل للكتابة/DB للقراءة فقط → فشل مغلق؛ RSS فوق الحد → رفض قبول + تنبيه؛ FD فوق الحد → لا بدء جديد (لا يوقف جلسة جارية بالتصميم)؛ ضغط قرص → إيقاف؛ نقل تنبيهات فاشل لا يعطّل الحلقة ومحدود؛ `restart_budget=0`؛ حساب RECOVERY_REQUIRED لا يُلمس؛ canary في التنبيه مرفوض | فقد طاقة فعلي على OS الهدف |
| `1daf93a` | `tests/conftest.py`، `evidence/clean_env_2026-10-24.md` | — | إصلاح خطأ حقيقي وُجد فقط في venv نظيف (ترتيب استيراد `ssl`) | — |

## النتيجة
`python3 -m pytest tests -p no:cacheprovider` → **282 passed, 8 skipped** (226 + 2 + 15 + 5 + 11 + config + 7 + 5 + 11؛ المتخطاة = tests/target). نفس النتيجة من استنساخ نظيف للحزمة في venv جديد (`evidence/clean_env_2026-10-24.md`).

## الأوامر التي تم التحقق منها يدويًا
- `osrs-ee config-check --config config.example.toml` → `"mode": "SIMULATED"`، المكوّنات `FAKE`/`DISABLED`/`LOOPBACK_ONLY`، exit 0.
- `osrs-ee doctor --config config.example.toml` → `ready_local: false` في sandbox بسبب DISPLAY (TARGET_ONLY) والقرص دون الاحتياطي (REAL) — حقائق المضيف لا أخطاء كود.
- `osrs-ee service --config config.example.toml --max-ticks 20 --fast` → جلسة محاكاة كاملة، `"components"` و`"egress_denied": []`.
