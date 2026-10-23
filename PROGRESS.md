# نقطة الاستئناف — OSRS_ee

الحالة: PUBLISHED_TO_BRANCH / PR_OPEN. `genspark_ai_developer` على GitHub = HEAD المحلي؛ `main` = `3740096f` (لم يُدمج بعد؛ PR #1 بانتظار المالك). 156 اختبارًا offline تمر محليًا ومن clone جديد. الوجهة النهائية الوحيدة https://github.com/belalalibb/OSRS_ee.git، الفرع `main`. لا تطبيق شُغّل على حسابات حقيقية، لا Web deployment.

## مصدر الاستئناف الأساسي (2026-10-23 فصاعدًا)

`git clone https://github.com/belalalibb/OSRS_ee.git && git checkout genspark_ai_developer` → `python3 -m pytest tests -q` (توقع 156). PR: https://github.com/belalalibb/OSRS_ee/pull/1. الحزم أدناه احتياطي عند فقد التفويض.

## آخر حزمة استعادة (احتياطي)

| الحقل | القيمة |
|---|---|
| الرابط | https://www.genspark.ai/api/files/s/tQdN3gNF (bundle S08a، SHA-256 `f5690d891482423fcc4928f41efd6a4bccd8a0518c13a44e52b44ba2764f9a55`) |
| commit | `1ecb5f3` على `genspark_ai_developer` (156 اختبارًا تمر) |
| main | `3740096f31d4977b5d5705c4dd7208166208908c` (الأساس المعتمد) |
| احتياطي | حزمة التسليم الأصلية https://www.genspark.ai/api/files/s/Qmm5YBwM (`a973b8ec…`) |

سجل الحزم الكامل في `evidence/bundles.md`. الحزمة الأحدث تحتوي دائمًا سجل سابقاتها.

## حادثة فقد 2026-10-23 ~18:52

مُسحت مساحة العمل للمرة الخامسة قبل تحزيم S01؛ ضاع عمل S01 غير المحزّم (schemas/package/fixtures/tests كانت تمر 10/10) وcommit تسجيل الحزمة. القاعدة المشددة: **لا رد للمالك قبل رفع الحزمة**؛ الشرائح أصغر؛ bundle بعد كل ملف مجموعة مكتملة.

## العائق الثابت

GitHub OAuth غير متاح للأدوات (`No Valid GitHub Authorization Found` بعد ربط المالك). المالك قرر عدم إعادة التفويض في كل مرحلة. SB-Git وAI Drive محجوبان بالخطة/غير مركّبين (ADR-013). **لا محاولة GitHub قبل النهاية وتأكيد المالك.** مفتاحان شخصيان نُشرا في المحادثة؛ لم يُستخدما؛ إلغاؤهما مطلوب وحالته NOT_CONFIRMED.

## ما حدث فعليًا (2026-10-23)

- استُعيد checkpoint `3740096f` أربع مرات بعد مسح مساحة العمل؛ كل مرة بتحقق كامل من ZIP/manifests/bundle.
- اختبار مسار الحفظ على مستودع تجريبي: bundle → رفع → حذف محلي → تنزيل → هاش مطابق → استعادة commit `e38fd045…` ناجحة.
- اعتُمد مسار الحفظ المحلي (ADR-013) وحُدّث RESUME_PROTOCOL 0.3 وTASKS. لم يُعد كتابة FOUNDATION أو التدقيق.

## الحالة التالية

S01 مكتملة محليًا (43 اختبارًا؛ evidence/s01_tests.md). S02 مكتملة محليًا (ADR-003 = SQLite؛ 34 اختبار Store؛ المجموع 77؛ evidence/s02_tests.md). S03 مكتملة محليًا (worker/scheduler/FakeAdapter/abort-drain/health؛ 20 اختبارًا؛ المجموع 97؛ evidence/s03_tests.md). S06 مكتملة محليًا (Telegram fake-first: RBAC/redaction/outbox/approval callbacks؛ 22 اختبارًا؛ المجموع 119؛ evidence/s06_tests.md). S07 مكتملة محليًا (AI advisory fake-first؛ 14 اختبارًا؛ المجموع 133؛ evidence/s07_tests.md). S08 مكتملة محليًا (registry/release/cache/admission/network؛ 23 اختبارًا؛ المجموع 156؛ evidence/s08_tests.md). ما خارج الصندوق موثق في docs/OUT_OF_SANDBOX.md. PUB-02 منجز 2026-10-23: remote كان فارغًا؛ push عادي لـ main وgenspark_ai_developer؛ PR #1 مفتوح؛ تحقق من clone جديد (شجرة مطابقة، 156 اختبارًا). المتبقي للمالك: دمج PR، إبطال المفاتيح المكشوفة، قرارات ADR-007/008، S04/S05 على جهاز حقيقي.
