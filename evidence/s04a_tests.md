# S04a — أدوات adapter محلية (بلا عميل) — أدلة الاختبار

التاريخ: 2026-10-23 (UTC). البيئة: sandbox Linux x86_64، Python 3.13.14، sqlite 3.46.1، jsonschema 4.26.0، pytest 9.x.

## ما أُضيف
| ملف | المحتوى |
|---|---|
| `osrs_ee/adapters/__init__.py` | إعادة تصدير `Adapter`/`AdapterResponse`/`AdapterFailure`/`FakeAdapter` من worker (مصدر واحد) |
| `osrs_ee/adapters/recording.py` | `TraceWriter` (JSONL `trace/1`؛ تنقيح إلزامي fail-closed: pseudonym متوافق مع العقد `acc_r<sha256>` لمعرّفات الحسابات، `Redactor.scan` لكل سجل، السجل غير الآمن لا يُكتب ويُرفع `RedactionError`) + `RecordingAdapter` (يحافظ على سلوك الـadapter الملفوف تمامًا) |
| `osrs_ee/adapters/replay.py` | `load_trace` (header/schema/redacted/seq صارمة) + `ReplayAdapter` (strict: مطابقة command_id/operation وإلا `ReplayMismatch`؛ `ReplayExhausted`) |
| `osrs_ee/adapters/conformance.py` | `run_conformance`: C1 عقد Observation، C2 زمن صادق، C3 state_version لا ينقص، C4 أنواع/enums الرد، C5 لا استثناءات غير `AdapterFailure`، C6 VERIFIED يحتاج evidence، C7 لا شبكة خارج allowlist؛ probe = OBSERVE فقط (SAFE_OPERATIONS) وإلا رفض |
| `osrs_ee/target_check.py` | جرد الجهاز: OS/Python/sqlite/jsonschema/java (فقط `java -version`)/مسار العميل/شاشة/قرص/RAM/fd؛ قائمة «ينقص» + تحذيرات؛ **لا يشغّل شيئًا** |
| `osrs_ee/cli.py` | أوامر `target-check` (exit 2 عند النقص)، `conformance [--trace]`، `replay <jsonl>` |
| `tests/test_adapters.py` (12)، `tests/test_target_check.py` (5)، `tests/test_cli.py` (+3) | |

## النتيجة
`python3 -m pytest tests -p no:cacheprovider` → **181 passed** (161 سابقًا + 20).

## ما تثبته هذه الاختبارات (وما لا تثبته)
- تثبت: مجموعة conformance تكشف العيوب المصنّفة (ملاحظة مستقبلية، عقد غير صالح، استثناء غريب، enum خاطئ، VERIFIED بلا دليل، محاولة شبكة، probe غير آمن)؛ FakeAdapter وReplayAdapter يجتازانها؛ التسجيل→الإعادة يعيد نفس مراحل الـjournal (VERIFIED/UNKNOWN/UNKNOWN) على store جديد؛ canary وأسرار على شكل `password:` لا تُكتب في الأثر أبدًا؛ أثر غير منقّح/بفجوة seq/بلا ملاحظة يُرفض؛ target-check في الـsandbox يعيد «ينقص: عميل، شاشة، ADR-007/008» بصدق مع exit 2.
- لا تثبت: أي سلوك لعميل حقيقي. T06/T10/T30/T31/T33 تبقى NOT_RUN؛ تنفيذها يحتاج S04b على جهاز المالك، وسيُشغَّل فيها `run_conformance` نفسها على الـadapter الحقيقي.

## تشغيل يدوي موثّق (sandbox)
- `osrs-ee target-check --no-java-probe` → `ready_for_s04b: false`؛ missing: client path، graphical session، ADR-007/008؛ warnings: RAM 985MB، fd 1024. exit 2.
- `osrs-ee conformance` → passed: true (FakeAdapter). exit 0.
- أثر مسجّل (FakeAdapter عبر RecordingAdapter، خطوة VERIFIED) → `osrs-ee replay trace.jsonl` → step VERIFIED، final RESTING؛ `osrs-ee conformance --trace trace.jsonl` → passed.
