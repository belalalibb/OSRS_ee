# RUNBOOK — تثبيت وتشغيل OSRS_ee

آخر تحديث: 2026-10-24. هذا الدليل يفصل بين ثلاثة أوضاع ولا يخلط بينها:

| الوضع | ما هو | هل يعمل الآن؟ |
|---|---|---|
| **A. النواة المحلية** | عقود + Store SQLite + منطق worker/telegram/advisor/release + config/service/wiring + CLI + مشرف عمليات عام + قياس موارد + egress + محوّل قراءة loopback + نقل Telegram/مزوّد AI (كود) | **نعم** — 282 اختبارًا offline تمر + 8 تُتخطى بصدق (tests/target تحتاج هدفًا/مفاتيح)، تثبيت موثق أدناه ومُتحقق في نسخة نظيفة (`evidence/clean_env_2026-10-24.md`) |
| **B. المحاكاة المتكاملة** | نفس النواة مع محوّلات وهمية (FakeAdapter/FakeTransport/FakeProvider) في حلقة واحدة | **نعم** — `osrs-ee demo`؛ يثبت التوصيل لا سلوك اللعبة |
| **C. النظام المتكامل** | JVM + GUI + عميل اللعبة + Telegram حقيقي + مزوّد AI حقيقي | **لا** — محوّل اللعبة ونقطة القراءة على الهدف غير موجودين؛ Telegram/AI كود حقيقي لكنه **لم يُشغَّل حيًا قط** (انظر §3 و§4 وdocs/ROADMAP.md) |

لا يوجد أمر «تشغيل البوت». لم يُضف عمدًا لأن المكونات التي يحتاجها (S04b على الهدف/S05) لم تُنفَّذ. `osrs-ee service` يعمل في وضع SIMULATED افتراضيًا ويرفض أي شبكة حقيقية بلا opt-in صريح (§2.5).

---

## 1. التثبيت (الوضع A وB)

### المتطلبات
- Python **≥ 3.11** (مُختبر على 3.13.14). SQLite المدمج (مُختبر على 3.46.1).
- لا Java، لا عميل لعبة، لا مفاتيح، لا شبكة أثناء الاختبارات.
- الاعتمادية الوحيدة خارج stdlib: `jsonschema>=4.18,<5` (تجلب `referencing` و`jsonschema-specifications`). للتطوير: `pytest>=8`.

### الخطوات (Linux/macOS)
```bash
git clone https://github.com/belalalibb/OSRS_ee.git
cd OSRS_ee
git checkout genspark_ai_developer          # الفرع الذي يحمل النواة؛ main = الأساس الوثائقي فقط حتى دمج PR #1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"                       # يثبّت osrs-ee + jsonschema + pytest
```
Windows (PowerShell): `py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e ".[dev]"`.

بديل بلا تثبيت الحزمة: `pip install -r requirements-dev.txt` ثم استخدم `python -m osrs_ee.cli` بدل `osrs-ee`.

### التحقق من التثبيت
```bash
python -m pytest                              # المتوقع: 282 passed, 8 skipped (pyproject يضبط testpaths=tests؛ المتخطاة = tests/target)
osrs-ee config-check --config config.example.toml   # mode SIMULATED + جدول المكوّنات FAKE/DISABLED/LOOPBACK_ONLY
osrs-ee doctor --config config.example.toml         # فحوص البيئة بنوعها REAL/SIMULATED/TARGET_ONLY/PRESENCE_ONLY
osrs-ee status                                # JSON: إصدارات + حالة كل مكوّن (REAL / FAKE only / NOT IMPLEMENTED)
```
إذا ظهر `ModuleNotFoundError: jsonschema` فالبيئة الافتراضية غير مفعّلة. إذا فشل اختبار بسبب الشبكة فهذا متعمد: `tests/conftest.py` يحجب أي socket.

