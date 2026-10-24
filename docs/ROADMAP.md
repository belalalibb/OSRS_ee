# ROADMAP — خطة التنفيذ الهندسية إلى المنتج المتكامل

آخر تحديث: 2026-10-24. مرتبة حسب الاعتماديات؛ كل مرحلة تذكر: الهدف، ما يسبقها، الملفات المطلوب إنشاؤها/تعديلها، الاختبارات، معيار القبول، ومن ينفذها وأين. **المنجز**: S01–S03، S06a، S07a، S08a، **S04a** (أدوات تسجيل/إعادة/امتثال/جرد الهدف؛ `evidence/s04a_tests.md`)، **S04c-local** (config TOML fail-closed + Supervisor Protocol/FakeSupervisor + Service loop + CLI `service` محاكاة فقط؛ 203 اختبارات؛ `evidence/s04c_local_tests.md`). **كل T01–T35 وV01–V08 تبقى بحالتها** (NOT_RUN / REPORTED_UNVERIFIED) حتى تُنفَّذ على الهدف بدليل.

```
 D0 قرارات ──► S04a أدوات تحقق محلية ──► S04b (جهاز) read-only adapter ──► S04c supervisor ──► S05 pilot
                   │                                                            │
                   └─► S06b Telegram حقيقي ◄──────────────────────────────────┘
                   └─► S07b AI provider حقيقي (اختياري)
                   └─► S08b release live canary (بعد S05)
```

---

## D0 — القرارات الحاكمة (المالك؛ لا كود يعتمد عليها قبلها)

| قرار | ما يجب تحديده | يفتح |
|---|---|---|
| **ADR-007 OS/toolchain** | نظام التشغيل الهدف (مثلًا Windows 11 x64 أو Ubuntu 24.04)، إصدار JVM (مثلًا Temurin 17)، عميل اللعبة وطريقة تشغيله، هل يُسمح بعمليات مملوكة (child processes) أم مراقبة فقط | S04b/S04c، اختبار متانة SQLite على الهدف، قياسات T18 |
| **ADR-008 auth_mode** | أي auth_mode مدعوم (LEGACY / JAGEX_SESSION) **بعد V05**؛ كيف تُخزَّن المراجع (`ref:`) وأين الأسرار (vault/OS keychain) | أي login في S05؛ قبلها `auth_mode=UNKNOWN` يمنع login بالتصميم |
| **إذن الهدف** | جهاز محدد، حساب اختبار واحد، نطاق الأفعال المسموحة (لا مالية)، نافذة زمنية | S04b/S05 |

معيار الإغلاق: صفوف ADR-007/008 في `docs/FOUNDATION.md` تتحول من PROPOSED إلى ACCEPTED بنص القرار.

---

## S04a — تحضير S04 داخل أي بيئة — **DONE_LOCAL 2026-10-23** (commits `875d722`, `78f696b`)

**الهدف:** كل ما يمكن اختباره قبل لمس عميل حقيقي: عقد الـ adapter، تسجيل/إعادة تشغيل جلسة read-only، فحص بيئة الهدف، اختبارات امتثال لأي adapter.

| ملف | إنشاء/تعديل | المحتوى |
|---|---|---|
| `osrs_ee/adapters/__init__.py` | إنشاء | تصدير `Adapter` Protocol (نقل من worker.py مع إبقاء alias) |
| `osrs_ee/adapters/recording.py` | إنشاء | `RecordingAdapter`: يلفّ أي adapter ويسجّل observe/dispatch كـ JSONL منقّح (عبر `Redactor`) لإعادة التشغيل |
| `osrs_ee/adapters/replay.py` | إنشاء | `ReplayAdapter`: يعيد تشغيل JSONL مسجّل؛ يسمح باختبار منطق الـ worker على بيانات حقيقية منقّحة دون عميل |
| `osrs_ee/adapters/conformance.py` | إنشاء | `run_conformance(adapter, clock)`: observe يعيد Observation صالحًا بالعقد؛ dispatch يحترم deadline؛ لا استثناءات غير `AdapterFailure`؛ لا شبكة خارج allowlist |
| `osrs_ee/target_check.py` | إنشاء | `osrs-ee target-check`: يجمع (بلا تنفيذ أي لعبة) OS/arch/Python/Java (`java -version` إن وُجد)/قرص/RAM/حدود FD/وجود عميل في مسار مُعطى؛ JSON + قائمة «ينقص». **لا يشغّل شيئًا.** |
| `osrs_ee/cli.py` | تعديل | إضافة `target-check` و`replay <jsonl>` |
| `tests/test_adapters.py` | إنشاء | conformance على FakeAdapter وReplayAdapter؛ Recording→Replay round-trip؛ التنقيح يمنع أي canary في JSONL |
| `tests/test_target_check.py` | إنشاء | يعمل على sandbox ويبلّغ «java مفقود» بدل الفشل |

