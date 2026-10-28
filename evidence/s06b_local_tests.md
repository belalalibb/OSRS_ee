# S06b-local — نقل Telegram حقيقي عبر HTTP (مختبر ضد خادم وهمي محلي فقط) — أدلة الاختبار

التاريخ: 2026-10-24 (UTC). البيئة: sandbox Linux، Python 3.13.14، stdlib `urllib`/`http.server`؛ لا إنترنت. الحارس في `tests/conftest.py` يحجب كل socket ويسمح عبر `loopback_only()` بالاتصال بـ127.0.0.1 فقط.

## ما أُضيف
| ملف | المحتوى |
|---|---|
| `osrs_ee/transports/telegram_http.py` | `TelegramHttpTransport` ينفذ `Transport.send` بـ`urllib` (POST JSON إلى `/bot<token>/sendMessage`)؛ `resolve_secret_ref("ref:env:NAME")` فقط — أي شكل آخر مرفوض؛ التوكن يُسجَّل canary في الـRedactor فلا يُعرض في أي مخرج؛ `TransportConfig` يرفض مضيفًا خارج allowlist وhttp غير loopback ومهلة خارج [0.5, 60]؛ خريطة الحالات: 200+ok → نجاح؛ 429 → `retry_after`؛ 5xx/انقطاع → عابر (الـOutbox يعيد المحاولة بتراجع)؛ 4xx أو `ok:false` → دائم؛ نص الخطأ يُقص ويُنقّح (`<token>`) |
| `osrs_ee/transports/telegram_poll.py` | `parse_update` صارم (message/callback_query فقط؛ أنواع صحيحة؛ بوتات مرفوضة؛ نص مقصوص 512؛ callback_data JSON بمفاتيح `{a,i,acc,e,p,v}` مرتبطة بالسياق) → `InboundMessage`/`InboundCallback`؛ `TelegramPoller.poll` عبر `getUpdates` بحد/مهلة محدودين، يُقدّم الـoffset فقط لما سُلِّم؛ **لا تفويض هنا** — كل شيء يمر على `ControlPlane`/`AccessPolicy` (default deny) |
| `tests/fake_http.py` | خادم HTTP مبرمج على 127.0.0.1 يسجل الطلبات ويرد بسيناريو |
| `tests/test_telegram_http.py` (14) | |

## النتيجة
`python3 -m pytest tests -p no:cacheprovider` → **217 passed** (203 + 14).

## ما تثبته (وما لا تثبته)
- تثبت: المراجع `ref:env:` وحدها تُقبل والمتغير يجب أن يوجد؛ المضيفون غير المدرجين مرفوضون؛ التوكن canary ولا يمكن إدخاله في Outbox؛ شكل الطلب والمسار؛ 429/5xx/4xx/`ok:false`/JSON تالف تُترجم كما هو موثق؛ نص غير آمن يُرفض قبل أي طلب؛ خطأ الخادم لا يعيد التوكن؛ رفض الاتصال عابر لا استثناء؛ Outbox + النقل الحقيقي: 429 → تراجع بلا طلب → تسليم بعد `retry_after`؛ التحليل يُسقط التحديثات المشوهة (11 شكلًا) دون رفع؛ poll يقدم offset ويرسل `offset` التالي، والأخطاء لا تلمسه؛ ControlPlane يرفض مستخدمًا مجهولًا وcallback من VIEWER.
- لا تثبت: أي سلوك لـapi.telegram.org أو بوت/دردشة حقيقيين؛ T02/T03 على دردشة فعلية تبقى NOT_RUN (تحتاج مفتاح اختبار من المالك ودردشة اختبار). CLI `service` ما زال يرفض `telegram.enabled=true` حتى يُربط النقل الحقيقي بالخدمة بإذن المالك.