**تم التحقق فعليًا** (2026-10-24): استنساخ نظيف من bundle → venv جديد → `pip install -e ".[dev]"` → `osrs-ee config-check`/`doctor` يعملان → **282 passed, 8 skipped** من خارج مجلد المستودع. هذا الفحص كشف خطأً حقيقيًا (ترتيب استيراد `ssl` في `tests/conftest.py`) وأُصلح في `1daf93a` — التفاصيل في `evidence/clean_env_2026-10-24.md`.

---

## 2. تشغيل ما يعمل الآن

### 2.1 التحقق من وثائق العقود
```bash
osrs-ee validate CommandIntent contracts/fixtures/valid/CommandIntent/noop.json     # exit 0, "VALID"
osrs-ee validate ResultEvent some_event.json                                        # exit 2 + أسباب عند الفشل
cat doc.json | osrs-ee validate Observation -
```
العقود: SessionLaunch, Observation, CommandIntent, ResultEvent, AIProposal (`contracts/schemas/`).

### 2.2 المخزن المحلي
```bash
osrs-ee store init data/store.sqlite      # ينشئ/يفتح (WAL, FULL, FK) ويشغّل recovery؛ يطبع integrity
osrs-ee store show data/store.sqlite      # الحسابات، الإيجارات النشطة، عدّ مراحل اليومية
```
`data/` و`*.sqlite*` في `.gitignore`. لا تضع أسرارًا في الحسابات: `credential_ref` يجب أن يبدأ بـ `ref:` وإلا يُرفض.

### 2.3 الحلقة المحاكاة (الوضع B)
```bash
osrs-ee demo
```
ينشئ مخزنًا مؤقتًا، حسابًا، إيجارًا، يمرّر intent عبر Worker + FakeAdapter (PREPARED → DISPATCHING → VERIFIED)، يرسل رسالة عبر Outbox + FakeTransport، يطلب رأي Advisor + FakeProvider، ثم abort/drain → RESTING. الخرج يحمل `"mode": "SIMULATED ..."` دائمًا. **لا يلمس أي لعبة أو شبكة.**

### 2.4 أدوات S04a (تحضير الهدف؛ بلا عميل)
```bash
osrs-ee target-check [--client PATH] [--data-dir DIR] [--no-java-probe]   # جرد الجهاز؛ exit 2 مع قائمة «ينقص» حتى يكتمل D0؛ لا يشغّل شيئًا سوى `java -version`
osrs-ee conformance                      # مجموعة الامتثال C1–C7 على FakeAdapter المدمج (تثبت المجموعة لا العميل)
osrs-ee conformance --trace trace.jsonl  # المجموعة نفسها على أثر مسجّل
osrs-ee replay trace.jsonl               # إعادة تشغيل أثر JSONL منقّح عبر Worker على مخزن مؤقت
```
الأثر يُنتَج بلفّ أي adapter بـ`RecordingAdapter(TraceWriter(path, Redactor(aliases=...)))`؛ التنقيح إلزامي (معرّفات الحسابات → pseudonym، أي canary/سر → السجل لا يُكتب). الـadapter الحقيقي في S04b يجب أن يجتاز `run_conformance` نفسها قبل أي استخدام.

