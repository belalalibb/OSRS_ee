# بروتوكول الاستئناف

«تابع» = استئناف أول مهمة مصرح بها غير مكتملة. فقد الاتصال ليس نجاحًا أوفشلًا.

1. اقرأ PROGRESS وTASKS وFOUNDATION،ثم افحص الملفات وgit status/log/diff والفرع. إذا اختفت الملفات،استعد آخر حزمة مسلّمة،لا تبدأ التدقيق من الصفر ولا تنشئ Hono template.
2. افحص مسارات الأرشيف وبصماته قبل الاستخراج؛لا traversal أوsymlink خارج workspace ولا overwrite فوق عمل أحدث. كل الملفات تحت /home/user/webapp/.
3. **آخر رد GitHub: Reconnect Required.** لا setup أوremote operations حتى يؤكد المالك أنه أتم Reconnect من إعداداتGitHub فيGenspark. عندها استخدم setup_github_environment؛الفشل يوقف العمليات البعيدة. لا تستخدم توكن المحادثة أو تطبع اعتمادًا ضمن origin.
4. بعد نجاح التفويض افحص origin والوجهة OSRS_ee والفرع الافتراضي والصلاحيات والتاريخ وfetch/ls-remote. فحص قديم وجد المستودع فارغًا لا يثبت حالته الآن. main الفرع المطلوب؛اختلاف default يحتاج تسوية واضحة.
5. إذا تقدم remote اقرأ محتواه واحفظ تعديلات المستخدم. لا force push/reset --hard/حذف تاريخ. عند تاريخين مستقلين احتفظ بالـcommit المحلي وانقل التغييرات على قاعدة remote المدروسة دون مسح التاريخ.
6. push مجهول النتيجة: قارن SHA قبل retry. تحقق من SHA البعيد وشجرة الملفات وقراءة README/PROGRESS/العقود عنده،لا نجاح HTTP فقط. سجل آخر SHA بعيد متحقق؛لا تضع SHA الملف داخل نفسه.
7. المصادر keyed by SHA-256؛duplicate delivery لا رأي مستقل. الفحوص التاريخية لا تسمى نتائج حالية. أعد الفحوص المتأثرة فقط بتغير أوفقد دليل لازم.
8. وحدة عمل: diff محدود،اختبارات/scan،checkpoint،مراجعة staged paths/content،commit،push عادي،تحقق بعيد. لا أسرار في logs أوartifacts،ولا git add . دون مراجعة.
9. احفظ ZIP مبكرًا من allowlist؛لا .git/config أو.research أوruntime data. git bundle من التاريخ المحلي المنقح يحفظ commits دون إعدادات الاعتماد. لا تفترض بقاء ملفات sandbox أوعملياتها بعد الانقطاع.
10. نهاية الجلسة تحدد خطوة واحدة وعائقًا وأدلة فعلية. لا READY للحساب بعد crash؛UNKNOWN يبقى حتىreconcile.

بوابة التنفيذ: نشر الأساس والتحقق أولًا،ثم S01 pure schemas/fixtures/tests تلقائيًا ضمن التفويض. storage/OS/auth المفتوحة لا تمنع pure contracts لكنها تمنع تكاملًا يفترضها. لا live accounts أوعمليات مالية أوتشغيل متعدد/غير مراقب.
