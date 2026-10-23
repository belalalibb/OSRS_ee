# المهام الحالية

| ID | الحالة | المخرج / بوابة الإغلاق |
|---|---|---|
| DOC-01 | RECOVERED_FROM_RECORD | مصادر وبصمات وأدلة تاريخية موثقة؛ لم يُعد تدقيق upstream |
| DOC-02 | DONE_LOCAL | FOUNDATION موحدة: 35 قضية و35 اختبارًا مقترحًا وcrosswalk لـ29F و13R1 و16R2 والعقود والقرارات والخطة |
| DOC-03 | VALIDATED_LOCAL | فحص التغطية/JSON/أنماط الأسرار/ignore؛ evidence/validation.json |
| DOC-04 | DONE_LOCAL | RESUME_PROTOCOL 0.3 + ADR-013 + سجل الحزم؛ مسار الحفظ مختبر على مستودع تجريبي |
| SAVE-xx | RECURRING | بعد كل شريحة: commit → tests → bundle → verify+sha256 → رفع → تسجيل في PROGRESS/evidence/bundles.md |
| AUTH-01 | DEFERRED_TO_END | المالك يلغي المفتاحين المكشوفين (NOT_CONFIRMED) ويعيد OAuth مرة واحدة عند النهاية |
| PUB-01 | SUPERSEDED | «نشر الأساس قبل الكود» أُلغي بقرار المالك؛ انظر PUB-02 |
| PUB-02 | DEFERRED_DOCUMENTED | بعد التفويض النهائي: فحص remote الحقيقي، حفظ أي عمل بعيد، push عادي للفرع، PR واحد إلى main، تحقق SHA/شجرة/محتوى. قيد «PR لكل تعديل» غير قابل للتلبية حاليًا لسبب خارجي؛ يُلبى دفعة واحدة |
| VERIFY-01 | BLOCKED_AUTH | V01–V08 عند source revisions مثبتة؛ تسبق التكاملات المتأثرة لا pure contracts |
| DEC-STORE | DECIDED | ADR-003 = SQLite (قرار المالك 2026-10-23) |
| DEC-OS/AUTH | OPEN | ADR-007/008 قبل process/GUI/auth integration |
| S01 | DONE_LOCAL | 5 عقود JSON Schema 2020-12 + validator صارم + canonical hashing + guards خالصة؛ 48 fixtures؛ 43 اختبارًا offline تمر (evidence/s01_tests.md) |
| S02 | DONE_LOCAL | Store SQLite: accounts/sessions/leases/commands/events/approvals + journal + dedupe + recovery؛ اختبارات T04/T07/T08/T09 الخالصة مع persistent fake |
| S03 | DONE_LOCAL | worker/scheduler + fake adapter + cancellation + health (الأجزاء الخالصة من T16/T17/T21/T29) فوق Store؛ concurrency=1؛ لا game I/O؛ 20 اختبارًا (evidence/s03_tests.md) |
| S04/S05 | GATED_OWNER + OUT_OF_SANDBOX | read-only target ثم pilot مراقب؛ تحتاج JVM/GUI/عميل على جهاز المالك |
| S06/S07/S08 | PLANNED | Telegram مضبوط، AI advisory، release/cache/resources |
| S09 | DEFERRED | الاقتصاد/البيع/النقل بتفويض مستقل |

كل T01–T35 NOT_RUN على OSRS_ee حتى يُنفَّذ اختبار الهدف بدليل؛ اختبارات S01 تغطي أجزاء T20/T05/T26 الخالصة فقط وتُسجَّل عند نجاحها.

عند «تابع»: نفّذ دورة الاستئناف في RESUME_PROTOCOL §1 ثم أول مهمة غير مكتملة. لا تبدأ GitHub قبل النهاية.