### 2.5 حلقة الخدمة المحاكاة (S04c-local؛ بلا عميل)
```bash
cp config.example.toml config.toml            # عدّل data_dir إن أردت؛ لا تضع أي سر — مراجع ref: فقط
osrs-ee service --config config.toml --max-ticks 20          # ينام tick_seconds بين الدورات
osrs-ee service --config config.toml --max-ticks 20 --fast   # بلا نوم (عروض/اختبارات)
osrs-ee store show data/store.sqlite
python -m osrs_ee status                                     # نفس نقطة الدخول إن لم يكن سكربت pip على PATH
```
**خدمة واحدة لكل `data_dir`** (SUP-04): عند البدء يُؤخذ قفل حصري `data_dir/service.lock` (`flock`؛ تُحرّره النواة عند موت الحامل فلا قفل عالق). خدمة ثانية على نفس المجلد → `REFUSED … One service per data_dir` exit 2 **قبل** لمس المخزن. امتلاك القفل هو الدليل أنه لا خدمة أخرى حيّة، لذا بعد `recover()` تُستدعى `reconcile_orphaned_sessions()`: أي حساب تُرك في LEASED/STARTING/RUNNING/DRAINING مع lease نشط (موت مفاجئ/SIGKILL/انقطاع كهرباء) → تحرير الـlease بسبب `orphan: service lock acquired` + `RECOVERY_REQUIRED` (لا READY أبدًا). الخرج يحمل `"orphaned_sessions_reconciled"` و`"lock"`.
يحمّل الإعدادات **fail-closed** (مفتاح مجهول/سر حرفي/حد خاطئ → `CONFIG REFUSED` exit 2)، يبني المكوّنات عبر `osrs_ee/wiring.py` (كل مكوّن يُعلن وضعه: `FAKE` / `DISABLED` / `LOOPBACK_ONLY` / `REAL`)، يفتح/يستعيد المخزن، يُهيئ الحساب إلى READY، ثم يدير جلسة واحدة: قبول بالموارد (قياس المضيف الفعلي عبر `measure.py` إن توفر `/proc`، وإلا لقطة محقونة) → `LEASED→STARTING` → `sup.start` → **بوابة الجاهزية** (`STARTING→RUNNING` فقط عند `sup.ready()`؛ انقضاء `health.ready_timeout_seconds` أو خروج العملية → `RECOVERY_REQUIRED` بسبب `start.timeout`/`start.exited`) → خطوات → إيقاف منظم (`abort → drain → stop`) → RESTING. يُثبّت الحالة في SQLite ويستأنف منها في التشغيل التالي (RESTING → READY → epoch جديد). الخرج يحمل `"mode"` و`"components"` و`"egress_denied"`.

**يرفض** (exit 2، بلا أي اتصال): `target.mode="device"` (لا محوّل لعبة حقيقي بعد؛ S04b على الهدف)؛ `telegram.enabled=true` أو `ai.enabled=true` بلا **كلٍّ من** `--allow-real-network` **و** متغيّر البيئة `OSRS_EE_ALLOW_NETWORK=1` **و** وجود المضيف في `allowed_hosts` **و** وجود السر المُشار إليه بـ`ref:env:NAME` في البيئة — أي شرط ناقص → `WiringError`؛ والتشغيل بلا حد (`--max-ticks` أو `[worker].max_ticks`). Ctrl-C/SIGTERM → `request_stop` → إيقاف منظم في الدورة التالية. الوضع الافتراضي SIMULATED ولا يمكن الانزلاق إلى REAL بالصدفة.

#### 2.5.1 فحوص قبل التشغيل
```bash
osrs-ee config-check --config config.toml     # يحمّل ويفحص الإعدادات، يطبع ملخصًا منقّحًا (المراجع ref: تُعرض كوجود/غياب فقط) + وضع كل مكوّن؛ exit 2 عند الرفض
osrs-ee doctor --config config.toml           # إصدارات Python/SQLite/jsonschema، /proc، قرص data_dir مقابل الاحتياطي، DISPLAY/java (TARGET_ONLY)، وجود أسرار ref:env (PRESENCE_ONLY)، ready_local
osrs-ee store init data/store.sqlite          # تهيئة/استعادة المخزن
osrs-ee conformance                           # C1–C7 على FakeAdapter؛ المحوّل الحقيقي يجب أن يجتازها على الهدف (tests/target)
osrs-ee secret-scan .                         # فحص أشكال الأسرار في الشجرة: يطبع path/line/pattern/length فقط — لا يطبع القيمة أبدًا؛ exit 2 عند أي نتيجة
osrs-ee secret-scan . --config config.toml    # + فحص صلاحيات data_dir/store/service.lock (POSIX: تحذير إن كانت مقروءة للمجموعة/الآخرين؛ SEC-04: الخدمة نفسها تنشئها 0700/0600 مهما كان umask، فالنتيجة المتوقعة permission_issues=[])
```
سطر يحمل كناري اصطناعيًا موثّقًا يُستثنى بعلامة مرئية `# secret-scan: allow`. الشجرة الحالية: 145 ملفًا، 0 نتائج (اختبار انحدار `test_repository_is_clean`).
دلالة أنواع فحوص `doctor`:
| النوع | المعنى |
|---|---|
| `REAL` | قياس فعلي على هذا المضيف الآن؛ فشله يجعل `ready_local=false` (exit 2) |
| `SIMULATED` | ما يُعرض ناتج محاكاة/حقن وليس قياسًا للهدف |
| `TARGET_ONLY` | لا معنى له إلا على جهاز الهدف (DISPLAY، java، عميل اللعبة)؛ لا يُحتسب فشلًا هنا |
| `PRESENCE_ONLY` | يُفحص وجود متغيّر البيئة فقط؛ لا تُقرأ قيمته ولا تُختبر صلاحيته |
| `REAL_UNVERIFIED_LIVE` | كود حقيقي مختبر ضد خادم وهمي محلي فقط؛ لم يُنفَّذ حيًا قط |

