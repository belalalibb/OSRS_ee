# مقارنة هندسية قائمة على الأدلة: OSRS_ee (هذا المستودع) مقابل Engine-Docs

**تاريخ المراجعة:** 2026-10-28  
**المرجع:** `https://github.com/zizo0022sasa/Engine-Docs.git` فرع `main`  
**النسخة المدروسة:** HEAD `8eb3231` (39 commit). بدأت المراجعة على `b06ec3c` (28 commit) ثم تحرّك HEAD أثناء العمل إلى `8eb3231` (PR-12 → PR-16)؛ المصفوفة أدناه تشير إلى `8eb3231`.  
**نسختنا:** `genspark_ai_developer` من `0ecf40c` (قبل المراجعة) إلى الـcommits المذكورة في §6.

## 0. قواعد المراجعة (مُلزمة)

| القاعدة | التطبيق |
|---|---|
| **الرخصة** | Engine-Docs **لا يحتوي ملف LICENSE** (تحقّق: `ls LICENSE*` → لا شيء، عند `b06ec3c` و`8eb3231`). بلا رخصة صريحة لا يجوز نسخ كود حرفيًا. **كل ما أُخذ هو أفكار أُعيد تنفيذها بتصميم مختلف واختبارات مختلفة.** لا سطر كود منقول. |
| **لا ثقة في الادعاءات** | ادعاء README المرجع «38 اختباراً» أُعيد تشغيله فعليًا: `b06ec3c` → **38 passed in 5.37s**؛ `8eb3231` → **61 passed in 13.55s** (محلي، Python 3.13، stdlib فقط). هذا يثبت أن مجموعة اختباراته خضراء محليًا، **ولا يثبت** أي تشغيل حي (معظم اختباراته تستخدم `FakeGameAdapter`/HTTP وهمي كما عندنا). |
| **لا «أفضل» بلا دليل** | كل خانة «الفجوة/القرار» تستند إلى سطر كود أو اختبار أُعيد تشغيله أو سلوك أُعيد إنتاجه هنا. |
| **قواعد المالك** | أي ميزة تمسّ حسابات حية/تعدد حسابات/GE/إخفاء هوية/HWID/بروكسي جغرافي → **REJECT** بغضّ النظر عن جودة تنفيذها. |

## 1. مصفوفة الوظائف

