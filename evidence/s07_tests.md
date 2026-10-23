# S07 — أدلة اختبارات AI advisory (fake-first)

- التاريخ: 2026-10-23 (UTC) — sandbox؛ Python 3.13، pytest 9.0.3.
- الأمر: `python3 -m pytest tests -q` → **133 passed** (S01: 43، S02: 34، S03: 20، S06: 22، S07: 14).
- لا شبكة؛ المزوّد `FakeProvider` مكتوب السيناريو. لا مفاتيح API، لا نموذج حقيقي.

## الملفات
- `osrs_ee/advisor.py` — `Advisor.advise()` بوابات مرتبة: consent → ارتباط الملاحظة بالسياق الحي (account/epoch) → عمر الملاحظة → تنقيح (`redact_observation`: حقول مرئية محددة فقط، alias بدل account_id، إزالة source، فحص canary/أسرار) → سقف حجم الـ prompt → ميزانية (عالمية calls/bytes + سقف لكل incident) → نداء بمهلة → تحليل صارم (`loads_strict`) → `require_valid("AIProposal")` → مطابقة incident → `check_ai_proposal_context` → فحص أسرار في diagnosis. `Budget`، `AdvisorConfig`، `Advice`، `FakeProvider`، `ProviderTimeout`.
- `tests/test_advisor.py` (14).

## ما تثبته الاختبارات (قواعد AI في FOUNDATION؛ أجزاء خالصة)
- **لا بيانات بلا consent؛ ولا نداء للمزوّد** عند أي رفض مبكر (consent/ارتباط/عمر/حجم/canary).
- **التنقيح:** الـ prompt يحوي alias فقط ولا account_id، لا حقول غير مرئية (varp.*)، لا source؛ canary في الملاحظة يمنع النداء كليًا.
- **الحدود:** سقف حجم، ميزانية عالمية (calls/bytes)، سقف لكل incident؛ timeout = DEADLINE_EXCEEDED، خطأ مزوّد = CAPABILITY_UNKNOWN — رفض لا فعل.
- **المخرجات AIProposal فقط، لا سلطة تنفيذ:** `parameters` غير فارغة / `requires_human_approval=false` / فعل مخترع → مرفوضة بالعقد؛ نص حقن ("ignore previous instructions…") غير قابل للتحليل → مرفوض؛ JSON بمفاتيح مكررة أو غير كائن → مرفوض؛ نسخة حالة قديمة أو incident مختلف → STALE_CONTEXT؛ سر في diagnosis → مرفوض. المقبول يبقى `requires_human_approval=true` و`parameters={}` ويُسجَّل في audit؛ لا شيء يُنفَّذ.

## ما لا تثبته
- جودة أي نموذج حقيقي، سلوك API حقيقي، أو تكلفة فعلية. لا تحمي من تسريب عبر قنوات خارج `Redactor`. الربط بالموافقة البشرية يمر عبر S06 (callbacks مقيّدة) وStore؛ لا تنفيذ على اللعبة في أي مسار.