#### 2.5.2 مكوّنات محلية جاهزة لكن غير مُثبتة على الهدف
| المكوّن | الملف | ما يثبته الاختبار المحلي | ما لا يثبته |
|---|---|---|---|
| محوّل قراءة loopback | `osrs_ee/adapters/loopback_readonly.py` | GET `/observe` من `http://127.0.0.1:<port>` فقط، حدود الحجم/المهلة، رفض كل `dispatch()` (`NEVER_DISPATCH`)، أخطاء صادقة في `last_error` | وجود أي نقطة قراءة على الهدف (ADR-008) |
| مشرف عمليات عام | `osrs_ee/supervisor.py: ProcessSpec/ProcessSupervisor` | بدء عملية ابنة في session خاصة، جاهزية عبر ready_file، tick من ملف، **SIGTERM→مهلة→SIGKILL على مجموعة العملية كاملة (`killpg`؛ الحفيد يُقتل — SUP-03)**، دليل خروج، قياس /proc، **سجل الابن محدود بـ`log_max_bytes` (افتراضي 64 MiB: دوران إلى `.1` عند البدء + اقتطاع في المكان أثناء التشغيل — SUP-05)** — مُختبر بعملية python فقط على Linux | تشغيل JVM/GUI فعلي (ADR-007)؛ أي سلوك على Windows (مجموعات العمليات/`taskkill`) |
| قفل الخدمة | `osrs_ee/lock.py: ServiceLock` | `flock` حصري غير حاجب على `data_dir/service.lock`؛ رفض الازدواج؛ تحرير تلقائي عند موت الحامل؛ ملف pid للتشخيص فقط؛ الملف 0600 و`data_dir` 0700 والمخزن 0600 مع `-wal`/`-shm` (SEC-04، POSIX فقط، best-effort) | فرع `msvcrt.locking` على Windows (غير مُختبر هنا) |
| فحص أسرار | `osrs_ee/secret_scan.py` | نتائج وصفية فقط، استثناء `ref:`/placeholders، تخطّي .git/الثنائيات، فحص صلاحيات POSIX | أن غياب النتائج يعني غياب الأسرار (الفحص بالأشكال فقط) |
| قياس موارد | `osrs_ee/measure.py` | RSS/FD/قرص/CPU من `/proc` على Linux | OS الهدف إن لم يكن Linux مع /proc |
| سياسة egress | `osrs_ee/egress.py` | allowlist `host:port[:purpose]`، loopback مسموح افتراضيًا، `guarded_opener` يرفع `EgressDenied` قبل `connect()`، جرد كل قرار | أن النظام الحقيقي لا يملك مسارًا آخر للشبكة خارج هذا الفاتح |
| توصيل المكوّنات | `osrs_ee/wiring.py` | بناء Telegram/AI حقيقيين فقط بشروط opt-in الأربعة؛ وإلا FAKE/DISABLED | صلاحية أي token/مفتاح فعلي |

### 2.6 الاستخدام كمكتبة
```python
from osrs_ee.store import Store
from osrs_ee import worker, guards, contracts
```
واجهات `Adapter`/`Transport`/`Provider` هي Protocols في `worker.py`/`telegram.py`/`advisor.py`؛ أي تنفيذ حقيقي يجب أن يلتزم بها (انظر ROADMAP S04).