| الوظيفة | تنفيذنا الحالي | تنفيذ Engine-Docs | الدليل من الكود والاختبارات | الفجوة أو العيب | القرار |
|---|---|---|---|---|---|
| **CLI / التثبيت** | `pyproject` setuptools، `packages` صريحة + `package-data` (`store_schema.sql`, contracts)؛ سكربت `osrs-ee`؛ تبعية `jsonschema`؛ اختبار `test_packaging` يضمن أن كل حزمة فرعية مُعلنة (اكتُشف نقص سابق في wheel). أوامر: `status validate store demo target-check conformance replay service config-check doctor` + **جديد** `secret-scan`؛ **جديد** `python -m osrs_ee`. | stdlib فقط (`dependencies = []`)، `packages.find include osrs_ee*`، `__main__.py`، أوامر: `doctor init ingest grant-operator telegram-check telegram-poll status reconcile plan-stagger plan-route simulate-pilot live-probe attach-bot`. | المرجع: `pyproject.toml` سطور 11–17، `osrs_ee/__main__.py`. نحن: `tests/test_packaging.py`, `tests/test_secret_scan.py::MainModule`. | كان ينقصنا `__main__.py` (فائدة فعلية على Windows حين لا يكون سكربت pip على PATH). أمر `ingest` عند المرجع يستورد **كلمات مرور حسابات** إلى ملف JSON — خارج قواعد المالك. | **IMPROVE (منفّذ)**: `osrs_ee/__main__.py` + اختبار. **REJECT**: `ingest`/`attach-bot`/`live-probe` (حسابات حية). |
| **التخزين والاستعادة** | SQLite WAL/`synchronous=FULL`/FK؛ جداول accounts/leases/commands/transitions/approvals؛ CAS على `state_version`؛ `Store.open()` يستدعي `recover()`: in-flight → UNKNOWN + RECOVERY_REQUIRED؛ حالة جلسة **بلا** lease → RECOVERY_REQUIRED. **جديد**: `reconcile_orphaned_sessions()` (حالة جلسة **مع** lease نشط → تحرير الـlease + RECOVERY_REQUIRED) يُستدعى فقط تحت قفل الخدمة. | `StateStore` 1378 سطرًا؛ `reconcile_on_boot`: أي حالة غير مغلقة **أو** lease نشط → RECOVERY_REQUIRED ويحذف `active_leases`؛ PR-16 أضاف `owner_pid` في `active_leases` و`is_process_alive(pid)` (ctypes على Windows). | المرجع: `state/store.py` 953–1031 (`reconcile_on_boot`), 1032–1120 (`reconcile_orphaned_leases`), 70–105 (`is_process_alive`). نحن: **أُعيد إنتاج العيب** قبل الإصلاح: RUNNING + lease نشط → `Store.open()` بعد ساعتين ⇒ `RUNNING`, lease نشط, `recover()==[]` (أي لا طريق للخروج إلا يدويًا). اختبار `tests/test_lock_and_orphans.py::OrphanedSessions::test_recover_alone_leaves_running_with_active_lease` يوثّق الحد. | **فجوة حقيقية عندنا** (مُصلحة). تصميم المرجع (pid مخزّن + فحص حياة) له عيب معروف: إعادة استخدام PID بعد إعادة التشغيل تعطي إيجابيًا كاذبًا، و`os.kill(pid,0)` يحتاج تفرعًا خاصًا لويندوز. | **REIMPLEMENT (منفّذ)** بدليل مختلف: قفل `flock` حصري على `data_dir/service.lock` (يُحرَّر بالنواة عند موت الحامل) = إثبات أنه لا خدمة أخرى حيّة؛ عندها فقط تُعامل الجلسات المفتوحة كأيتام. 9 اختبارات. |
| **إدارة العمليات / الإيقاف** | `ProcessSupervisor`: `start_new_session=True`، ready_file كإثبات جاهزية، SIGTERM→انتظار→SIGKILL، إثبات خروج `poll()`، قياس `/proc`. **قبل المراجعة**: الإشارة إلى الابن المباشر فقط. **جديد (SUP-03)**: `os.killpg` على مجموعة العملية في المسارين. | `ManagedProcessTree`: POSIX `killpg(SIGTERM)` → 0.5s → `killpg(SIGKILL)`؛ Windows `CREATE_NEW_PROCESS_GROUP` + `taskkill /F /T`؛ اختبار T16 يتحقق من موت الحفيد. | المرجع: `sandbox/process_runner.py` 72, 80–118؛ `tests/test_pr04…::test_t16_managed_process_tree_kills_parent_and_grandchild_without_orphans`. نحن: اختباران جديدان **فشلا قبل الإصلاح** («grandchild orphaned after SIGTERM/SIGKILL stop») ونجحا بعده: `tests/test_process_supervisor.py::ProcessTree`. | **فجوة حقيقية عندنا** (مُصلحة): كان الحفيد يُيتَّم. عيب في المرجع: الإصدار الأقدم استخدم `stdout=PIPE` بلا قارئ (خطر امتلاء الأنبوب وتجمّد الابن)؛ في `8eb3231` أصبح `DEVNULL` (سطر 92). نحن نستخدم ملف سجل منذ البداية. | **REIMPLEMENT (منفّذ)**. Windows: لم يُختبر هنا لأي من المشروعين؛ لا ندّعي دعمه (`@skipUnless(posix)`). |
| **حدود السجلات / الموارد** | قبول بالموارد (RSS/FD/CPU/قرص) و`must_stop`؛ **قبل المراجعة**: سجل الابن مُلحق بلا حد. **جديد (SUP-05)**: `ProcessSpec.log_max_bytes` (افتراضي 64 MiB، [64 KiB, 2 GiB])؛ دوران عند البدء إلى `.1`، واقتطاع في المكان أثناء التشغيل عبر `tick()`، `log_bytes` في القياس. | `LogQuotaGuardian`: حدود 4 MiB/حساب، 10 MiB core، 120 MiB triage، ميزانية كلية 500 MiB؛ `RotatingFileHandler` + فلتر تنقيح. | المرجع: `telemetry/log_guardian.py` 16–23, 72–94. نحن: `tests/test_process_supervisor.py::LogQuota` (5) بما فيها ابن ثرثار يثبت أن الملف يبقى محدودًا تحت `tick()`. | **فجوة حقيقية عندنا** (مُصلحة). ملاحظة فنية: دوران بإعادة التسمية **لا** يحدّ ملفًا يحتفظ الابن بوصفه مفتوحًا (O_APPEND)؛ لذلك اخترنا الاقتطاع في المكان. أرقام المرجع (500 MiB) مرتبطة بـ15 حسابًا — لا تنطبق علينا (حساب واحد). | **REIMPLEMENT (منفّذ)** بأسلوب مختلف. |
| **مراقبة الحالة / Adapter** | `Adapter` Protocol؛ `FakeAdapter`؛ `ReadOnlyAdapter` لا يستطيع dispatch (اختبار)؛ conformance + replay لتتبّع منقّح؛ `HealthMonitor` (ساكن ≠ مجمّد). | `MicrobotHttpAdapter` loopback فقط + `X-Agent-Token ≥16`، لكنه **يرسل** `POST /scripts/stop`, `/logout`, `/widgets/click`؛ `evaluate_watchdog` بأحكام HEALTHY_MOVING/…/CIRCUIT_BREAKER_TRIPPED. | المرجع: `sandbox/http_adapter.py` 13, 524, 528؛ `runtime/supervisor.py`. نحن: `tests/test_adapters.py`, `tests/test_worker.py`. | المرجع يطلق تشغيلًا حيًا فعليًا على عميل Microbot (PR-12.1 «live wire-verification») — خارج ADR-007/008 المفتوحين عند المالك ولا يمكن التحقق منه هنا. تصميمنا يفصل القراءة عن الإرسال صراحة. | **KEEP** تصميمنا. **REJECT** اعتماد نقطة نهاية حقيقية قبل قرار المالك. |
| **عزل الشبكة والبيانات** | `EgressPolicy` allowlist `host:port[:purpose]` + `guarded_opener` يرفع `EgressDenied` قبل الاتصال؛ REAL يتطلب `allow_real_network` **و** `OSRS_EE_ALLOW_NETWORK=1` **و** المضيف في القائمة **و** `ref:env`؛ لا اتصالات حقيقية في الاختبارات. | `LocalSocks5Sidecar` RFC1928/1929 fail-closed مع تدوير جغرافي؛ `SandboxProfileSeeder` + `build_isolated_jvm_command` تحقن `hwid.properties`/`-javaagent`/`spoofed-device-ids.properties`. | المرجع: `sandbox/seeder.py` 4, 34, 53؛ `network/socks5_sidecar.py`. نحن: `tests/test_wiring.py`, `tests/test_guards.py`. | ميزات المرجع هنا = **إخفاء هوية/بروكسي جغرافي/HWID** — محظورة صراحة بقواعد المالك مهما كانت جودتها. | **REJECT** (seeder/hwid/javaagent/SOCKS5-geo). **KEEP** سياسة الخروج عندنا. |
| **خزنة الأسرار والتدقيق** | أسرار عبر `ref:env:NAME` فقط؛ لا خزنة ملفات؛ `Redactor` يرفض الأشكال السرية والكناري عند أي مَخرج (Telegram)؛ `config-check`/`doctor` تطبع «presence» فقط. **جديد (SEC-03)**: `osrs-ee secret-scan` (بيانات وصفية فقط: path/line/pattern/length؛ `--config` يفحص صلاحيات data_dir/store/lock). | `LocalSecretVault` = JSON نصي صريح بصلاحية 0600 يضم **كلمات مرور حسابات**؛ `secret_scan.scan_path` بنتائج وصفية؛ `check_secret_file_permissions`. | المرجع: `security/vault.py` 134–141 (`json.dumps`… `chmod(0o600)`), `security/secret_scan.py`. نحن: `tests/test_secret_scan.py` (8) بما فيها اختبار انحدار «المستودع نظيف»؛ فحص فعلي: 144 ملفًا، 0 نتائج. | كان ينقصنا أمر فحص للمستودع. فكرة «لا تطبع القيمة المطابقة» صحيحة وأُخذت. خزنة JSON نصية لكلمات مرور حسابات = **REJECT** (قاعدة لا حسابات حية + ملف واحد يسرّب كل شيء). | **REIMPLEMENT (منفّذ)** للفحص؛ **REJECT** الخزنة. أثناء الفحص وُجدت 8 كناري اصطناعية في اختباراتنا (FAKE_/sk-FAKE/hunter2) وسُمِّت بعلامة مرئية `# secret-scan: allow`. |
| **Telegram / AI** | `Outbox` محدود + `FakeTransport`/HTTP حقيقي خلف البوابات؛ `Redactor` إلزامي؛ AI استشاري فقط (`advisor`) بحدود `max_bytes`؛ T02/T03/T35 الحية NOT_RUN. | `BoundedOutbox`/`TelegramGateway`؛ `build_live_bot_sender` يتطلب `token_rotation_confirmed`؛ PR-16 أضاف **استيراد حسابات عبر Telegram** مع RBAC. | المرجع: `telemetry/outbox_and_bot.py` 27–145, 358, 431. نحن: `tests/test_telegram*.py`, `tests/test_advisor.py`. | متكافئان في الفكرة (صندوق صادر محدود + تنقيح). استيراد حسابات عبر دردشة = خارج القواعد. | **KEEP**. **REJECT** استيراد الحسابات عبر Telegram. |
| **المهام / الموارد / الإصدارات** | حساب واحد، جلسة واحدة؛ `restart_budget` + نافذة؛ `ready_timeout`؛ `max_ticks` إلزامي (لا تشغيل غير محدود)؛ `measure.py` من `/proc`. | `RssCapacityCalculator` (ctypes Windows) + `StaggeredLaunchPlanner` (≥90s) + `MicrobreakCoordinator` + `GEOrderLedger` + Stronghold/Tutorial bots. | المرجع: `tasks/capacity_and_stagger.py`, `economy/ge_ledger.py`, `bots/*`. نحن: `tests/test_service.py`, `tests/test_failures.py`. | كل ذلك يفترض **تعدد حسابات/اقتصاد/أتمتة لعب** — خارج نطاقنا بقرار المالك (S09 DEFERRED). | **REJECT** (خارج النطاق). |
| **Runbook / الاستعادة** | `docs/RUNBOOK.md` (تشغيل، بوابات، استكشاف أخطاء)، `docs/RESUME_PROTOCOL.md`، `evidence/`، حزم git موقّعة SHA-256 بعد كل دفعة. | `docs/RESUME_PROTOCOL.md` (7 خطوات)، `كيفيه_الاستخدام_من_الالف_للياء.md`، `FIELD_TESTING_PROTOCOL.md`. | قراءة مباشرة للملفات. | دليل المرجع يصف خطوات Windows/Linux حية (بناء Microbot، Golden Cache، بروكسي) لا يمكن التحقق منها هنا وتخالف القواعد. فكرة «خطوات استئناف مرقّمة» موجودة عندنا أصلًا. | **KEEP**. تحديث RUNBOOK لدينا بالأوامر الجديدة (secret-scan، القفل، الأيتام، حد السجل). |
| **منع ازدواج الخدمة** | **قبل المراجعة**: لا شيء يمنع تشغيل `service` مرتين على نفس `data_dir` (SQLite busy_timeout فقط). **جديد (SUP-04)**: `ServiceLock` → `REFUSED` exit 2 قبل لمس المخزن. | `SingleSlotSupervisor` (فتحة واحدة في العملية) ولا قفل بين عمليات — يعتمد على `owner_pid`. | نحن: `tests/test_lock_and_orphans.py::ServiceCli::test_second_service_on_same_data_dir_is_refused_with_exit_2`. | **فجوة عندنا** (مُصلحة) و**فجوة عند المرجع** (لا قفل عبر العمليات). | **IMPROVE (منفّذ)**. |

