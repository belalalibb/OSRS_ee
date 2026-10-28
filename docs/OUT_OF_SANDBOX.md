# ما لا يمكن إنجازه داخل هذا الصندوق — وما يلزم لإغلاقه

الحالة 2026-10-24. كل ما يلي محجوب بسبب خارجي (لا جهاز هدف، لا عميل، لا قرار مالك، لا مفاتيح، لا تفويض GitHub)، وليس لنقص عمل محلي. الأجزاء المحلية المقابلة منجزة ومختبرة (282 اختبارًا offline تمر + 8 اختبارات هدف تُتخطى بصدق؛ انظر `evidence/`). الكود المساند لـS04b (محوّل قراءة loopback، مشرف عمليات عام، قياس، egress، wiring، tests/target) موجود ومختبر محليًا بحيث **يكون العمل على الهدف تنفيذ `ProcessSpec` ونقطة قراءة وتشغيل اختبارات جاهزة، لا كتابة نظام جديد**.

## 1. القرارات المفتوحة (يملكها المالك)
| ADR | الحالة | ما يلزم | ما يعتمد عليه |
|---|---|---|---|
| ADR-007 OS/toolchain | PROPOSED | اختيار نظام التشغيل والـ JVM/toolchain الإنتاجيين؛ sandbox ليست production | S04/S05، متانة فقدان الطاقة لـ SQLite، قياسات T18، سلوك الشبكة T19 |
| ADR-008 auth_mode | PROPOSED | إثبات دعم LEGACY/JAGEX_SESSION بعد V05؛ لا جلسات حقيقية قبل ذلك | أي تكامل login/adapter؛ `auth_mode=UNKNOWN` يمنع login بالتصميم |
| S09 الاقتصاد | DEFERRED | تفويض مستقل صريح | لا GE/بيع/نقل في أي مسار حالي |

### 1.1 ADR-007 — بدائل وتوصية فنية (القرار للمالك؛ لا يُفترض هنا)
| البديل | الوصف | ما يدعمه الكود الحالي | المخاطر/القيود |
|---|---|---|---|
| **A. عملية ابنة مملوكة (owned child)** | الخدمة تطلق العميل (JVM) عبر `ProcessSpec(argv, cwd, ready_file, stop_grace_seconds, env)` في session خاصة وتملك دورة حياته | `ProcessSupervisor` جاهز: جاهزية بملف، tick، SIGTERM→SIGKILL، دليل خروج، قياس /proc؛ اختبارات T10/T30 في `tests/target` تعمل عليه مباشرة | يحتاج غلافًا/plugin يكتب ready_file وtick (أو تعديل الطريقة إلى فحص نافذة/منفذ)؛ Windows يحتاج بديل إشارات (`terminate()` بدل SIGTERM) |
| **B. attach-only** | العميل يُشغَّل يدويًا والخدمة تراقب فقط (pid/نافذة/منفذ) بلا إطلاق أو قتل | `measure.py` (pid محدد) و`LoopbackReadOnlyAdapter`؛ لا يوجد `Supervisor` attach بعد (يحتاج صنفًا صغيرًا: `ready()` = منفذ/ملف، `stop()` = طلب مهذب فقط، `exited()` = pid غائب) | لا يمكن ضمان إيقاف منظم أو إعادة تشغيل محدودة؛ `kill ≠ logout` يبقى صحيحًا؛ أضعف في T16/T17/T34 |
| **C. حاوية/ VM مخصصة (Linux + Xvfb)** | البديل A داخل حاوية Linux مع Xvfb وcgroups للحدود | كل الكود المحلي Linux/proc يعمل كما هو؛ `doctor` يُبلّغ DISPLAY | تعقيد تجهيز أعلى؛ أداء GUI؛ ترخيص العميل داخل حاوية |
**التوصية الفنية:** **A على Linux** (أو C إن كان جهاز المالك ليس Linux) لأنه الوحيد الذي يوفر دليل خروج وإيقافًا منظمًا وقياسًا يطابق تصميم الخدمة الحالي بلا كود جديد جوهري؛ B مقبول كمرحلة قراءة فقط مؤقتة إذا رفض المالك إطلاق العميل من الخدمة. **القرار للمالك**؛ حتى يُتخذ يبقى `target.mode="device"` مرفوضًا.