---

## 3. ما الحقيقي وما المحاكى وما المفقود

| المكوّن | الحالة | الملف | ملاحظة |
|---|---|---|---|
| عقود JSON Schema + validator صارم + canonical hash | **REAL** | `contracts/`, `osrs_ee/contracts.py`, `canonical.py` | offline كامل |
| Guards (سياق/طزاجة/نتيجة/AI) | **REAL** | `osrs_ee/guards.py` | خالص، ساعة محقونة |
| Store SQLite (آلة حالات، leases، journal، approvals، recovery) | **REAL** | `osrs_ee/store.py`, `store_schema.sql` | ملف محلي؛ متانة فقدان الطاقة على OS الهدف غير مُثبتة (ADR-007) |
| Worker/scheduler/abort/health | **REAL logic** | `osrs_ee/worker.py` | **المحوّل FAKE فقط** (`FakeAdapter`) |
| Telegram RBAC/redaction/outbox/approvals | **REAL logic** | `osrs_ee/telegram.py` | نقل حقيقي موجود في `osrs_ee/transports/` (urllib؛ token عبر `ref:env:` فقط) **مختبر ضد خادم وهمي محلي فقط**؛ غير مربوط بالخدمة بعد |
| AI advisory gates | **REAL logic** | `osrs_ee/advisor.py` | مزوّد حقيقي في `osrs_ee/providers/openai_compat.py` (urllib؛ مفتاح عبر `ref:env:`) **مختبر ضد خادم وهمي محلي فقط**؛ لم يُتصل بأي API فعلي |
| Registry/Release/Cache/Admission/NetworkPolicy | **REAL logic** | `osrs_ee/release.py` | القياسات محقونة؛ canary حي غير مُنمذج |
| Config TOML + Service loop + بوابة الجاهزية + Wiring | **REAL logic** | `osrs_ee/config.py`, `service.py`, `wiring.py` | الخدمة تعمل بـ`FakeSupervisor`+`FakeAdapter` افتراضيًا؛ وضع `device` مرفوض حتى يوجد محوّل لعبة |
| CLI (`validate`, `store`, `demo`, `target-check`, `conformance`, `replay`, `service`, `config-check`, `doctor`, `status`) | **REAL** | `osrs_ee/cli.py` | يعرض فقط ما هو موجود؛ `--allow-real-network` opt-in صريح |
| محوّل قراءة فقط عبر loopback | **REAL code, UNVERIFIED on target** | `osrs_ee/adapters/loopback_readonly.py` | مُختبر ضد خادم وهمي محلي؛ لا نقطة قراءة حقيقية موجودة (ADR-008) |
| مشرف عمليات عام (`ProcessSupervisor`) | **REAL code, UNVERIFIED with JVM/GUI** | `osrs_ee/supervisor.py` | مُختبر بعملية python ابنة؛ لم يُشغَّل JVM قط (ADR-007) |
| قياس موارد فعلي (`measure.py`) | **REAL (Linux /proc)** | `osrs_ee/measure.py` | يغذي قبول الجلسة في الخدمة؛ OS الهدف غير مُثبت |
| سياسة egress + فاتح محروس | **REAL** | `osrs_ee/egress.py` | يمنع أي اتصال خارج allowlist قبل `connect()` |
| Telegram transport حقيقي | **REAL code; live NOT_RUN** | `osrs_ee/transports/telegram_http.py` | ضد خادم وهمي محلي فقط؛ التشغيل الحي = T02/T03 في `tests/target/` تحتاج token (المالك) |
| AI provider حقيقي | **REAL code; live NOT_RUN** | `osrs_ee/providers/openai_compat.py` | ضد خادم وهمي محلي فقط؛ T35 تحتاج مفتاحًا (المالك)؛ استشاري فقط |
| **Game client adapter** (تنفيذ `Adapter` حقيقي على الهدف) | **MISSING** | — | S04b على الهدف؛ يحتاج ADR-007/008 + جهاز + نقطة قراءة |
| **تشغيل JVM/GUI فعلي** (ProcessSpec لعميل حقيقي، إشارات صحة من العميل) | **MISSING** | — | S04b؛ `ProcessSupervisor` جاهز لكن لا spec حقيقي |
| **خدمة daemon طويلة العمر** (بلا `--max-ticks`، مراقبة، إعادة تشغيل الخدمة نفسها) | **MISSING** | — | S05؛ مرفوض عمدًا حتى اكتمال S04b |