## 2. ما لم يُعتمد من المرجع ولماذا (سجل الرفض)

| البند في Engine-Docs | السبب |
|---|---|
| `SandboxProfileSeeder` / `hwid.properties` / `-javaagent hwid_agent.jar` / `spoofed-device-ids.properties` | إخفاء هوية/HWID — محظور صراحة. |
| `LocalSocks5Sidecar` مع تدوير مناطق | بروكسي/تمويه جغرافي — محظور؛ ولا شبكة حقيقية في التطوير. |
| `launch-slot` / `attach-bot` / `live-probe` (تشغيل JVM حي بحقن اعتمادات نصية في env) | حسابات حية + ADR-007/008 قرار المالك. |
| `LocalSecretVault` JSON نصي + `ingest accounts.txt` + استيراد عبر Telegram | كلمات مرور حسابات في ملف؛ تخالف «لا أسرار إلا `ref:`». |
| `GEOrderLedger` / economy | S09 مؤجل بتفويض مستقل. |
| `RssCapacityCalculator`/`StaggeredLaunchPlanner`/`MicrobreakCoordinator` | تعدد حسابات. |
| `status` يقرأ `store._conn` مباشرة | كسر تغليف؛ لدينا `store show` عبر sqlite للقراءة فقط ونحتفظ به. |
| `owner_pid` + `is_process_alive` كدليل حياة | إعادة استخدام PID تعطي إيجابيًا كاذبًا؛ استبدلناه بقفل النواة. |
| تفرّعات Windows (`taskkill`, ctypes) | غير قابلة للاختبار هنا؛ لا ندّعي ما لا نختبره. |

