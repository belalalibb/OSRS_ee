# S03 — أدلة اختبارات worker/scheduler/fake adapter/cancellation/health

- التاريخ: 2026-10-23 (UTC) — sandbox؛ Python 3.13، pytest 9.0.3.
- الأمر: `python3 -m pytest tests -q` → **97 passed** (S01: 43، S02: 34، S03: 20).
- لا شبكة (محجوبة في `tests/conftest.py`)، لا threads، لا sleep؛ الساعة محقونة. لا game I/O، لا حسابات حية.

## الملفات
- `osrs_ee/worker.py` — `Worker` (حساب واحد/إيجار واحد/أمر واحد in-flight)، `WorkerConfig`، `StepResult`، `FakeAdapter` (سيناريو مكتوب: رد/None=timeout/Exception=انقطاع)، `HealthMonitor` (ticks مستقلة عن الحركة + ميزانية إعادة تشغيل = قاطع دائرة)، `AdapterResponse`.
- `tests/test_worker.py` (20).

## ما تثبته الاختبارات (الأجزاء الخالصة من T16/T17/T21/T29)
- **T21 (مالك واحد / Store هو نقطة الالتزام الوحيدة):** `start()` يمر عبر انتقالات CAS في Store (LEASED→STARTING→RUNNING)؛ `replan()` يُسقط فقط العمل غير المُدوَّن في اليومية ولا يمس ما التزم به Store؛ نفس الـ intent مرتين لا يُرسل مرتين؛ intent غير مرتبط بالإيجار يُسقط قبل أي تدوين.
- **T29 (حدود/لا إرسال دون intent):** طابور محدود (`INSUFFICIENT_RESOURCES`)؛ كل إرسال يسبقه صف PREPARED دائم ثم guards؛ رفض guard = حدث NOT_SENT ولا يصل المحوّل إطلاقًا (نسخة قديمة، ملاحظة قديمة، حقل UNKNOWN)؛ NOOP يُسمح به مع حقل UNKNOWN بينما الفعل يُرفض بـ `CAPABILITY_UNKNOWN`.
- **T16 (abort/drain):** بعد `mark_dispatching` أي فشل = UNKNOWN (timeout أو انقطاع المحوّل) وليس NOT_SENT أبدًا؛ أمر UNKNOWN معلّق يمنع الأفعال التالية حتى التسوية؛ `request_abort()` يغلق الطابور ويحوّل المعلّق إلى NOT_SENT/POLICY_DENIED دون إرسال؛ `drain()` يحرر الإيجار وينتهي RESTING فقط إذا لا UNKNOWN، وإلا RECOVERY_REQUIRED؛ إعادة فتح Store لا «تشفي» الحالة؛ `drain()` بلا abort مرفوض.
- **T17 (health):** لاعب ساكن مع ticks حية = OK وليس FROZEN؛ غياب ticks = FROZEN حتى لو «تحرك» الموضع؛ ميزانية إعادة التشغيل تفتح القاطع ويبقى مفتوحًا حتى تدخل المشغّل.

## ما لا تثبته
- أي سلوك لعميل حقيقي/JVM/عملية OS (S04/S05 خارج هذا الصندوق)، إشارات health الفعلية، أو أن abort «يوقف» فعلًا in-flight (بالتصميم لا يُسترجع). T16/T17/T21/T29 تبقى NOT_RUN كاختبارات قبول هدف.