### 1.2 ADR-008 — بدائل مصدر الحالة/المصادقة وتوصية فنية
| البديل | الوصف | ما يدعمه الكود الحالي | المخاطر/القيود |
|---|---|---|---|
| **A. نقطة قراءة loopback HTTP من داخل العميل** (plugin/agent للقراءة فقط يخدم `GET /observe` على 127.0.0.1) | العميل (أو plugin مرخص) يصدر لقطة حالة بصيغة عقد `Observation` | `LoopbackReadOnlyAdapter` كامل: regex loopback فقط، حدود حجم/مهلة/انحراف، تحقق عقد، `dispatch()` مرفوض دائمًا؛ T33 واختبارات امتثال S04b في `tests/target/test_target_adapter.py` | يحتاج كتابة plugin جانب العميل (خارج هذا المستودع، بلغة العميل)؛ شروط ترخيص/سياسة العميل؛ V05 لإثبات دعم auth_mode |
| **B. قراءة من ملفات/سجلات يكتبها العميل** | الخدمة تقرأ ملف حالة/سجل محلي | يحتاج `FileReadOnlyAdapter` صغيرًا (نفس نمط loopback؛ ~نفس الاختبارات) | طزاجة أضعف (STALE أكثر)، صيغ غير مستقرة |
| **C. لقطات شاشة/OCR** | استنتاج الحالة من الصورة | لا شيء | هش، غير صادق في UNKNOWN، مرفوض فنيًا |
**auth_mode:** يبقى `UNKNOWN` ويمنع أي login بالتصميم حتى يثبت V05 دعم `LEGACY`/`JAGEX_SESSION` على الجهاز؛ S04b لا تحتاج تسجيل دخول أصلًا (قراءة فقط بلا حساب). **التوصية الفنية:** **A** لأن الطرف الخادم موجود ومختبر؛ B كاحتياط. **القرار للمالك.**

### 1.3 متغيّرات البيئة التي يحتاجها التحقق على الهدف
| المتغيّر | الغرض | من يوفره |
|---|---|---|
| `OSRS_EE_TARGET=1`, `OSRS_EE_TARGET_CONFIG`, `OSRS_EE_TARGET_READY_FILE`, `OSRS_EE_TARGET_ENDPOINT` | تفعيل `tests/target -m target` (T06/T10/T30/T31/T33) | المالك على جهاز الهدف بعد ADR-007/008 |
| `OSRS_EE_ALLOW_NETWORK=1` | السماح بأي socket غير loopback (اختبارات `live` و`service --allow-real-network`) | المالك، وقت التشغيل فقط |
| `OSRS_EE_TG_TOKEN`, `OSRS_EE_TG_CHAT_ID` | T02/T03 Telegram حي (bot اختبار + دردشة اختبار) | المالك؛ خارج المستودع؛ لا تُسجَّل |
| `OSRS_EE_AI_KEY`, `OSRS_EE_AI_BASE_URL`, `OSRS_EE_AI_MODEL` | T35 مزوّد AI حي (اختياري؛ استشاري فقط) | المالك |
الأسماء الفعلية في `config.toml` تُحدَّد بـ`ref:env:NAME`؛ الكود لا يقرأ إلا الاسم المُشار إليه ويسجّل قيمته canary.

## 2. التحقق من المصدر V01–V08
كلها **REPORTED_UNVERIFIED**: تحتاج source revisions مثبتة وجهازًا يُشغَّل عليه التحقق. لا تُغلق بقراءة التقارير. تسبق التكاملات المتأثرة (adapter/identity/cache/egress)، لا العقود الخالصة.

## 3. S04 / S05 (تحتاج JVM/GUI/عميل على جهاز المالك)
- S04 read-only target: owned processes، readiness، إشارات health فعلية، قياس RSS/native/GC/FD/disk/network، egress inventory (T06/T10/T30/T31/T33/T34/T35). **المساند المحلي جاهز** (`ProcessSupervisor`، `LoopbackReadOnlyAdapter`، `measure.py`، `egress.py`، `tests/target/`)؛ المتبقي على الجهاز: `ProcessSpec` حقيقي + نقطة قراءة + تشغيل الاختبارات.
- S05 pilot مراقب: حساب واحد بإذن صريح، لا أفعال مالية، abort/drain حي، canary إصدار حي بإذن (T15/T16 الجزء الحي).
- ما يُستبدل عند الوصل: `FakeAdapter` → `LoopbackReadOnlyAdapter` (أو بديل ADR-008) يحترم `Adapter` Protocol؛ `FakeSupervisor` → `ProcessSupervisor(ProcessSpec(...))`؛ `FakeTransport`/`FakeProvider` → يبنيهما `wiring.py` تلقائيًا عند opt-in؛ `ResourceSnapshot` من `measure.host_measurer` (موجود). لا تغيير مطلوب في Store/guards/contracts.

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
| القياس | Linux مع `/proc` (منفذ في `measure.py` بلا psutil)؛ OS آخر يحتاج تنفيذًا بديلًا | ResourceSnapshot حقيقي، Admission |

