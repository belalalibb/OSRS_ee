# سجل حزم الاستعادة

كل صف: حزمة متحققة (`git bundle verify` + SHA-256) مرفوعة إلى رابط دائم. الصف الأحدث في الأعلى هو نقطة الاستئناف. الحزمة لا تحتوي بصمتها الذاتية؛ بصمتها تُسجل في الحزمة التالية وفي المحادثة.

| التاريخ UTC | commit (الفرع العامل) | SHA-256 للحزمة | الرابط | ملاحظة |
|---|---|---|---|---|
| 2026-10-23 19:05 | `4263f4e` (genspark_ai_developer) | `02d3419b688c2b749e038d80b738071d7f482b9083279a38d5ba7ec9611e48bd` | https://www.genspark.ai/api/files/s/yoCAYEEl | S01c: guard tests + evidence؛ 43 اختبارًا تمر؛ S01 DONE_LOCAL |
| 2026-10-23 18:57 | `b092883` (genspark_ai_developer) | `b333e5de36915413ce470c0a0af73965047b6a9fde8bf1958f010cc5b1325ded` | https://www.genspark.ai/api/files/s/WuwvZ5Bc | S01b: guards + 48 fixtures + harness؛ 16 اختبارًا |
| 2026-10-23 18:55 | `f8d2467` (genspark_ai_developer) | `f2efec96d94014ac64c3850856144e1350eb544c7b5ee32187ead3ea7e8df511` | https://www.genspark.ai/api/files/s/GUj06fMK | S01a: schemas + validator + canonical |
| 2026-10-23 18:50 | `17fa22765fd1125311477776b79349323ce3cab3` (genspark_ai_developer; main=`3740096f`) | `f949c09abfed2ba54b0eaccf1a21c582a74f4ecc8dd4f658986efe36420dd5ce` | https://www.genspark.ai/api/files/s/mcC7Qm4p | S00: RESUME_PROTOCOL 0.3 + ADR-013 + TASKS/PROGRESS. استُعيدت بنجاح بعد المسح الخامس |
| 2026-10-23 17:40 | `3740096f31d4977b5d5705c4dd7208166208908c` (main) | `a973b8ecad4ce71290341ccdbf59115286ccd1a8330fd3d325c8a613b24a342e` (ZIP التسليم؛ bundle داخله `585e37845f84a88c9d27871e2a86ae37dcdc97e7245f6270b066a487c0366802`) | https://www.genspark.ai/api/files/s/Wbh3j3VW | حزمة التسليم الأصلية؛ استُعيدت 4 مرات بنجاح |

## اختبار الآلية (مستودع تجريبي منفصل، 2026-10-23 18:39)

commit `e38fd045d5fa234af15512d06865de4a9ff9dedb` → bundle SHA-256 `56eeddb929335edb09a35c7dae11c38a33786ef7d48418071f5149fd5212cdea` → رفع → حذف كل الآثار المحلية → تنزيل → `sha256sum -c` OK → `git bundle verify` OK → clone → HEAD مطابق والمحتوى صحيح. طلب بلا جلسة يعيد 302 (الروابط تتطلب جلسة المالك).
