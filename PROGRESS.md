# نقطة الاستئناف — OSRS_ee

الحالة: PUBLISHED_TO_BRANCH / PR_OPEN / LOCAL_AHEAD. `genspark_ai_developer` على GitHub = `6552b84`؛ محليًا/في آخر حزمة: `6552b84` → `7a63ebc` (تغليف + CLI) → `dc51bea` (RUNBOOK/ROADMAP) → تصحيح الوثائق (هذا الـcommit) **غير مدفوعة بعد** لفقد التفويض؛ `main` = `3740096f` (لم يُدمج بعد؛ PR #1 بانتظار المالك). 161 اختبارًا offline تمر محليًا (منطق قرار فقط؛ ليست قبول نظام). الوجهة النهائية الوحيدة https://github.com/belalalibb/OSRS_ee.git، الفرع `main`. لا تطبيق شُغّل على حسابات حقيقية، لا Web deployment.

## مصدر الاستئناف الأساسي (2026-10-23 فصاعدًا)

`git clone https://github.com/belalalibb/OSRS_ee.git && git checkout genspark_ai_developer` → `pip install -e ".[dev]"` → `python -m pytest` (توقع 161 عند آخر حزمة؛ الـremote عند `6552b84` يعطي 156 حتى يُدفع التحديث). PR: https://github.com/belalalibb/OSRS_ee/pull/1. **قاعدة الترتيب:** قارن SHA الـremote بـSHA آخر حزمة أدناه؛ الأحدث هو مصدر الاستئناف، ولا تستبدل الأحدث بالأقدم.

## آخر حزمة استعادة (احتياطي)

| الحقل | القيمة |
|---|---|
| الرابط | https://www.genspark.ai/api/files/s/9aieKrdt (bundle d02، SHA-256 `08af7d5ce7c2536244876545e6c37f5ccaeedf53ddb5460945c01c415ad7fdb1`) — يُستبدل بـ d03 بعد commit هذا التصحيح (الصف الأعلى في evidence/bundles.md هو الأحدث دائمًا) |
| commit | `dc51bea` على `genspark_ai_developer` (161 اختبارًا تمر) |
| main | `3740096f31d4977b5d5705c4dd7208166208908c` (الأساس المعتمد) |
| احتياطي | حزمة التسليم الأصلية https://www.genspark.ai/api/files/s/Qmm5YBwM (`a973b8ec…`) |

سجل الحزم الكامل في `evidence/bundles.md`. الحزمة الأحدث تحتوي دائمًا سجل سابقاتها.

## حادثة فقد 2026-10-23 ~18:52

مُسحت مساحة العمل للمرة الخامسة قبل تحزيم S01؛ ضاع عمل S01 غير المحزّم (schemas/package/fixtures/tests كانت تمر 10/10) وcommit تسجيل الحزمة. القاعدة المشددة: **لا رد للمالك قبل رفع الحزمة**؛ الشرائح أصغر؛ bundle بعد كل ملف مجموعة مكتملة.

## حالة التفويض والنشر (محدّثة)

تفويض GitHub **متقطع**: نجح مرة واحدة 2026-10-23 (~21:30) واستُخدم لفحص الـremote (كان فارغًا) والدفع العادي وفتح PR #1 والتحقق من clone جديد، ثم أُبطل خلال دقائق؛ الجلسات اللاحقة أعادت `No Valid GitHub Authorization Found`. البروتوكول (RESUME_PROTOCOL 0.4): محاولة `setup_github_environment` واحدة في بداية كل جلسة؛ نجاح → استئناف من GitHub ودفع عادي بعد كل commit؛ فشل → حزم. المالك قرر عدم إعادة التفويض في كل مرحلة.

## العائق التاريخي (قبل 21:30)

GitHub OAuth لم يكن متاحًا للأدوات. SB-Git وAI Drive محجوبان بالخطة/غير مركّبين (ADR-013). **لا محاولة GitHub قبل النهاية وتأكيد المالك.** مفتاحان شخصيان نُشرا في المحادثة؛ لم يُستخدما؛ إلغاؤهما مطلوب وحالته NOT_CONFIRMED.

## ما حدث فعليًا (2026-10-23)

- استُعيد checkpoint `3740096f` أربع مرات بعد مسح مساحة العمل؛ كل مرة بتحقق كامل من ZIP/manifests/bundle.
- اختبار مسار الحفظ على مستودع تجريبي: bundle → رفع → حذف محلي → تنزيل → هاش مطابق → استعادة commit `e38fd045…` ناجحة.
- اعتُمد مسار الحفظ المحلي (ADR-013) وحُدّث RESUME_PROTOCOL 0.3 وTASKS. لم يُعد كتابة FOUNDATION أو التدقيق.

## الحالة التالية

S01 مكتملة محليًا (43 اختبارًا؛ evidence/s01_tests.md). S02 مكتملة محليًا (ADR-003 = SQLite؛ 34 اختبار Store؛ المجموع 77؛ evidence/s02_tests.md). S03 مكتملة محليًا (worker/scheduler/FakeAdapter/abort-drain/health؛ 20 اختبارًا؛ المجموع 97؛ evidence/s03_tests.md). S06 مكتملة محليًا (Telegram fake-first: RBAC/redaction/outbox/approval callbacks؛ 22 اختبارًا؛ المجموع 119؛ evidence/s06_tests.md). S07 مكتملة محليًا (AI advisory fake-first؛ 14 اختبارًا؛ المجموع 133؛ evidence/s07_tests.md). S08 مكتملة محليًا (registry/release/cache/admission/network؛ 23 اختبارًا؛ المجموع 156؛ evidence/s08_tests.md). التغليف/CLI (`7a63ebc`: pyproject + `osrs-ee` status/validate/store/demo؛ 5 اختبارات؛ المجموع 161). RUNBOOK/ROADMAP (`dc51bea`). تصحيح الوثائق (DOC-08). ما خارج الصندوق موثق في docs/OUT_OF_SANDBOX.md. **التالي القابل للتنفيذ بلا هدف:** S04a (ROADMAP) بعد دفع الحزمة/الفرع. PUB-02 منجز 2026-10-23: remote كان فارغًا؛ push عادي لـ main وgenspark_ai_developer؛ PR #1 مفتوح؛ تحقق من clone جديد (شجرة مطابقة، 156 اختبارًا). المتبقي للمالك: دمج PR، إبطال المفاتيح المكشوفة، قرارات ADR-007/008، S04/S05 على جهاز حقيقي.