**معيار القبول S04a:** الاختبارات تمر offline؛ `FakeAdapter` يجتاز conformance؛ `target-check` يعطي تقريرًا صحيحًا على sandbox (java مفقود، عميل مفقود) دون محاولة تشغيل.

---

## S04b — adapter حقيقي للقراءة فقط (على جهاز المالك؛ بعد D0)

**الهدف:** تنفيذ `Adapter.observe()` فعلي من عميل حقيقي **بلا أي dispatch** (dispatch يعيد `NOT_SENT` دائمًا في هذه المرحلة)، وقياس الموارد الفعلي.

| ملف | المحتوى |
|---|---|
| `osrs_ee/adapters/<client>_readonly.py` | observe من مصدر الحالة المعتمد في ADR-007 (مثلًا loopback HTTP لـ agent داخل العميل بـ `loopback_endpoint` من العقد)؛ يملأ `fields` بـ KNOWN/STALE/UNKNOWN بصدق؛ `bank.items` UNKNOWN إن البنك مغلق |
| `osrs_ee/measure.py` | `ResourceSnapshot` من `psutil` أو `/proc` (اعتمادية اختيارية تُضاف فقط هنا) |
| `osrs_ee/egress_allowlist.py` | وجهات شبكة مسموحة؛ أي اتصال خارجها يُسجَّل ويُرفض (T31) |
| `tests/target/` | اختبارات تُشغَّل **على الجهاز فقط** (`pytest -m target`)، تُعلَّم `skip` في sandbox |

**اختبارات الهدف المطلوبة (تُسجَّل في `evidence/target/`):**
- T06 readiness: العميل يصل لحالة قابلة للملاحظة خلال حد زمني ويُبلغ ذلك بصدق.
- T10 observation: الحقول المطلوبة KNOWN عند فتح البنك، UNKNOWN عند إغلاقه (لا صفر).
- T30 egress inventory: قائمة الوجهات الفعلية أثناء جلسة read-only.
- T31 telemetry: لا egress خارج allowlist؛ flags coverage.
- T33 resources: قياس RSS/native/FD/CPU/disk لمدة ≥30 دقيقة read-only.
- متانة SQLite: kill -9/قطع طاقة أثناء كتابة ثم `integrity_ok` + recovery → RECOVERY_REQUIRED.

**معيار القبول S04b:** الـ adapter يجتاز conformance؛ T06/T10/T30/T31/T33 لها ملفات أدلة بتاريخ وأرقام؛ لا dispatch حدث (journal خالٍ من DISPATCHING).

---

## S04c — supervisor عمليات — **الجزء المحلي DONE_LOCAL 2026-10-24** (commits `b26a731`, `f2564e3`, `4fdb0b9`, `8c4216f`)؛ الجزء على الجهاز بعد S04b

منجز محليًا: `config.py` + `config.example.toml`، `supervisor.py` (Protocol + `FakeSupervisor` لا يطلق شيئًا)، `service.py` (قبول/بدء/إيقاف منظم/إعادة تشغيل محدودة/ضغط/تنبيهات منقّحة)، CLI `service --config` (simulated فقط)، 22 اختبارًا. **المتبقي على الجهاز:** تنفيذ `Supervisor` حقيقي (owned child أو attach-only حسب ADR-007) وربطه بـadapter S04b؛ معيار القبول أدناه لم يُنفَّذ.

