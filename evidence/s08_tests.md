# S08 — أدلة اختبارات release/cache/admission/network (الأجزاء الخالصة)

- التاريخ: 2026-10-23 (UTC) — sandbox؛ Python 3.13، pytest 9.0.3.
- الأمر: `python3 -m pytest tests -q` → **156 passed** (S01: 43، S02: 34، S03: 20، S06: 22، S07: 14، S08: 23).
- لا I/O: البصمات على bytes في الذاكرة؛ القياسات محقونة. **canary الحي غير مُنمذج** (يتطلب إذن المالك وجهازًا حقيقيًا).

## الملفات
- `osrs_ee/release.py` — `Registry` (allow-list مُراجَع: name→(sha256, license)؛ أي مجهول/بصمة مختلفة/مسار غير آمن → quarantine قبل التحميل)، `ReleaseManifest` (frozen؛ بصمة canonical؛ `compatible_with` على contract/schema version)، `Release` (DETECTED→DOWNLOADED→BUILT→CONTRACT_TESTED→APPROVED→DRAINING→CANARY→ACTIVE؛ خطوة واحدة للأمام فقط مع `ref:` دليل لكل خطوة؛ DOWNLOADED يتطلب قبول كل artifact؛ `fail()` → ROLLED_BACK إلى ACTIVE متوافق فقط وإلا STOPPED)، `BoundedCache` (count/bytes/age، LRU، عزل لكل owner، مفاتيح تحمل هوية لا تُخزَّن أبدًا، مفاتيح traversal مرفوضة)، `ResourceSnapshot`/`Admission` (قياس مؤرَّخ لا تقدير؛ snapshot قديم لا يقبل؛ disk reserve/RSS/FD/CPU؛ concurrency=1؛ `must_stop` تحت الضغط)، `NetworkPolicy` (PROXY مطلوب → لا fallback مباشر؛ انقطاع proxy = PROXY_UNAVAILABLE؛ انتهاء sticky = تجديد مطلوب؛ لا تجديد أثناء UNKNOWN معلّق؛ مسارات مجهولة مرفوضة).
- `tests/test_release.py` (23).

## ما تثبته الاختبارات
- **T14:** dependency/hash/path خاطئ → quarantine قبل load؛ بصمة غير صالحة تُرفض عند التسجيل.
- **T15:** manifest ثابت وبصمته canonical؛ لا تخطي خطوات ولا خطوة بلا دليل؛ artifact غير مقبول يوقف الإصدار عند DOWNLOADED؛ الفشل يعود فقط إلى ACTIVE متوافق وإلا STOP (migration غير متوافقة → STOP؛ لا ACTIVE → STOP).
- **T32/V08 (نطاق فقط):** لا نسخ لمسارات هوية في الكاش؛ حدود العدد/البايتات/العمر مع إخلاء LRU؛ عزل القراءة بين المالكين. **لا ادعاء anti-ban.**
- **T18 (المبدأ):** القبول يعتمد على قياس طازج داخل كل الحدود (لا heap estimate)؛ أي حد يُرفض بـ INSUFFICIENT_RESOURCES؛ الضغط على جلسة جارية يوجب stop.
- **T19:** انقطاع/انتهاء لا يؤدي إلى fallback محظور؛ reason code صحيح؛ لا renew خلال UNKNOWN.

## ما لا تثبته
- أرقام السعة الفعلية (RSS/native/GC/FD) على الهدف، سلوك DNS/IPv6/proxy الحقيقي، canary حي، أو rollback فعلي لعمليات JVM. T14/T15/T18/T19/T32 تبقى NOT_RUN كاختبارات قبول هدف؛ ما هنا هو منطق القرار فقط.
