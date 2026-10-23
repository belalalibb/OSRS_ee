# ما لا يمكن إنجازه داخل هذا الصندوق — وما يلزم لإغلاقه

الحالة 2026-10-23. كل ما يلي محجوب بسبب خارجي (لا جهاز هدف، لا عميل، لا قرار مالك، لا تفويض GitHub)، وليس لنقص عمل محلي. الأجزاء الخالصة المقابلة منجزة ومختبرة (156 اختبارًا offline؛ انظر `evidence/s0*_tests.md`).

## 1. القرارات المفتوحة (يملكها المالك)
| ADR | الحالة | ما يلزم | ما يعتمد عليه |
|---|---|---|---|
| ADR-007 OS/toolchain | PROPOSED | اختيار نظام التشغيل والـ JVM/toolchain الإنتاجيين؛ sandbox ليست production | S04/S05، متانة فقدان الطاقة لـ SQLite، قياسات T18، سلوك الشبكة T19 |
| ADR-008 auth_mode | PROPOSED | إثبات دعم LEGACY/JAGEX_SESSION بعد V05؛ لا جلسات حقيقية قبل ذلك | أي تكامل login/adapter؛ `auth_mode=UNKNOWN` يمنع login بالتصميم |
| S09 الاقتصاد | DEFERRED | تفويض مستقل صريح | لا GE/بيع/نقل في أي مسار حالي |

## 2. التحقق من المصدر V01–V08
كلها **REPORTED_UNVERIFIED**: تحتاج source revisions مثبتة وجهازًا يُشغَّل عليه التحقق. لا تُغلق بقراءة التقارير. تسبق التكاملات المتأثرة (adapter/identity/cache/egress)، لا العقود الخالصة.

## 3. S04 / S05 (تحتاج JVM/GUI/عميل على جهاز المالك)
- S04 read-only target: owned processes، readiness، إشارات health فعلية، قياس RSS/native/GC/FD/disk/network، egress inventory (T06/T10/T30/T31/T33/T34/T35).
- S05 pilot مراقب: حساب واحد بإذن صريح، لا أفعال مالية، abort/drain حي، canary إصدار حي بإذن (T15/T16 الجزء الحي).
- ما يُستبدل عند الوصل: `FakeAdapter` → adapter حقيقي يحترم `Adapter` Protocol؛ `FakeTransport` → Telegram transport؛ `FakeProvider` → مزوّد AI؛ `ResourceSnapshot` من قياس فعلي. لا تغيير مطلوب في Store/guards/contracts.

## 4. اختبارات القبول T01–T35
كلها **NOT_RUN** كاختبارات هدف. التغطية المحلية (منطق القرار فقط):
| T | مغطى محليًا (خالص) | يحتاج الهدف |
|---|---|---|
| T02/T03 | RBAC، redaction/canary، approvals مقيّدة أحادية الاستخدام (S06) | sinks حقيقية، Telegram API |
| T04/T07/T08/T09/T10/T12/T28 | Store: CAS/leases/epochs/journal/dedupe/recovery (S02) | power-loss على OS الهدف |
| T05/T20/T26 | عقود/fixtures/canonical/guards (S01) | — |
| T14/T15/T18/T19/T32 | registry/release/cache/admission/network (S08) | قياسات فعلية، canary حي، شبكة حقيقية |
| T16/T17/T21/T29 | worker/abort-drain/health/outbox (S03/S06) | عمليات حقيقية، إشارات health فعلية |
| AI (FOUNDATION) | consent/redaction/budgets/AIProposal-only (S07) | مزوّد حقيقي |
| T01, T06, T11, T13, T22–T25, T27, T30, T31, T33–T35 | — | كلها تحتاج الهدف/قرارات |

## 5. النشر (PUB-02)
GitHub OAuth غير متاح للأدوات طوال العمل. المطلوب عند النهاية: تفويض واحد من المالك → فحص remote دون افتراض فراغه → حفظ أي عمل بعيد → push عادي لـ `genspark_ai_developer` → PR واحد إلى `main` → تحقق SHA/شجرة/محتوى. لا force push، لا حذف. **المفاتيح الشخصية المنشورة في المحادثة يجب إبطالها ولن تُستخدم.**

## 6. حدود لا تتغير
لا حسابات حية، لا GE/بيع/نقل، لا تشغيل متعدد/غير مراقب، AI استشاري فقط، لا spoofing/mutation، لا ضمان anti-ban أو أرباح أو عدد نوافذ.