| ملف | المحتوى |
|---|---|
| `osrs_ee/supervisor.py` | إطلاق/مراقبة عملية العميل كـ owned child (إن سمح ADR-007) أو attach-only؛ readiness؛ `HealthMonitor` من ticks فعلية؛ drain ينتظر quiescence؛ `kill` ليس logout (T16/T17/T34) |
| `osrs_ee/service.py` | حلقة تشغيل طويلة: Store → Worker → Supervisor → Outbox؛ إشارات OS (SIGTERM → request_abort → drain)؛ لا concurrency >1 |
| `osrs_ee/config.py` | إعدادات من TOML (مسارات، allowlists، حدود) مع تحقق؛ لا أسرار — مراجع فقط |
| `config.example.toml` | نموذج |
| `tests/test_service.py` | حلقة الخدمة مع FakeAdapter وsupervisor وهمي: SIGTERM → drain → RESTING/RECOVERY_REQUIRED |

**معيار القبول S04c:** T16 (abort → لا أفعال لاحقة؛ UNKNOWN إن لا exit proof)، T17 (ساكن≠متجمد؛ restart storm محدود)، T34 (لا autologin بعد stop) مع أدلة على الجهاز.

---

## S05 — pilot مراقب (على الجهاز؛ بعد S04c + ADR-008 + إذن صريح)

- تفعيل `dispatch` لأفعال من القائمة المسموحة فقط (NOOP/OBSERVE/BANK_OPEN/BANK_CLOSE/WALK_TO/LOGOUT، ثم BANK_* بعد نجاحها)؛ لا GE/بيع/نقل.
- حساب واحد، جلسة واحدة، مشغّل حاضر، Telegram حقيقي (S06b) للـ /stop والموافقات.
- **الاختبارات:** T04/T07/T08/T09/T12 على الهدف (journal/dedupe/idempotency/recovery الحية)، T35 جلسة كاملة بلا تدخل غير مخطط.
- **معيار القبول:** ≥3 جلسات pilot بأدلة؛ كل UNKNOWN سُوّي عبر RECONCILING موثّق؛ صفر أفعال خارج القائمة.

---

## S06b — Telegram transport حقيقي (بعد S04b؛ يمكن تطويره بالتوازي بمفتاح اختبار)

| ملف | المحتوى |
|---|---|
| `osrs_ee/transports/telegram_http.py` | `Transport.send` عبر Bot API (stdlib `urllib`)؛ يحترم 429/retry_after؛ token من `ref:` → متغير بيئة فقط |
| `osrs_ee/transports/telegram_poll.py` | long polling → `InboundMessage`/`InboundCallback`؛ كل تحديث يمر عبر `AccessPolicy` |
| `tests/test_telegram_http.py` | مع خادم HTTP محلي وهمي (لا إنترنت): 200/429/5xx/شكل الرد |

**معيار القبول:** T02 (canary لا يظهر في chat فعلي بمفتاح اختبار)، T03 (مستخدم خاطئ/replay مرفوض فعليًا).

## S07b — مزوّد AI حقيقي (اختياري؛ بعد S06b)
`osrs_ee/providers/openai_compat.py` ينفذ `Provider.complete` بميزانية ومهلة؛ المفتاح من البيئة؛ اختبار بخادم وهمي محلي. بدون هذا، النظام يعمل بلا AI (الـ advisor اختياري بالتصميم).

## S08b — canary إصدار حي (بعد S05)
ربط `Release` بـ supervisor: APPROVED → DRAINING (حقيقي) → CANARY (جلسة واحدة بإذن) → ACTIVE؛ فشل → rollback متوافق أو STOP. T15 على الهدف.

## S09 — الاقتصاد (مؤجل؛ تفويض مستقل)
خارج النطاق حتى قرار مكتوب.

---

## معايير القبول العامة (تنطبق على كل مرحلة)
1. لا دمج بلا اختبارات offline تمر + أدلة في `evidence/`.
2. اختبارات الهدف تُحفظ في `evidence/target/<T>_<date>.md` مع الأرقام الخام وبيئة التشغيل.
3. حالة T/V تتغير في `docs/FOUNDATION.md` **فقط** عند وجود ملف دليل.
4. لا أسرار في Git؛ `ref:` فقط؛ فحص أسرار قبل كل push.
5. كل تغيير: commit → push للفرع → PR؛ عند فقد التفويض: bundle + sha256 + رابط (RESUME_PROTOCOL).

## ما الذي يمكن للوكيل تنفيذه الآن دون المالك
S04a وS04c-local منجزتان. المتبقي بلا مالك: S06b وS07b بخوادم وهمية محلية. كل ما يحتاج جهازًا حقيقيًا أو قرار D0 معلّم صراحة أعلاه.