## 3. ما اعتُمد (أفكارًا) وكيف أُعيد تنفيذه

| الفكرة | تنفيذنا | الاختبار الأحمر→الأخضر |
|---|---|---|
| قتل شجرة العملية | `ProcessSupervisor._signal_tree()` = `os.killpg(os.getpgid(pid), sig)` مع `ProcessLookupError` مبتلَع؛ كنس SIGKILL إن كان الابن خرج أصلًا | `ProcessTree` (3) — الاثنان الأولان فشلا قبل الإصلاح |
| تسوية الجلسات اليتيمة عند الإقلاع | `Store.reconcile_orphaned_sessions()` تحت `ServiceLock` فقط | `OrphanedSessions` (4) + `ServiceCli` (2) |
| فحص أسرار وصفي | `osrs_ee/secret_scan.py` + أمر CLI | `test_secret_scan.py` (8) |
| `python -m osrs_ee` | `osrs_ee/__main__.py` | `MainModule` (1) |
| حد حجم السجل | `ProcessSpec.log_max_bytes` + اقتطاع في المكان | `LogQuota` (5) |

## 4. عيوب رُصدت في المرجع (للتوثيق لا للتشهير)

1. `b06ec3c`: `stdout=subprocess.PIPE` بلا قارئ في `ManagedProcessTree` → ابن ثرثار يتجمّد عند امتلاء الأنبوب. (أُصلح لاحقًا إلى `DEVNULL` في `8eb3231` سطر 92.)
2. فترة سماح SIGTERM ثابتة 0.5s قبل SIGKILL — قصيرة لعميل JVM؛ عندنا `stop_grace_seconds` قابل للضبط [0.1, 300].
3. `reconcile_on_boot` يحذف صفوف `active_leases` بدل تحريرها بسبب → يفقد أثر التدقيق؛ نحن نحتفظ بالصف مع `released_at`/`release_reason`.
4. لا قفل بين العمليات؛ ازدواج التشغيل على نفس قاعدة البيانات ممكن.