### الانتقال بين الأوضاع
- **A → B**: لا شيء مطلوب؛ `osrs-ee demo` موجود.
- **B → C**: يتطلب بالترتيب (1) قرار ADR-007 OS/toolchain، (2) قرار ADR-008 auth_mode بعد V05، (3) تنفيذ `Adapter` حقيقي read-only أولًا (S04b) على جهاز حقيقي مع تمرير `tests/target/` (T06/T10/T30/T31/T33؛ §4)، (4) `ProcessSpec` لعميل حقيقي عبر `ProcessSupervisor` الموجود، (5) pilot مراقب بحساب واحد بإذن صريح (S05). التفاصيل والملفات ومعايير القبول في `docs/ROADMAP.md`.

---

## 4. التحقق على الهدف والاختبارات الحية (`tests/target/`)

الاختبارات الموسومة `@pytest.mark.target` و`@pytest.mark.live` **تُتخطى بصدق** (8 skipped) ما لم تتوفر بوابات البيئة أدناه. لا تُشغَّل تلقائيًا ولا تُحتسب ناجحة. حالتها الرسمية **NOT_RUN** حتى تُنفَّذ على جهاز الهدف وتُحفظ أدلتها في `evidence/`.

| المتغيّر | يفعّل | ملاحظة |
|---|---|---|
| `OSRS_EE_TARGET=1` | اختبارات `target` | على جهاز الهدف فقط |
| `OSRS_EE_TARGET_CONFIG` | مسار config.toml للهدف | `target.mode` و`[process]` حقيقيان |
| `OSRS_EE_TARGET_READY_FILE` | ملف الجاهزية الذي يكتبه العميل/الغلاف | T10/T30 |
| `OSRS_EE_TARGET_ENDPOINT` | `http://127.0.0.1:<port>` لنقطة القراءة | T33 + امتثال S04b؛ **لا توجد بعد** (ADR-008) |
| `OSRS_EE_ALLOW_NETWORK=1` | اختبارات `live` + `--allow-real-network` | بدونه لا socket غير loopback |
| `OSRS_EE_TG_TOKEN`, `OSRS_EE_TG_CHAT_ID` | T02/T03 (Telegram حي) | يوفرها المالك؛ لا تُسجَّل |
| `OSRS_EE_AI_KEY`, `OSRS_EE_AI_BASE_URL`, `OSRS_EE_AI_MODEL` | T35 (مزوّد AI حي) | اختياري؛ استشاري فقط |

```bash
# على جهاز الهدف، بعد قرار ADR-007/008 وتوفير العميل ونقطة القراءة:
OSRS_EE_TARGET=1 OSRS_EE_TARGET_CONFIG=target.toml OSRS_EE_TARGET_READY_FILE=/run/osrs/ready \
OSRS_EE_TARGET_ENDPOINT=http://127.0.0.1:18080 python -m pytest tests/target -m target -rs
# الخدمات الحية (بإذن المالك وبمفاتيح من البيئة فقط):
OSRS_EE_ALLOW_NETWORK=1 OSRS_EE_TG_TOKEN=... OSRS_EE_TG_CHAT_ID=... python -m pytest tests/target -m live -rs
```
ما تثبته هذه الاختبارات عند تمريرها: T10 بدء/جاهزية عملية حقيقية، T30 إيقاف منظم مع دليل خروج، T06/T31 قياس وحدود على الهدف، T33 قراءة فقط عبر loopback بلا أي dispatch، T02/T03 إرسال/استقبال Telegram حقيقي مع تنقيح، T35 استدعاء مزوّد AI واحد محدود. إلى أن يحدث ذلك: V01–V08 تبقى REPORTED_UNVERIFIED وT01–T35 تبقى NOT_RUN.

