# S02 — أدلة اختبارات Store (SQLite)

- التاريخ: 2026-10-23 (UTC) — بيئة sandbox؛ Python 3.13، sqlite 3.46.1، pytest 9.0.3.
- القرار الحاكم: ADR-003 = SQLite (قرار المالك). ADR-013 مسار الحفظ المحلي.
- الأمر: `python3 -m pytest tests -q` → **77 passed** (S01: 43 + S02: 34).
- الشبكة محجوبة في الاختبارات (`tests/conftest.py`). لا حسابات حية، لا game I/O.

## الملفات
- `osrs_ee/store_schema.sql` — جداول schema_meta/accounts/leases/commands/events/approvals/transitions؛ فهرس جزئي «lease نشط واحد لكل حساب».
- `osrs_ee/store.py` — `Store.open` (WAL, synchronous=FULL, foreign_keys, busy_timeout؛ BEGIN IMMEDIATE)؛ آلة حالات CAS (`ALLOWED_TRANSITIONS`)؛ leases/epochs؛ command journal (PREPARED→DISPATCHING→…)؛ event dedupe؛ موافقات مقيّدة أحادية الاستخدام؛ `recover()`.
- `tests/test_store.py` (19) — دورة الحياة، آلة الحالات، الإيجارات، اليومية، التعافي بعد crash.
- `tests/test_store_events.py` (15) — الأحداث، الموافقات، حواف التعافي.

## ما تثبته الاختبارات (الأجزاء الخالصة/المحلية من T04/T07/T08/T09/T10/T12/T28)
1. فتح المخزن يفرض schema_version=1 وWAL ويرفض نسخة مخالفة؛ `integrity_check` سليم؛ `backup_to` ينتج نسخة مطابقة.
2. credential_ref يجب أن يكون مرجعًا (`ref:`) لا سرًا.
3. الانتقالات غير المسموحة تُرفض (`InvalidTransition`)؛ CAS على `state_version` (`VersionConflict`)؛ سجل transitions كامل.
4. lease نشط واحد لكل حساب؛ epoch يتزايد؛ TTL يُحترم؛ تحرير بـ epoch خاطئ يُرفض.
5. اليومية: PREPARED قبل أي إرسال؛ نفس المعرف + نفس الحمولة = idempotent؛ حمولة مختلفة = `IdempotencyConflict`؛ intent غير مرتبط بالإيجار/epoch الحالي = `LeaseConflict`.
6. الأحداث: dedupe بـ event_id؛ VERIFIED/FAILED_VERIFIED نهائية؛ TIMEOUT→UNKNOWN بلا finished_at ويُحسب في `unknown_pending`؛ UNKNOWN لا يُرقّى إلا بحدث VERIFIED/FAILED_VERIFIED؛ حدث ثانٍ نهائي يُرفض؛ epoch/session مخالف يُرفض؛ حدث مخالف للمخطط يُرفض قبل أي كتابة؛ NOT_SENT يُسجَّل بدون إرسال.
7. الموافقات: أحادية الاستخدام؛ مقيّدة بـ (incident, account, epoch, plan_hash, state_version)؛ انتهاء الصلاحية عند الإنشاء والاستهلاك؛ FK إلى حساب موجود.
8. التعافي: أوامر in-flight → UNKNOWN والحساب → RECOVERY_REQUIRED (لا READY أبدًا)؛ حالات الجلسة بلا lease → RECOVERY_REQUIRED؛ READY/RESTING لهما حافة مباشرة إلى RECOVERY_REQUIRED (إصلاح S02c؛ FOUNDATION §5 محدَّث).

## ما لا تثبته
- متانة فقدان الطاقة على نظام التشغيل الهدف (ADR-007 مفتوح)؛ التزامن بين عمليات متعددة فعلية؛ أي سلوك للعبة. T01–T35 تبقى NOT_RUN كاختبارات قبول هدف.
