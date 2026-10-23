# ما لا يمكن إنجازه داخل هذا الصندوق — وما يلزم لإغلاقه

الحالة 2026-10-23. كل ما يلي محجوب بسبب خارجي (لا جهاز هدف، لا عميل، لا قرار مالك، لا تفويض GitHub)، وليس لنقص عمل محلي. الأجزاء الخالصة المقابلة منجزة ومختبرة (161 اختبارًا offline؛ انظر `evidence/s0*_tests.md`).

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

### 3.1 متطلبات جهاز الهدف (يجهزها المالك قبل S04b)
| البند | المطلوب | لماذا |
|---|---|---|
| نظام التشغيل | قرار ADR-007 (Linux موصى به للـservice/cgroups؛ Windows ممكن بقيود) | إدارة العمليات المملوكة، حدود الموارد، سلوك SQLite عند فقد الطاقة |
| Python | ≥3.11 + venv + `pip install -e ".[dev]"` (نفس RUNBOOK §1) | تشغيل النواة والاختبارات |
| JVM | JDK/JRE متوافق مع العميل المختار؛ إصدار مثبت ومسجل | S04b: إطلاق/مراقبة عملية عميل مملوكة |
| العميل | عميل OSRS طرف ثالث مرخص للاستخدام، بوضع قراءة فقط أولًا؛ بدون أي plugin تنفيذ | S04b read-only؛ V05 لـauth_mode |
| الشاشة/GUI | جلسة رسومية (X11/Wayland/Windows desktop) أو Xvfb للـheadless | مشرف GUI، لقطات حالة النافذة |
| الحساب | **لا حساب حي قبل S05 وإذن صريح**؛ S04b بلا تسجيل دخول | ثابت لا يسقط |
| الشبكة | قائمة egress مسموحة صريحة؛ لا proxy fallback محظور | T19/T31، NetworkPolicy |
| Telegram/AI | توكنات في متجر أسرار خارج المستودع (`ref:` فقط)؛ اختيارية حتى S06b/S07b | لا أسرار في الكود |
| القياس | أدوات قراءة RSS/FD/GC/disk (psutil أو /proc) | ResourceSnapshot حقيقي، Admission |

### 3.2 الاختبارات التشغيلية بالترتيب (على الجهاز، كل واحدة بدليل artifact)
1. `osrs-ee status` + `python -m pytest` على الجهاز (بيئة سليمة) → ثم `osrs-ee target-check` (S04a) يسجل OS/Python/JVM/عميل/شاشة.
2. T10/T30: إطلاق عملية عميل مملوكة بلا تسجيل دخول، readiness، إنهاء نظيف، kill -9 → RECOVERY_REQUIRED لا READY.
3. T06/T31/T33: قياس RSS/FD/GC/disk فعلي → `ResourceSnapshot`؛ جرد egress.
4. SQLite power-loss: kill -9 أثناء كتابة → إعادة فتح → journal متسق (ADR-003 على OS الهدف).
5. T16/T17/T34: مشرف/خدمة: إعادة تشغيل محدودة بميزانية، قاطع الدائرة، abort/drain حي.
6. S05 فقط بإذن: حساب واحد، recipe واحدة مراقبة، T04/T07/T08/T09/T12/T35، خطة إيقاف مكتوبة قبل البدء.
كل خطوة تُسجَّل في `evidence/target_*.md` مع SHA للـcommit وبيئة الجهاز؛ نجاح الاختبارات المحلية لا يغني عن أي منها.

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

## 5. النشر (PUB-02 منجز جزئيًا؛ التفويض متقطع)
تم 2026-10-23: فحص remote (كان فارغًا) → push عادي لـ`main`=`3740096f` و`genspark_ai_developer` → PR #1 → تحقق من clone جديد. بعد ذلك أُبطل التفويض؛ commits أحدث (تغليف/CLI، RUNBOOK/ROADMAP، تصحيح الوثائق) محفوظة في حزم وتُدفع عاديًا عند أول جلسة بتفويض ناجح ثم يُحدّث PR #1. يبقى: مراجعة/دمج PR #1 (المالك). لا force push، لا حذف. **المفاتيح الشخصية المنشورة في المحادثة يجب إبطالها ولن تُستخدم.**

## 6. حدود لا تتغير
لا حسابات حية، لا GE/بيع/نقل، لا تشغيل متعدد/غير مراقب، AI استشاري فقط، لا spoofing/mutation، لا ضمان anti-ban أو أرباح أو عدد نوافذ.