## 5. ما لا يمكن التحقق منه هنا (للمشروعين)

- أي تشغيل حي لعميل لعبة/JVM/GUI، Telegram حقيقي، AI حقيقي: **TARGET_TEST_NOT_RUN / OWNER_ACTION_REQUIRED**.
- سلوك Windows (مجموعات العمليات، `msvcrt.locking`، صلاحيات الملفات): **TARGET_TEST_NOT_RUN**.
- اختبارات Engine-Docs الـ61: **LOCAL_VERIFIED** كنجاح محلي فقط.

## 6. سجل القرارات والـcommits

| القرار | Commit | الاختبارات بعده |
|---|---|---|
| SUP-03 قتل مجموعة العملية | `01d75d2` | 285 passed / 8 skipped |
| SUP-04 قفل الخدمة + تسوية الأيتام | `ebfa9d4` | 294 / 8 |
| SEC-03 secret-scan + `__main__` | `48619b2` | 302 / 8 |
| SUP-05 حد السجل | `28ab1ab` | 307 / 8 |
| COMPARE-01 هذه الوثيقة | `d63825d` | 307 / 8 |
| DOC-10 RUNBOOK/README + TASKS/PROGRESS | `07f8886`, `2f6e35c` | 307 / 8 |
| SEC-04 صلاحيات مالك فقط للمخزن/القفل/`data_dir` (اكتُشفت بفحص التسلم؛ لا يقابلها شيء في المرجع — `LocalSecretVault` هناك يضبط 0600 لملف الخزنة فقط ولا يلمس مجلد البيانات أو SQLite) | `482a893` | 309 / 8 |

كل ما سبق **LOCAL_VERIFIED** على Linux (sandbox)، Python 3.13؛ لا شيء منه يثبت سلوكًا على جهاز المالك.
