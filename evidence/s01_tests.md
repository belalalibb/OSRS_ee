# S01 — نتائج الاختبارات الفعلية

| البند | القيمة |
|---|---|
| التاريخ UTC | 2026-10-23T19:01:11Z |
| toolchain | Python 3.13.14، jsonschema 4.26.0، referencing 0.37.0، pytest 9.0.3 |
| الأمر | `python3 -m pytest tests -q` من جذر المستودع |
| النتيجة | 43 passed in 1.69s |
| ملفات الاختبار | test_contracts.py (10)، test_canonical.py (6)، test_guards.py (27) |
| حارس الشبكة | tests/conftest.py يجعل socket.socket يرفع استثناء؛ اختبار يثبت ذلك |
| fixtures | 48 (9 صالحة / 39 غير صالحة) من contracts/fixtures/generate.py؛ كل غير صالحة تفشل للسبب المسمّى في اسمها |

## ما تغطيه (أجزاء خالصة فقط)
- T20 (جزئي): valid/invalid، missing/extra/type/version/bool-as-int، params مغلقة لكل operation، bank opened/closed قيمة لا success.
- T05 (جزئي): AIProposal يرفض actions حرة/parameters/extra/no-approval؛ confidence=1 لا يمنح شيئًا؛ لا مسار تنفيذ.
- T26 (جزئي): timestamps خارج UTC-subset مرفوضة؛ الوقت محقون؛ issued<expires؛ intent لا يتجاوز lease.
- §5: epoch/state_version/config_hash/policy/binding mismatch → رفض؛ UNKNOWN pending يمنع غير-observational؛ ACK/TIMEOUT ≠ VERIFIED؛ REJECTED ≠ VERIFIED؛ bank closed ≠ 0.

## ما لا تثبته
لا durability/fencing/lease ownership (T04/T07/T08)، لا سلوك عميل حقيقي، لا V01–V08. T01–T35 تبقى NOT_RUN كاختبارات قبول للهدف.
