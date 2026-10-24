# RUNBOOK — تثبيت وتشغيل OSRS_ee

آخر تحديث: 2026-10-23. هذا الدليل يفصل بين ثلاثة أوضاع ولا يخلط بينها:

| الوضع | ما هو | هل يعمل الآن؟ |
|---|---|---|
| **A. النواة المحلية** | عقود + Store SQLite + منطق worker/telegram/advisor/release + config/service + CLI | **نعم** — 203 اختبارات offline، تثبيت موثق أدناه |
| **B. المحاكاة المتكاملة** | نفس النواة مع محوّلات وهمية (FakeAdapter/FakeTransport/FakeProvider) في حلقة واحدة | **نعم** — `osrs-ee demo`؛ يثبت التوصيل لا سلوك اللعبة |
| **C. النظام المتكامل** | JVM + GUI + عميل اللعبة + Telegram حقيقي + مزوّد AI حقيقي | **لا** — المكونات غير موجودة (انظر §3 وdocs/ROADMAP.md) |

لا يوجد أمر «تشغيل البوت». لم يُضف عمدًا لأن المكونات التي يحتاجها (S04/S05) لم تُنفَّذ.

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
python -m pytest                              # المتوقع: 203 passed (pyproject يضبط testpaths=tests)
osrs-ee status                                # JSON: إصدارات + حالة كل مكوّن (REAL / FAKE only / NOT IMPLEMENTED)
```
إذا ظهر `ModuleNotFoundError: jsonschema` فالبيئة الافتراضية غير مفعّلة. إذا فشل اختبار بسبب الشبكة فهذا متعمد: `tests/conftest.py` يحجب أي socket.

**تم التحقق فعليًا** (2026-10-23): venv جديد → `pip install -e ".[dev]"` → `osrs-ee status` يعمل → 161 اختبارًا تمر (181 بعد S04a؛ 203 بعد S04c-local) من خارج مجلد المستودع.

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
```
يحمّل الإعدادات **fail-closed** (مفتاح مجهول/سر حرفي/حد خاطئ → `CONFIG REFUSED` exit 2)، يفتح/يستعيد المخزن، يُهيئ الحساب إلى READY، ثم يدير جلسة واحدة بـ`FakeSupervisor` + `FakeAdapter`: قبول بالموارد → بدء → خطوات → إيقاف منظم (`abort → drain → stop`) → RESTING. يُثبّت الحالة في SQLite ويستأنف منها في التشغيل التالي (RESTING → READY → epoch جديد). الخرج يحمل `"mode": "SIMULATED ..."` دائمًا. **يرفض**: `target.mode="device"` (لا مشرف حقيقي؛ S04b)، `telegram.enabled=true` (S06b)، والتشغيل بلا حد (`--max-ticks` أو `[worker].max_ticks`). Ctrl-C/SIGTERM → `request_stop` → إيقاف منظم في الدورة التالية.

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
| Telegram RBAC/redaction/outbox/approvals | **REAL logic** | `osrs_ee/telegram.py` | **النقل FAKE فقط** (`FakeTransport`)؛ لا bot token |
| AI advisory gates | **REAL logic** | `osrs_ee/advisor.py` | **المزوّد FAKE فقط** (`FakeProvider`) |
| Registry/Release/Cache/Admission/NetworkPolicy | **REAL logic** | `osrs_ee/release.py` | القياسات محقونة؛ canary حي غير مُنمذج |
| Config TOML + Service loop + Supervisor boundary | **REAL logic** | `osrs_ee/config.py`, `service.py`, `supervisor.py` | **المشرف FAKE فقط** (`FakeSupervisor` لا يطلق أي عملية)؛ وضع `device` مرفوض |
| CLI | **REAL** | `osrs_ee/cli.py` | يعرض فقط ما هو موجود |
| **Game client adapter** (تنفيذ `Adapter` حقيقي) | **MISSING** | — | S04؛ يحتاج ADR-007/008 + جهاز |
| **JVM/GUI process supervisor** (owned processes, readiness, health signals فعلية) | **MISSING** | — | S04 |
| **Telegram transport حقيقي** | **MISSING** | — | S06b؛ بعد S04 |
| **AI provider حقيقي** | **MISSING** | — | S07b؛ اختياري |
| **قياس موارد فعلي** (`ResourceSnapshot` من OS) | **MISSING** | — | S04 |
| **خدمة تشغيل طويلة العمر** (daemon/loop/config) | **MISSING** | — | S05؛ بعد S04 |

### الانتقال بين الأوضاع
- **A → B**: لا شيء مطلوب؛ `osrs-ee demo` موجود.
- **B → C**: يتطلب بالترتيب (1) قرار ADR-007 OS/toolchain، (2) قرار ADR-008 auth_mode بعد V05، (3) تنفيذ `Adapter` حقيقي read-only أولًا (S04) على جهاز حقيقي مع تمرير T06/T10/T30/T31/T33، (4) supervisor عمليات، (5) pilot مراقب بحساب واحد بإذن صريح (S05). التفاصيل والملفات ومعايير القبول في `docs/ROADMAP.md`.

---

## 4. حدود ثابتة (لا يغيّرها أي وضع)
لا حسابات حية دون إذن صريح ومرحلة S05؛ لا GE/بيع/نقل (S09 مؤجلة بتفويض مستقل)؛ لا تشغيل متعدد أو غير مراقب؛ AI استشاري فقط؛ لا spoofing/mutation؛ لا ادعاء anti-ban.

## 5. استكشاف الأخطاء
| العرض | السبب | الحل |
|---|---|---|
| `StoreError: unsupported schema_version` | ملف sqlite من إصدار آخر | لا ترقية تلقائية؛ `backup_to` ثم مخزن جديد |
| `LeaseConflict` عند `prepare_command` | intent غير مرتبط بالإيجار/epoch الحالي | هذا سلوك مقصود؛ أعد توليد intent من السياق الحي |
| الحساب `RECOVERY_REQUIRED` بعد الفتح | أوامر in-flight عند آخر إغلاق | مقصود؛ يتطلب `RECONCILING` يدويًا؛ لا يعود READY تلقائيًا |
| `RuntimeError: network forbidden` في الاختبارات | كود يحاول فتح socket | الاختبارات offline بالتصميم |
