# S06 — أدلة اختبارات Telegram (fake-first)

- التاريخ: 2026-10-23 (UTC) — sandbox؛ Python 3.13، pytest 9.0.3.
- الأمر: `python3 -m pytest tests -q` → **119 passed** (S01: 43، S02: 34، S03: 20، S06: 22).
- لا شبكة (محجوبة)؛ النقل عبر `FakeTransport` مكتوب السيناريو. لا bot token، لا chat حقيقي.

## الملفات
- `osrs_ee/telegram.py` — `AccessPolicy` (allow-lists صريحة للـ chat والمستخدم/الدور؛ default deny؛ مصفوفة أوامر→أدوار)، `Redactor` (canaries مسجلة + أنماط أسرار + استبدال account_id بالـ alias؛ `RedactionError`)، `Outbox` (محدود، dedupe، أولوية STATE/STOP قبل الإشعارات، retry محدود مع retry_after/backoff، dead-letter)، `ControlPlane` (رسائل: /status /stop /disable؛ /approve نصيًا مرفوض؛ callbacks مقيّدة تستهلك موافقة Store أحادية الاستخدام)، `FakeTransport`.
- `osrs_ee/store.py` — `Store.get_approval()` (قراءة فقط) + `ApprovalRow`.
- `tests/test_telegram.py` (22).

## ما تثبته الاختبارات (الأجزاء الخالصة من T02/T03/T29)
- **T03 (RBAC + موافقات مقيّدة):** مستخدم/chat خارج القوائم = IDENTITY_UNVERIFIED؛ VIEWER لا يوقف، OPERATOR لا يوافق، أمر مجهول مرفوض حتى للمالك؛ دور مجهول يُرفض عند البناء. الموافقة تُستهلك مرة واحدة عبر callback مقيّد فقط (incident/account/epoch/plan_hash/state_version + approver_ref مطابق لصف Store)؛ replay نفس الـ callback مرفوض؛ مستخدم خاطئ/دور خاطئ/approver مختلف/خطة متغيرة/نسخة متغيرة/منتهية/معرّف مجهول — كلها مرفوضة ولا تمس `used_at`. /approve نصيًا مرفوض حتى للمالك. كل قرار مسجّل في audit.
- **T02 (لا أسرار في sinks):** canary مسجّل لا يُعرض أبدًا (`RedactionError`)؛ أشكال الأسرار (ghp_/github_pat_/bot token/password=) تُرفض؛ account_id يُستبدل بالـ alias؛ الـ Outbox يرفض الرسالة قبل الطابور.
- **T29 (outbox محدود):** dedupe بالمفتاح؛ ترتيب الأولوية (STOP قبل INFO)؛ عند الامتلاء يُسقط الأدنى/الأحدث ولا يُسقط STATE لصالح INFO؛ retry_after يُحترم ولا محاولة أثناء backoff؛ المحاولات محدودة ثم dead-letter؛ فشل دائم يذهب dead فورًا؛ ميزانية flush تحد الإرسال.

## ما لا تثبته
- أي تكامل مع Telegram API الحقيقي (webhook/polling، التحقق من هوية المستخدم فعليًا، سلوك rate-limit الحقيقي)، ولا إدارة الـ bot token (يبقى ref فقط). T02/T03/T29 تبقى NOT_RUN كاختبارات قبول هدف. الربط بـ Supervisor (on_stop/on_disable) عبر callbacks فقط؛ لا تنفيذ على اللعبة.