---

## 5. حدود ثابتة (لا يغيّرها أي وضع)
لا حسابات حية دون إذن صريح ومرحلة S05؛ لا GE/بيع/نقل (S09 مؤجلة بتفويض مستقل)؛ لا تشغيل متعدد أو غير مراقب؛ AI استشاري فقط؛ لا spoofing/mutation؛ لا ادعاء anti-ban.

## 6. استكشاف الأخطاء
| العرض | السبب | الحل |
|---|---|---|
| `StoreError: unsupported schema_version` | ملف sqlite من إصدار آخر | لا ترقية تلقائية؛ `backup_to` ثم مخزن جديد |
| `LeaseConflict` عند `prepare_command` | intent غير مرتبط بالإيجار/epoch الحالي | هذا سلوك مقصود؛ أعد توليد intent من السياق الحي |
| الحساب `RECOVERY_REQUIRED` بعد الفتح | أوامر in-flight عند آخر إغلاق | مقصود؛ يتطلب `RECONCILING` يدويًا؛ لا يعود READY تلقائيًا |
| `RuntimeError: network forbidden` في الاختبارات | كود يحاول فتح socket | الاختبارات offline بالتصميم |
| `WiringError` عند `service` مع `telegram.enabled=true` | ينقص أحد شروط opt-in الأربعة | أضف `--allow-real-network` + `OSRS_EE_ALLOW_NETWORK=1` + المضيف في `allowed_hosts` + السر في البيئة؛ أو أبقِه `false` |
| الحساب `RECOVERY_REQUIRED` بسبب `start.timeout` | المشرف لم يُعلن الجاهزية خلال `health.ready_timeout_seconds` | راجع ready_file/سجل العملية؛ ارفع المهلة بحذر؛ لا يعود READY تلقائيًا |
| `doctor` يطبع `ready_local=false` بسبب القرص | المساحة الحرة في data_dir أقل من `limits.disk_reserve_bytes` | حرّر مساحة أو اضبط الاحتياطي؛ في sandbox الاختبارات تضبط 0 عمدًا |
| 8 اختبارات skipped | بوابات `tests/target` غير مفعّلة | مقصود؛ انظر §4 |
| `REFUSED: service lock … is held by another instance (pid N)` | خدمة أخرى تعمل على نفس `data_dir` | أوقفها أولًا؛ لا تحذف `service.lock` يدويًا (القفل بالنواة لا بالملف؛ ملف pid قديم بلا حامل لا يمنع البدء) |
| `orphaned_sessions_reconciled` غير فارغ و`state_before=RECOVERY_REQUIRED` | التشغيل السابق مات دون إيقاف منظم (SIGKILL/كهرباء) | مقصود؛ راجع `store show` وسجل العملية؛ تسوية يدوية RECONCILING → READY |
| `[osrs_ee] log truncated …` في سجل الابن | الابن تجاوز `log_max_bytes` | مقصود؛ ارفع الحد في `ProcessSpec` أو قلّل ثرثرة العميل؛ النسخة السابقة في `<log>.1` إن دارت عند البدء |
| `secret-scan --config` يبلّغ `permission_issues` على `data_dir`/`store.sqlite`/`service.lock` | أُنشئت الملفات بأداة خارجية أو بإصدار أقدم من `482a893` | شغّل `osrs-ee store init <path>` أو `service` مرة؛ يضيّقها تلقائيًا (أو `chmod 700 data_dir && chmod 600 data_dir/*`)؛ على Windows الفحص لا ينطبق |
| `secret-scan` exit 2 | شكل سري أو صلاحيات واسعة | افحص السطر المُشار إليه؛ إن كان كناري اصطناعيًا موثّقًا أضف `# secret-scan: allow`؛ أصلح الصلاحيات بـ`chmod 600/700` |
