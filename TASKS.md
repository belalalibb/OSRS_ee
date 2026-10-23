# المهام الحالية

| ID | الحالة | المخرج / بوابة الإغلاق |
|---|---|---|
| DOC-01 | RECOVERED_FROM_RECORD | مصادر وبصمات وأدلة تاريخية موثقة؛ لم يُعد تدقيق upstream |
| DOC-02 | DONE_LOCAL | FOUNDATION موحدة: 35 قضية و35 اختبارًا مقترحًا وcrosswalk لـ29F و13R1 و16R2 والعقود والقرارات والخطة |
| DOC-03 | VALIDATED_LOCAL | فحص التغطية/JSON/أنماط الأسرار/ignore؛ evidence/validation.json |
| DOC-04 | DONE_LOCAL | RESUME_PROTOCOL 0.3 + ADR-013 + سجل الحزم؛ مسار الحفظ مختبر على مستودع تجريبي |
| SAVE-xx | RECURRING | بعد كل شريحة: commit → tests → bundle → verify+sha256 → رفع → تسجيل في PROGRESS/evidence/bundles.md |
| AUTH-01 | PARTIAL | OAuth أُعيد بنجاح 2026-10-23 (تفويض واحد، استُخدم للنشر فقط). إبطال المفتاحين المكشوفين: NOT_CONFIRMED من المالك |
| PUB-01 | SUPERSEDED | «نشر الأساس قبل الكود» أُلغي بقرار المالك؛ انظر PUB-02 |
| PUB-02 | DONE 2026-10-23 | remote كان فارغًا (isEmpty=true، فُحص قبل أي push)؛ push عادي: `main`=`3740096f`، `genspark_ai_developer`=`790ec2e`؛ PR #1 https://github.com/belalalibb/OSRS_ee/pull/1 (20 commits)؛ تحقق من clone جديد: شجرة `3b091a89…` مطابقة، 91 ملفًا، 156 اختبارًا تمر من الـ clone |
| VERIFY-01 | BLOCKED_AUTH | V01–V08 عند source revisions مثبتة؛ تسبق التكاملات المتأثرة لا pure contracts |
| DEC-STORE | DECIDED | ADR-003 = SQLite (قرار المالك 2026-10-23) |
| DEC-OS/AUTH | OPEN | ADR-007/008 قبل process/GUI/auth integration |
| S01 | DONE_LOCAL | 5 عقود JSON Schema 2020-12 + validator صارم + canonical hashing + guards خالصة؛ 48 fixtures؛ 43 اختبارًا offline تمر (evidence/s01_tests.md) |
| S02 | DONE_LOCAL | Store SQLite: accounts/sessions/leases/commands/events/approvals + journal + dedupe + recovery؛ اختبارات T04/T07/T08/T09 الخالصة مع persistent fake |
| S03 | DONE_LOCAL | worker/scheduler + fake adapter + cancellation + health (الأجزاء الخالصة من T16/T17/T21/T29) فوق Store؛ concurrency=1؛ لا game I/O؛ 20 اختبارًا (evidence/s03_tests.md) |
| S04/S05 | GATED_OWNER + OUT_OF_SANDBOX | read-only target ثم pilot مراقب؛ تحتاج JVM/GUI/عميل على جهاز المالك |
| S06 | DONE_LOCAL | Telegram fake-first: RBAC default-deny، redaction/canary، outbox محدود، approval callbacks مقيّدة (T02/T03/T29 الخالصة)؛ 22 اختبارًا (evidence/s06_tests.md) |
| S07 | DONE_LOCAL | AI advisory fake-first: consent/redaction/حدود حجم-عمر-ميزانية-مهلة، مخرجات AIProposal فقط بلا سلطة تنفيذ، الحقن لا يمنح سلطة؛ 14 اختبارًا (evidence/s07_tests.md) |
| S08 | DONE_LOCAL | registry quarantine، manifest ثابت + خط إصدار صارم مع rollback متوافق أو STOP، كاش محدود بلا مسارات هوية، admission بقياس/احتياطي، سياسة شبكة بلا fallback محظور (T14/T15/T18/T19/T32 الخالصة)؛ 23 اختبارًا (evidence/s08_tests.md)؛ canary حي غير مُنمذج |
| OOS-01 | DONE_LOCAL | docs/OUT_OF_SANDBOX.md: القرارات المفتوحة، V01–V08، S04/S05، مصفوفة T01–T35، متطلبات النشر |
| FINAL-01 | DONE_LOCAL_AND_PUBLISHED | كل الشرائح الممكنة محليًا منجزة ومنشورة على الفرع + PR #1. المتبقي يخص المالك: مراجعة/دمج PR، إبطال المفاتيح، ADR-007/008، S04/S05 على جهاز حقيقي |
| S09 | DEFERRED | الاقتصاد/البيع/النقل بتفويض مستقل |

كل T01–T35 NOT_RUN على OSRS_ee حتى يُنفَّذ اختبار الهدف بدليل؛ الاختبارات المحلية (156) تغطي منطق القرار الخالص فقط — المصفوفة في docs/OUT_OF_SANDBOX.md §4.

عند «تابع»: الاستئناف من GitHub (`git clone` + checkout `genspark_ai_developer`) إن كان التفويض متاحًا، وإلا من آخر حزمة في PROGRESS (RESUME_PROTOCOL §1). كل عمل جديد: commit → push للفرع (أو bundle عند فقد التفويض) → تحديث PR #1 أو فتح PR جديد.