### 3.2 الاختبارات التشغيلية بالترتيب (على الجهاز، كل واحدة بدليل artifact)
1. `osrs-ee doctor --config target.toml` + `python -m pytest` على الجهاز (بيئة سليمة؛ توقع 282 passed) → ثم `osrs-ee target-check` (S04a) يسجل OS/Python/JVM/عميل/شاشة.
2. T10/T30: `OSRS_EE_TARGET=1 ... python -m pytest tests/target -m target` — إطلاق عملية عميل مملوكة بلا تسجيل دخول عبر `ProcessSupervisor`، readiness، إنهاء نظيف، kill -9 → RECOVERY_REQUIRED لا READY.
3. T06/T31/T33: قياس RSS/FD/GC/disk فعلي → `ResourceSnapshot`؛ جرد egress.
4. SQLite power-loss: kill -9 أثناء كتابة → إعادة فتح → journal متسق (ADR-003 على OS الهدف).
5. T16/T17/T34: مشرف/خدمة: إعادة تشغيل محدودة بميزانية، قاطع الدائرة، abort/drain حي.
6. S05 فقط بإذن: حساب واحد، recipe واحدة مراقبة، T04/T07/T08/T09/T12/T35، خطة إيقاف مكتوبة قبل البدء.
كل خطوة تُسجَّل في `evidence/target_*.md` مع SHA للـcommit وبيئة الجهاز؛ نجاح الاختبارات المحلية لا يغني عن أي منها.

## 4. اختبارات القبول T01–T35
كلها **NOT_RUN** كاختبارات هدف. التغطية المحلية (منطق القرار فقط):
| T | مغطى محليًا (خالص) | يحتاج الهدف |
|---|---|---|
| T02/T03 | RBAC، redaction/canary، approvals مقيّدة أحادية الاستخدام (S06)؛ نقل HTTP ضد خادم وهمي + wiring (S06b/WIRE-01) | تشغيل حي بـtoken المالك (`tests/target/test_live_services.py` جاهز) |
| T04/T07/T08/T09/T10/T12/T28 | Store: CAS/leases/epochs/journal/dedupe/recovery (S02) | power-loss على OS الهدف |
| T05/T20/T26 | عقود/fixtures/canonical/guards (S01) | — |
| T14/T15/T18/T19/T32 | registry/release/cache/admission/network (S08) | قياسات فعلية، canary حي، شبكة حقيقية |
| T16/T17/T21/T29 | worker/abort-drain/health/outbox (S03/S06)؛ بوابة الجاهزية + `ProcessSupervisor` بعملية python (SUP-02)؛ اختبارات الفشل (TEST-FAIL) | عملية عميل حقيقية، إشارات health من العميل |
| AI (FOUNDATION) | consent/redaction/budgets/AIProposal-only (S07) | مزوّد حقيقي |
| T06/T10/T30/T31/T33 | اختبارات جاهزة في `tests/target/` (تُتخطى هنا) | جهاز الهدف + ADR-007/008 |
| T35 | مزوّد ضد خادم وهمي (S07b) + اختبار حي جاهز | مفتاح AI من المالك |
| T01, T11, T13, T22–T25, T27, T34 | — | كلها تحتاج الهدف/قرارات |

## 5. النشر (PUB-02 منجز جزئيًا؛ التفويض مؤجل للنهاية بقرار المالك)
تم 2026-10-23: فحص remote (كان فارغًا) → push عادي لـ`main`=`3740096f` و`genspark_ai_developer`=`6552b84` → PR #1 → تحقق من clone جديد. بعد ذلك أُبطل التفويض وقرر المالك عدم طلبه أثناء التطوير؛ كل commits ما بعد `6552b84` (تغليف/CLI، RUNBOOK/ROADMAP، S04a، S04c-local، S06b/S07b-local، S04b-prep، SUP-02، WIRE-01، CLI-02، tests/target، test_failures، clean-env، DOC-09) محفوظة في حزم موثقة بالبصمة وتُدفع عاديًا عند أول جلسة بتفويض ناجح ثم يُحدّث PR #1. يبقى: مراجعة/دمج PR #1 (المالك). لا force push، لا حذف. **المفاتيح الشخصية المنشورة في المحادثة يجب إبطالها ولن تُستخدم.**

## 6. حدود لا تتغير
لا حسابات حية، لا GE/بيع/نقل، لا تشغيل متعدد/غير مراقب، AI استشاري فقط، لا spoofing/mutation، لا ضمان anti-ban أو أرباح أو عدد نوافذ.
