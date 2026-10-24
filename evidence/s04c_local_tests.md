# S04c-local — إعدادات TOML + حدود الإشراف + حلقة الخدمة (محاكاة فقط) — أدلة الاختبار

التاريخ: 2026-10-24 (UTC). البيئة: sandbox Linux x86_64، Python 3.13.14 (`tomllib` قياسي)، sqlite 3.46.1، pytest 9.x. لا شبكة (conftest يحجب socket).

## ما أُضيف
| ملف | المحتوى |
|---|---|
| `osrs_ee/config.py` | `ServiceConfig` مُنمَّط (target/worker/health/resources/network/telegram/account) يُحمَّل بـ `tomllib` **fail-closed**: مفاتيح/أقسام مجهولة = خطأ؛ أي قيمة حرفية بشكل سر (ghp_/token/password:/شكل توكن Telegram) تُرفض ومسموح فقط بمراجع `ref:...`؛ `config_hash` 64 hex؛ حدود رقمية لكل قيد؛ `mode="device"` يحتاج `client_path`؛ `auth_mode` مقفول على `UNKNOWN` حتى ADR-008؛ تفعيل Telegram يحتاج `bot_token_ref` + `chat_ids` |
| `config.example.toml` | مثال كامل بوضع `simulated` بلا أي سر |
| `osrs_ee/supervisor.py` | `Supervisor` Protocol (start/ready/tick/position/stop/exited/measure) + `FakeSupervisor` حتمي **لا يطلق أي عملية**؛ يحاكي: جاهزية متأخرة، تجمّد (tick لا يتقدم)، انهيار (exited بلا طلب إيقاف)، عدم إثبات خروج (`exit_on_stop=False`)، قياسات موارد |
| `osrs_ee/service.py` | `bootstrap_account` (NEW→…→READY، RESTING→READY، idempotent، **لا يلمس** RECOVERY_REQUIRED/BLOCKED/DISABLED/RECONCILING ولا حالات جلسة حية) + `Service` (ساعة محقونة): قبول الجلسة عبر `Admission` بلقطة موارد طازجة؛ `stop → abort → drain → supervisor.stop`؛ بلا إثبات خروج → RECOVERY_REQUIRED بسبب `supervisor.no_exit_proof`؛ أمر UNKNOWN → RECOVERY_REQUIRED بلا إعادة تشغيل؛ انهيار/تجمّد → إعادة تشغيل من RESTING فقط ضمن ميزانية `HealthMonitor` ثم `CIRCUIT_OPEN`؛ ضغط موارد أثناء التشغيل → إيقاف منظم (الحالة أولًا)؛ تنبيهات عبر `Redactor.render` وما يفشل التنقيح لا يُرسل أبدًا |
| `osrs_ee/cli.py` | أمر `service --config c.toml [--max-ticks N] [--fast]`: يقبل `mode="simulated"` فقط؛ يرفض `device` (لا مشرف/adapter حقيقي)، يرفض Telegram المفعّل (S06b غير منفذ)، يرفض التشغيل غير المحدود (لا تشغيل بلا رقابة) — exit 2 لكل رفض |
| `tests/test_config.py` (7)، `tests/test_service.py` (13)، `tests/test_cli.py` (+2) | |

## النتيجة
`python3 -m pytest tests -p no:cacheprovider` → **203 passed** (181 سابقًا + 22).

## ما تثبته هذه الاختبارات (وما لا تثبته)
- تثبت (محليًا، ضد Fakes): تحميل الإعدادات يرفض الأخطاء المطبعية والأسرار والحدود الخاطئة ووضع الجهاز الناقص؛ الحلقة تبدأ فقط من READY وبلقطة موارد مقبولة (قرص منخفض → لا بدء، `sup.starts == 0`)؛ تشغيل نظيف يُنفّذ NOOP إلى VERIFIED وينتهي RESTING مع تحرير الإيجار؛ طلب الإيقاف يُحترم قبل الخطوة التالية (الأوامر المصفوفة تُسقط دون تسجيل)؛ UNKNOWN أثناء الطيران → RECOVERY_REQUIRED بلا إعادة تشغيل حتى مع انهيار لاحق؛ عدم إثبات الخروج → RECOVERY_REQUIRED؛ انهيار متكرر مع ميزانية 2 → 3 بدايات ثم CIRCUIT_OPEN وكل READY بعد البدء سببه `service.restart` فقط؛ تجمّد يُكتشف من الـticks لا من الحركة؛ ضغط RSS أثناء التشغيل → إيقاف منظم بسبب `resources.pressure`؛ التنبيهات لا تحوي معرّف الحساب الخام بل alias، وcanary يمنع الإرسال؛ CLI يثبت الحالة في SQLite ويستأنف من RESTING إلى epoch 2 في تشغيل ثانٍ.
- لا تثبت: أي شيء عن عميل/JVM حقيقي، إشارات نظام فعلية تحت حمل، أو تجمّد/انهيار حقيقيين. S04b (المشرف الحقيقي وadapter الجهاز) غير منفذ؛ ADR-007/008 مفتوحان. T06/T10/T13/T16/T17/T18/T30/T31/T33/T34 تبقى NOT_RUN على هدف حقيقي.

## تشغيل يدوي موثّق (sandbox)
- `osrs-ee service --config c.toml --max-ticks 4 --fast` → `state_before: READY`, `final_state: RESTING`, `stop_reason: max_ticks`, events: `session.started epoch 1` → `session.settled max_ticks -> RESTING`. exit 0.
- تشغيل ثانٍ بنفس الـstore → `READY → RESTING`, epoch 2؛ `store show` يُظهر `state_version 14, session_epoch 2`, لا إيجارات نشطة.
- `mode="device"` + `client_path` → `REFUSED: target.mode='device' is not runnable …` exit 2.
- بلا `--max-ticks` ولا `[worker].max_ticks` → `REFUSED: … no unattended runs` exit 2.
