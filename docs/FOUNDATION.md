# OSRS_ee — الأساس الموحد القابل للاستعادة، 0.2

**LOCAL_DRAFT / NOT_PUSHED — لا تطبيق منفذ ولا اختبارات تشغيل ناجحة للهدف.** هذه نسخة استعادة موحدة مكثفة من التحليل الموثق في المحادثة والتقارير المقروءة سابقًا؛ليست استعادة بايتية للـ13 ملفًا التي فقدت قبل commit/التسليم. جمعت الوثائق الحاكمة هنا لتقليل التكرار وخطر فقد العمل مرة أخرى.

## 1. السياق والتفويض

الوجهة الوحيدة https://github.com/belalalibb/OSRS_ee.git والفرع main. المستودعات أدناه مصادر لا أهداف رفع. التفويض: توحيد الوثائق ثم نشرها والتحقق من SHA والمحتوى ثم شرائح offline صغيرة مختبرة دون انتظار موافقة عامة لمجرد انتهاء التوثيق. لا كود قبل تحقق النشر؛لا حسابات حقيقية أوبيع/نقل أوتشغيل متعدد/غير مراقب ضمن هذا التفويض. لا force push أوحذف تاريخ أوبيانات.

النظام محلي: JVM/GUI/supervisor/processes/storage؛ليس تطبيق Cloudflare Pages. لا نشر ويب ولاHono scaffold مطلوب. الإنتاج وOS/auth/storage قرارات لم تحسم. «تابع» تعني استئناف أول مهمة غير مكتملة بعد فحص الحالة الفعلية،لا افتراض نجاح عملية انقطع اتصالها.

## 2. سجل المصادر والأدلة

H=HISTORICAL_OBSERVED: فحص تاريخي فيM،raw logs القديمة مفقودة. D=DOCUMENT_ANALYSIS: تعارض عقود لاruntime proof. R=REPORTED_UNVERIFIED: ادعاء منR1/R2 يحتاج مصدرًا/اختبارًا مستقلًا. P=PROPOSED: معالجة أوtest غير منفذ. فحوص الحزمة الحالية وحدها تسجل CURRENT_VERIFIED في evidence/validation.json؛لا ترفعclaims إلىverified.

| ID | مصدر التقرير الدائم | SHA-256 التاريخية | أسطر |
|---|---|---|---:|
| M | https://www.genspark.ai/api/files/s/m6P77vEf | 95bf609bd9c885390492217e44250455bfe945d8ac1b5abea3852028f8f07518 | 379 |
| R1 | https://www.genspark.ai/api/files/s/tGhZopMp | f6ca83ceb33897430a7d2b3062eed4a1bd3f62e8678a9ddc98b12d4c5eebf0ba | 209 |
| R2 | https://www.genspark.ai/api/files/s/6TGZpQQN | 81b39952d41cd8d1afff63df4bc1c08abe54e136b60b89dcee9ffca112f15b1c | 263 |
| P | https://www.genspark.ai/api/files/s/2E2egy1W | 39e5da84ac7ccd5069dd257119dc3e0a86a80784c09729a597e922a7dd9639c2 | 316 |

هذه البصمات تطابقت في الاستعادة السابقة قبل فقد الملفات،ولم تُعد تنزيلات التقارير في هذه الاستعادة الأخيرة. raw sources غير مرفقة وقد تتطلب الروابط جلسة المالك. نسخ(2) مطابقة بايتًا تاريخيًا وليست تقارير مستقلة. P خطة مشتقة منM،لا تدقيق مستقل. REF الأربع روابط SHA تاريخية cd59eaf29979543ac3ae18a53c815eafb9f9701aecaeae022b27b8e297ece9e3.

| الرمز | مصدر upstream | revision تاريخي،ليس main الحالي |
|---|---|---|
| O | https://github.com/zizo0022sasa/OSRS_Bot | d98a10ed89fbe52af42f2e70a9fc2e8fffc7c80b |
| U | https://github.com/chsami/Microbot | a2114401bbbc35e9762db9e8aa666d70ffcd24d8 |
| H | https://github.com/chsami/Microbot-Hub | ee6e066e04b29c1e12e554b3f73439217bdc0eed |
| G | https://gist.github.com/wewe00220033/9ee35367b892b836456eb24fd91bfd5d | 497001676deee744940271033908b1dcb19d851e |
| C | https://github.com/belalalibb/chat_engen | cb4ff32e5812931aeb8c7423a88255110c53acf5 |

G قد يحتوي أسرارًا،لا تعِد نشره. D0–D6 تحت O/OSRS_Bot/وثائق_المحركات/: D0=00_المرجع_المعماري_الموحد.md؛D1=01_محرك_عامل_المهمة_Task_Worker_Adapter.md؛D2=02_محرك_إدارة_الحسابات_Accounts_Manager.md؛D3=03_محرك_حارس_التليجرام_والسجلات_Telegram_Logs_Guardian.md؛D4=04_محرك_المايسترو_ومشرف_التشغيل_Master_Orchestrator.md؛D5=05_محرك_الذكاء_الاصطناعي_AI_Triage_Solver.md؛D6=مصفوفة_السكربتات_المفتوحة_وخريطة_المراحل.md.

### الأدلة التاريخية المحددة

- E01/M:F20: 6/8JSON fences فشلت؛D1:25,45؛D2:60,148؛D4:175,256. الصحيحتانD2:172,D4:130. ليس كل مثال رسالة نقل جاهزة.
- E02/M:F12: withdrawX=False أعادSUCCESS،صفرdepositEquipment،وcandidate_names دونname أدىKeyError لأنdefault لـget يقيم مبكرًا. عيب فيالمثال،لا تعميم علىكل التطبيق.
- E03/M:F02: ignore لا يستبعد accounts_database.json/accounts.txt/Root/accounts_database.json/logs/incidents.jsonl؛استبعد.env وRoot/keys.txt. ليس دليل تسرب ملفات.
- E04/M:F29: 15×4×10MB=600MB قبلالصور،لا500MB.
- E05/M:F27: 44mocked unittest ناجحة بلاfail/error/skip والشبكةمحظورة؛ليستJava build أوgame E2E أوtests لـOSRS_ee؛raw outputs فقدت.
- E06/M:F01: نمطTelegram token فيG:822 و1071؛موضعان لايثبتان سرينمختلفين أوصالحين. لم تستخدم الاعتمادات أوتختبر.
- E07/M:F06: U/docs/AGENT_SERVER.md:38–74 يصفloopback/8081 وskip startup عندcollision وX-Agent-Token وملف.agent-token؛enabled default محلخلاف.
- E08/M:F14: PluginDescriptor.java:68–168 لاmin_skills/required_tools/stage_tier؛DynamicScriptDeployHandler:78–118 يحتاجsource directory. لاScriptDescriptor ظهر فيالشجرةالمراجعة.
- E09/M:F10/F20: VarPlayerID.java:130 يعرفTUTORIAL=281 كـVarp؛BankHandler يعيدitems عندopen فقط وopened/closed لبعضالعمليات،لاsuccess موحد.
- E10/M:F12: Rs2Bank.java:512–513 يستدعيhasItem(name,false)،matching ليسexact افتراضيًا.
- E11/M:F14: 172اسمملف ينتهيPlugin.java فيH لا172مهمةصالحة؛170/171 بالمصادر ليستعدادًا معياريًا.
- E12/M:F22: chat completions موثق وauth يمكنتعطيلها؛لم يراجعmultimodal transport مستقلًا.
- E13/M:F11: Wiki/Account ذكر10QP و100total ووقت>20h وOak logs ضمنقيودF2P جديدة؛مرجع مجتمع مؤرخ لاuniversal rule؛حد>20/≥20 يحتاجتحقق.
- E14/M:F06/F27: runner يثبت8081،token read داخل__main__،main=False لايحوّلإلىnonzero؛O/OSRS_Bot/run_stronghold_bot.py:18–21,654–708.

### تحقق المصدر المؤجل

كل V01–V08 NOT_RUN/AUTH_BLOCKED. بعدReconnect ثبتSHA لكلقراءة ولا تنسبmain الجديد إلىrevision قديم.

| ID | الادعاء ومصدره | تحقق مطلوب |
|---|---|---|
| V01 | R2:P0-02: image parts تسقط فيchat_engine/api/openai_compat.py | تتبعtext/compile_payload/canonical/provider؛fake provider يرىالصورةأوunsupported صريح |
| V02 | R2:P0-03: ProxyConfiguration/RuneLite يرفضانURI ويعرضانmodal/exit | schemes/auth/IP probe failure عندSHA؛لاlaunch حي |
| V03 | R2:P0-04: enabledByDefault=false وprofile keys | AgentServerPlugin/Config/docs بنفسSHA؛config persistence قبلseeding |
| V04 | R2:P0-01: telemetry كل5دقائق وflags تعطلها | ScriptErrorReporter وكلegress؛flag واحدةلايثبتdisable شامل |
| V05 | R1:4.1/R2:P0-06: Jagex auth/session | source ووثائق رسمية مؤرخة؛لاجلساتحقيقية |
| V06 | R2:P1-06: LogoutHandler/AutoLoginSuppressionRequest | lifecycle وfake reconnect race |
| V07 | R2:P1-03: لاGE HTTP route | جميعroute registrations لاfilename واحد؛economy مؤجلة |
| V08 | R2:P1-05: cache/hwid-agent | paths/identity exclusions/mutable sharing؛وجودأداةلايثبتanti-ban |

## 3. السجل الموحد واختبارات القبول

35قضية OPEN؛العدد تنظيمي لاجاهزية. U01–U29 تحفظM:F01–F29 صراحة. U30–U35 ستةعقودمستقلة جديدة. كلصف يحددroot risk وحالاته والإصلاح وoracle اختبارTبنفسالرقم. **كلT01–T35 NOT_RUN علىOSRS_ee.** P0 قبل أسرار/أفعال حقيقية؛P1 قبلغيرالمراقب؛P2 قبلالتوسع/الاقتصاد. أولوياتالجديدمؤقتة؛الملاكأدوار.

| ID / أولوية / مالك | خطر ومعالجة | اختبار القبول المقترح | الدليل/الثقة |
|---|---|---|---|
| U01 / P0 / Security+Owner | secret يبقىفعالًا بعدحذفالنص؛GitHub الجديدحادثمنفصل؛إلغاءوتدويروتأكيدمنقح | T01: دليلإلغاءلكلحادث وعدمإعادةنشر؛لاتجربةالسر | M:F01,R2:P0-01,E06؛H عاليةللنمطلاالصلاحية |
| U02 / P0 / Security | plaintext فيstate/Telegram/errors/backups؛refs/aliases وACL/scan لاspoiler | T02: synthetic canary لايظهر فيsinks أوchild غيرمخول؛ignore/tracked files | M:F02,R2:P0-01,E03؛H/D عالية |
| U03 / P0 / Control | chat مسموح/user خاطئ وcallback replay؛RBAC وdurable context approval | T03: wrong user/role/expired/changed plan يرفض؛consume مرة | M:F03؛D عالية |
| U04 / P0 / State+Adapter | A late result يصلB،مشرفان،old worker بعدexpiry؛fencing كامللاslot ID | T04: no effect فيB،مالكواحد،لاbypass قبلreuse | M:F04,R2:P1-01؛D عالية |
| U05 / P0 / AI+Policy | injection/تحذيرخطر/ثقةذاتية؛symbolic ليسsafe؛AI advisory بلاauthority | T05: extra/free action/stale/confidence1 يرفض؛لاexecution path | M:F05,R1:5.1,R2:P1-01؛D عالية،pixel رقمR |
| U06 / P0 / Adapter | collision8081/token/profile/PID أوdisabled Agent؛unique endpoint/identity وV03 | T06: readiness تفشل بلا لمسclient آخر عندwrong binding/default | M:F06,R2:P0-04,E07؛H للتصادم،R للdefault |
| U07 / P1 / Store | effect ثمlost response/crash؛journal قبلdispatch وUNKNOWN/reconcile | T07: faults بكلboundary لاnon-idempotent replay ولاsuccess مخمن | M:F07؛D عالية |
| U08 / P1 / Store | lost update/tmp/disk/Windows sharing/performance writers؛single writer ومعاملات | T08: two writers/kill/disk-full/corruption/restore→valid أوquarantine | M:F08,R1:2.1,R2:P2-02؛D،WinError المطلقمرفوض |
| U09 / P1 / State | crash/2FA button→READY،late/duplicate delta؛CAS/dedupe/cooldown | T09: no double delta أوREADY تلقائية؛reconcile لازم | M:F09؛D عالية |
| U10 / P1 / Adapter | Varp≠Varbit؛closed bank≠0؛reads ليستatomic؛typed quality | T10: missing/stale/namespace error→UNKNOWN/reject لاstage مخمنة | M:F10,E09؛H عالية |
| U11 / P1 / Domain | 7QP/host uptime/fallback oak؛dated capabilities حسبaccount/item | T11: QP7/9/10،level99/100،حد20h/unknown membership يمنعfalse eligibility | M:F11,R2:P1-02,E13؛H محدودة،3h/17h R |
| U12 / P1 / Worker | false/partial withdrawal SUCCESS،KeyError،equipment/ambiguous name؛canonical IDs/postconditions | T12: false/partial/candidate-only/noted/PIN/full bag لاSUCCESS كاذبة | M:F12,R2:P1-03,E02/E10؛H للمثال |
| U13 / P1 / Economy | classifier مفترض،بيعinputs محجوزة،partial GE/replay؛reservations/ledger وبيعمعطل | T13: reserved/unknown/old stock/partial order→no-sale/no double effect | M:F13,R1:4.3,R2:P1-03؛D/H؛V07 R |
| U14 / P1 / Registry | file≠package،metadata/recipe مفترضة،traversal؛reviewed registry/hash/license/compat | T14: dependency/descriptor/resource/hash/path خطأ→quarantine قبلload | M:F14,R2:P0-05,E08/E11؛H جزئية |
| U15 / P1 / Release | runtime pull/mixed versions/rollback mismatch؛immutable staging+approval | T15: build/download/canary/migration fail→compatible rollback أوstop | M:F15,R1:5.2,R2:P1-06؛D عالية |
| U16 / P1 / Supervisor | stop ينتظرbank/HTTP؛kill ليسlogout؛revoke ثمbounded owned escalation | T16: abort معتعليق→no later actions ضمنdeadline؛UNKNOWN إنلاexit proof | M:F16؛D عالية |
| U17 / P1 / Supervisor | stationary=freeze وPID deadlocked/restart storm؛health signals مستقلة | T17: ticks حيةمعسكونلاfreeze؛budgets/circuit breaker تمنعstorm | M:F17؛D عالية |
| U18 / P1 / Capacity | heap=RSS/leak fix وأرقامسعةمفترضة؛قياسRSS/native/GC/CPU/FD/reserve | T18: target ramp/soak/pressure يثبتadmission/stop لاheap estimate | M:F18,R1:2.2,R2:P1-04؛D للمبدأ،R للأرقام |
| U19 / P1 / Network | preflight ثمDNS/IPv6/direct fallback/sticky expiry/quota؛policy واختبارOS | T19: outage/expiry→no forbidden fallback،reason صحيح،no renew خلالUNKNOWN | M:F19,R1:3.1/3.2,R2:P0-03/P1-05؛D/R |
| U20 / P1 / Contracts | JSON/path/plane/status/unit mismatch؛strict schemas وendpoint mapping | T20: valid/invalid fixtures،missing/extra/type/version/bool-as-int؛opened/closed | M:F20,E01/E09؛H عالية |
| U21 / P1 / Scheduler | worker/scheduler/state owners متعددون؛owner واحد/replan لاhidden writes | T21: resource تغيرت/recipe أخرى→Scheduler replan،Store وحدهcommit | M:F21,R2:P2-02؛D عالية |
| U22 / P1 / Gateway | route بلاvision/auth/image drop/cost loop؛V01/capability/budget | T22: unsupported أوصورةتصل،401/429/timeout لاloop أوgame effect | M:F22,R2:P0-02,E12؛H محدود،code R |
| U23 / P1 / Recovery | death/teleport/PIN/2FA تختلط،death loop؛quarantine/re-probe | T23: respawn/أغراضناقصة/2FA غيرمكتملة→no guessed move/READY | M:F23,R1:4.2؛D عالية |
| U24 / P2 / Economy | deposit=profit/old stock=production/USD=revenue؛فصلquantity/cashflow/fees/valuation | T24: deposit profit0،dated fees،partial/replayed events لاdouble count | M:F24,R2:P2-03؛D؛tax/limits R |
| U25 / P2 / Governance | anti-ban/circadian/persona/hwid/AST certainty وIP causation؛facts/hypotheses | T25: كلclaim لهsource/method/bounds أوhypothesis؛لاضمان100% | M:F25,R1:1.1/1.2/1.3,R2:P2-01/P1-05؛D عاليةلحدودالدليل |
| U26 / P1 / Config | zero constants/minmax/units/reload/clock jump؛immutable hash/monotonic waits | T26: invalid config يرفض؛snapshot ثابت وcancellation لاwallclock | M:F26,R1:1.1,R2:P2-01؛D عالية |
| U27 / P1 / Build+QA | 44mocks→live proof،main=False exit0،OS/copies؛pin/fresh checkout | T27: build عندوجودcode،nonzero failure،OS matrix فعليةلاpathlib guarantee | M:F27,R2:P2-04,E05/E14؛H محدود |
| U28 / P2 / Governance | conflicting approved docs/chat authority؛ADR hierarchy/provenance | T28: conflict يوقفالميزة؛source→issue→test→owner trace | M:F28 وخواتيمR1/R2/P؛D عالية |
| U29 / P1 / Logs | outbox/photos/logs تملأdisk،retry storm،حذفincident؛global quotas/reserve | T29: flood/outage/disk-full bounded؛state/stop أولًا؛no dispatch دونintent | M:F29,E04؛H/D |
| U30 / P0 مؤقت / Auth | modern يعاملlegacy وsecret inheritance؛auth_mode وrefs وV05 | T30: UNKNOWN/mismatch/expired ref→no login/no secret leak | R1:4.1,R2:P0-06؛R متوسطة |
| U31 / P0 مؤقت / Privacy | telemetry/error egress غيرمصرح؛inventory وV04 | T31: synthetic collector يرىفقطallowed destinations/data؛flags coverage | R2:P0-01؛R للتفاصيل |
| U32 / P1 مؤقت / Packaging | cache quota/shared mutable/identity contamination؛V08/clean manifest | T32: no identity copy،hash mismatch quarantine،isolated writes/bandwidth measured | R2:P1-05؛R متوسطة |
| U33 / P1 / Supervisor | orphan child/PID reused/lookalike java؛owned groups/start time | T33: kill فقطowned tree؛لاقتلprocess أجنبية أوrelaunch بلاfencing | R1:2.3؛D للمبدأ،OS pending |
| U34 / P1 مؤقت / Adapter | logout ثمautologin/early lease release؛V06/quiescence | T34: reconnect race لايعيدالدخولبعدstop؛exit مثبت | R2:P1-06؛R متوسطة |
| U35 / P1 مؤقت / Network | URI unsupported/modal/exit قبلreadiness؛V02/typed validation | T35: bad URI قبلlaunch،startup deadline/reason منقح؛لاتوكنبالlog | R2:P0-03,R1:3.1؛R متوسطة |

### Crosswalk عكسي دون إسقاط بند

| R1 | أسطر | قضايا | موقف |
|---|---:|---|---|
| 1.1 | 21–27 | U25,U26 | رفضcausal anti-ban؛نافذةراحةاختيارلاحق |
| 1.2 | 31–37 | U25 | jitter/spoofing مؤجلان،لاclustering proof |
| 1.3 | 41–45 | U25,U15 | لاgeneral javac DCE؛mutation خارجMVP |
| 2.1 | 51–61 | U08 | sharding/inbox لاtransaction،ولا5ms شرط |
| 2.2 | 65–71 | U18 | قياسلاheap prescription |
| 2.3 | 75–81 | U33,U16 | owned cleanup لاقتلcommand-text match |
| 3.1 | 89–99 | U19,U35 | parser≠routing؛لا0.001s guarantee |
| 3.2 | 103–108 | U19 | provider expiry لامواعيدعالمية |
| 4.1 | 116–121 | U30,U02 | V05 وsecret refs |
| 4.2 | 125–137 | U23 | لاbank/fallback آمنمفترض |
| 4.3 | 143–148 | U13 | reservations فعليةلاقفلكلeligible pool |
| 5.1 | 156–168 | U05,U22 | symbolic≠safe؛advisory |
| 5.2 | 174–179 | U15 | compile ليسbehavior؛canary حي بإذن |

| R2 | أسطر | قضايا | موقف |
|---|---:|---|---|
| P0-01 | 29–37 | U01,U02,U31 | فصلexposure/design/telemetry؛رفضspoiler/live-token certainty |
| P0-02 | 41–59 | U22 | V01؛quoted code لاfirsthand proof،90% UI غيرمقاس |
| P0-03 | 63–73 | U35,U19 | V02؛sidecar ليسuniversal fail-closed |
| P0-04 | 77–88 | U06 | V03؛لانسخconfig keys قبلتحقق |
| P0-05 | 92–105 | U14,U20 | package/recipe منفصلان؛recipe names تحتاجfixtures |
| P0-06 | 109–119 | U30,U23 | V05؛auth type لاgame capability proof |
| P1-01 | 125–132 | U04,U05,U09 | رفضlive autonomous AI فيMVP |
| P1-02 | 136–145 | U11 | capability لامرحلةوقت؛3h/17h estimates |
| P1-03 | 149–155 | U12,U13 | V07؛yield name وحدهليسprovenance |
| P1-04 | 159–167 | U18 | no guaranteed windows/heap |
| P1-05 | 171–179 | U32,U25,U19 | V08؛cache/identity لاanti-ban |
| P1-06 | 183–191 | U15,U34 | update وautologin خطرانمستقلان |
| P2-01 | 197–204 | U25,U26 | persona/distribution خارجMVP |
| P2-02 | 208–210 | U08,U21 | shared stats single writer/transaction |
| P2-03 | 214–217 | U24,U13 | fees/limits مؤرخة؛USD ليسrevenue أوRWT authorization |
| P2-04 | 221–223 | U27,U18 | OS pending؛25–30% توفيرغيرمقاس |

P:A–G أدخلت تحليليًا في المعمارية والعقود والأمن والخطة،لا ألصقت كمواصفة منافسة. P:200–240 أساسالعقود،242–282 الاختبارات،284–310 مراحلPR؛قيدالانتظارP:314 تاريخي تجاوزهmandate بالحدودالمذكورة. R2 المقدمة5P0/7P1 مقابلجدول6P0/6P1/4P2: تناقضجودةمصدر لاعدادمشروع. لاcase أغلق بالتوثيق وحده.

## 4. القرارات والحسم

| ADR | الحالة | القرار وحده |
|---|---|---|
| ADR-001 | MANDATED | OSRS_ee/main؛حفظالتاريخ؛docs→verified publish→offline |
| ADR-002 | SCOPE_BASELINE | AI advisory بلاaction authority؛لاLIVE_AI_TRIAGE التلقائي |
| ADR-003 | ACCEPTED 2026-10-23 (قرار المالك: «SQLite») | SQLite محلي عبر stdlib `sqlite3`: journal_mode=WAL، synchronous=FULL، foreign_keys=ON، busy_timeout؛ كاتب منطقي واحد (Store)؛ كل انتقال حالة/lease/journal/dedupe في معاملة واحدة؛ backup عبر `Connection.backup` + checksum؛ لا ادعاء durability مطلقة عبر power loss دون اختبار على OS الهدف (ADR-007). JSON مرفوض كأساسي. |
| ADR-004 | SCOPE_BASELINE | supervisor/fake account واحد،Store مالكالحالة وAdapter بوابةوحيدة؛لاJVM reuse |
| ADR-005 | SCOPE_BASELINE | immutable releases،staging/contracts/approval/drain/canary،rollback متوافق |
| ADR-006 | DEFERRED | GE/بيع/نقل/RWT،mutation/spoofing/personas،auto-executable discovery |
| ADR-007 | PROPOSED | production OS وtoolchain غيرمحسومة؛sandbox ليستproduction |
| ADR-008 | PROPOSED | auth_mode/support يثبتبعدV05؛لاجلساتحقيقية |
| ADR-009 | SCOPE_BASELINE | aliases/refs فقط؛لاTelegram password أوspoiler workaround |
| ADR-010 | PROPOSED | sidecar اختياربعدV02/OS network tests؛ليسضمانًا |
| ADR-011 | SCOPE_BASELINE | reported claims تبقىR؛44mocks ليستtarget/live evidence |
| ADR-012 | PROPOSED | migrations versioned/backup/restore/quarantine؛لاREADY افتراضية |
| ADR-013 | ACCEPTED 2026-10-23 | حفظ التقدم: commits محلية على `genspark_ai_developer` + `git bundle` متحقق (verify+SHA-256) يُرفع إلى رابط ملف دائم بعد كل شريحة ويُسجل في PROGRESS/evidence/bundles.md. السبب: مسح sandbox متكرر (4×/يوم)، OAuth غير متاح والمالك لا يعيده كل مرحلة، SB-Git/AI Drive محجوبان (CLI يتطلب خطة مدفوعة؛ /mnt/aidrive غير مركّب). البدائل المرفوضة: توكن منشور في المحادثة (مكشوف)، نشر مبكر إلى main. الأثر: PR مؤجل موثق (PUB-02)؛ الروابط تتطلب جلسة المالك؛ المحادثة هي السجل الخارجي. يُراجع عند توفر OAuth أو خطة. مثبت باختبار استعادة على مستودع تجريبي |

SCOPE_BASELINE قرار هندسي محافظ ضمن التفويض لا موافقةمستخدمعلىكلتفصيل. «تابع» لا تحسمstorage/OS/auth. تعارضAgent default يحسمV03 بنفسSHA؛Windows sharing لايعُم؛heap/Xmx لاRSS؛reservations كميةللخطةلاكلeligible ولاyield name وحده؛sidecar ليسfirewall؛kill ليسserver logout؛javac/JIT ليساanti-ban دليلًا.

السلطة: mandate وحدودالأمان ثمADR معتمديسميمايلغيه ثمهذهالعقودالمتوافقة. التقاريروالشات تاريخلاspec منافسة. تغييريسجلreason/alternatives/owner/scope/tests/migration/rollback. التعارضيوقفالميزةالمتأثرةلاالأعمالالمستقلة.

## 5. المعمارية وحالات التشغيل

Store يملكstate/leases/epochs/journal/dedupe/approvals؛Supervisor owned processes/readiness/drain/budgets؛Scheduler يختارrecipe منsnapshot؛Worker pre/postconditions ويطلبreplan،لايغيرحسابًا/مهمةخفيًا؛Adapter يتفردبidentity/policy/freshness/fencing والإرسال؛Telegram طلباتمخولة/aliases؛AI مقترحاستشاري؛Registry artifacts/recipes مراجعة. لاnetwork داخلtransaction. فصلclasses ليسعزلصلاحيات؛worker قديممعtoken قديتجاوزgate،يجبمنعطريقهقبلreuse،expiry وحدهلايكفي.

Read→decide→durable PREPARED→DISPATCHING قبلnetwork→ACKNOWLEDGED→fresh postcondition→VERIFIED. timeout/crash/lost response فينافذةالإرسال→UNKNOWN. لاnon-idempotent retry قبلreconcile. same commandID/same canonical payload يعيدالنتيجةبلاdispatch؛different payload يرفض. event/delta بمعاملةCAS/dedupe. لاexactly-once claim عبراللعبة.

| من | الحارس | إلى |
|---|---|---|
| NEW | opaque identity وsecret ref صالحان | PENDING_DISCOVERY |
| PENDING_DISCOVERY | exclusive lease وclient binding | DISCOVERING |
| DISCOVERING | required facts KNOWN وcapabilities مثبتة وإنهاءdiscovery session منضبط | READY |
| DISCOVERING | نقصحقائق/أثرمجهول | BLOCKED/RECOVERY_REQUIRED |
| READY | cooldown انتهى،لاincident مانع،admission وlease حصرية | LEASED |
| LEASED | launch binding/config/artifact hashes صحيحة | STARTING |
| STARTING | readiness/identity ولاأمرUNKNOWN متعارض | RUNNING |
| RUNNING | pause/end/update ووقفالجديدوبدءdeadline | DRAINING |
| DRAINING | quiescence/exit مثبت،delta مرة،lease release | RESTING |
| RESTING | انقضاءالراحةوإعادةفحص | READY |
| RUNNING | عائقمعروفوأثر/ملكيةمضبوطان | BLOCKED |
| أيحالةتشغيل/اكتشاف | crash/lease/identity uncertainty وسحبالأفعال | RECOVERY_REQUIRED |
| BLOCKED | approval صالحةعندلزومها | RECONCILING |
| RECOVERY_REQUIRED | منعالقديموبدءمراجعةالأوامر | RECONCILING |
| RECONCILING | الشروطمثبتة | RESTING أوREADY حسبcooldown |
| RECONCILING | تعذرحسم/تطلبauth | RECOVERY_REQUIRED أوBLOCKED |
| أيحالة | disable request/دليلمانع | DISABLED معrevoke/drain،ليستexit proof |

الانتقالغيرالمدرجيرفض. restart لاREADY؛يفحصالعملياتوالsessions المفتوحة والjournal. cooldown لايصفر؛لااستعادةmonotonic timer بينprocesses،أعدdeadline محافظةمنالدائم.

pause يمنعجديدًاويصرفتعاونيًا؛stop_shift يوقفالجدولةويصرفبمهلة؛abort يسحبالسلطةفورًاثمتصعيدللشجرةالمملوكة. لاانتظارbank،لاlater actions بعدabort،لاserver logout ادعائي. liveness/readiness/tick freshness/task progress إشاراتمختلفة؛stationary ليستfreeze. PID+start time+launch record+owned group/Job Object؛لاkill بالنص. budgets/circuit breaker لمنعstorms.

Bank: closed/missing list UNKNOWN؛canonical IDs/noted/charged وeligibility،deposit inventory/equipment حسبrecipe،false/partial withdrawal ليسSUCCESS،verify delta. Death/PIN/2FA/teleport أسبابمختلفة؛لاLumbridge/3items/safe fallback مفترضة. Client endpoint/home/profile/token_ref مستقل؛V03/V05/V06 قبلتكامل. Proxy typed input ثمreadiness،DNS/IPv6/expiry/egress policy علىOS،no unsafe renew خلالUNKNOWN. Cache clean immutable manifest بلاidentity،mutable copies معزولة.

قياسRSS/native/heap/GC/CPU/FD/disk/network علىالهدف؛admission/reserve. logs/photos/outbox bounded count/bytes/age؛لاdispatch إنفشلintent save. release: DETECTED→DOWNLOADED→BUILT→CONTRACT_TESTED→APPROVED→DRAINING→CANARY→ACTIVE؛hash/evidence لكلخطوة؛canary حي بإذن،rollback غيرمتوافق→stop.

## 6. العقود — SPECIFIED_NOT_IMPLEMENTED

S01 ستنفذJSON Schema draft2020-12: required/enums/bounds/additionalProperties:false،رفضunknown version وbool-as-int،opaque IDs،epoch موجب وstate_version غيرسالب،durations بوحداتصريحة،UTC RFC3339 للسجل وmonotonic للمهل. SHA-256 للمحتوىcanonical معتعريفcanonicalization قبلidempotency. schema لايثبتlease/هوية/freshness. params لكلoperation مغلقة لاfree map.

- Account: account_id/alias/auth_mode/credential_ref/proxy_ref/state/state_version/cooldown_until/capabilities. auth_mode UNKNOWN/LEGACY/JAGEX_SESSION لايثبتsupport؛UNKNOWN يمنعlogin.
- SessionLaunch: schema_version/run_id/session_id/account_id/session_epoch/lease_id/lease_expires_at/client_instance_id/task_id/task_descriptor_hash/artifact_hash/config_hash/credential_ref/adapter_endpoint/adapter_token_ref/max_session_seconds/drain_timeout_seconds. endpoint trusted loopback registry لاchat URL؛UDS platform-specific؛PID/start/profile/home binding.
- Observation: observation_id/account_id/client_instance_id/session_epoch/observed_at/state_version/consistency/fields. كلfield quality/source/observed_at/value؛UNKNOWN→null،STALE لايحققحارسًا؛KNOWN مطلوبللفعل. BEST_EFFORT ليسgame atomic revision؛plane canonical وnamespace صريحة.
- CommandIntent: schema_version/command_id/account_id/session_id/client_instance_id/session_epoch/lease_id/expected_state_version/operation/params/precondition_ref/postcondition_ref/issued_at/expires_at/policy_version/config_hash. issued<expires؛fresh state أوre-evaluation؛no conflicting UNKNOWN/abort؛hashes/allowlist صحيحة؛paths canonical بلاtraversal/symlink خارجي/shell.
- Result/Event: schema_version/event_id/command_id/session_id/session_epoch/state_version/transport_status/effect_status/reason_code/evidence_refs/occurred_at. transport=NOT_SENT/ACKNOWLEDGED/REJECTED/TIMEOUT/CONNECTION_LOST؛effect=NOT_ATTEMPTED/UNKNOWN/VERIFIED/FAILED_VERIFIED. REJECTED يثبتno-effect فقطبعقدالمصدر،غيرذلكUNKNOWN؛ACK/timeout ليستVERIFIED/FAILED_VERIFIED. VERIFIED يحتاجevidence بنفسbinding.
- Reasons: NONE/STALE_CONTEXT/POLICY_DENIED/HUMAN_AUTH_REQUIRED/BANK_PIN_REQUIRED/INSUFFICIENT_RESOURCES/PROXY_UNAVAILABLE/CAPABILITY_UNKNOWN/IDENTITY_UNVERIFIED/DEADLINE_EXCEEDED/STORAGE_UNAVAILABLE،مستقلةعنsession status.
- Approval: incident/account/epoch/plan_hash/state_version/approver/expires_at/used_at،استهلاكمرةذريًا؛تغيرcontext يبطلها؛resume→reconcile.
- Artifact/Recipe: revision/hash/license/runtime/entry/dependencies/compatibility،recipe config/capabilities/pre/post منفصلةعنplugin code. Outbox: redacted payload/bytes/attempts/next_retry/expiry معbounds. Reservation/GEOrder نماذجمستقبليةلاترخصأفعالًا.

AIProposal يسمحفقطNO_ACTION/REQUEST_REOBSERVATION/REQUEST_HUMAN_REVIEW،parameters مغلقة،confidence0..1 للتفسيرلاauthority،stale epoch/version يرفض. مثالنحويغيرمنفذ:

```json
{"schema_version":"1.0","incident_id":"incident_demo","account_id":"acc_demo","session_epoch":1,"observed_state_version":7,"diagnosis":"Requires operator review","suggested_action":"NO_ACTION","parameters":{},"requires_human_approval":true,"confidence":0.5}
```

Endpoint matrix لاحقًا تشملrevision/route/method/request/response/domain meanings/idempotency/failure windows/postconditions. لاresult.success موحد؛bank opened/closed. GE V07 غيرمتحقق.

Storage pending: SQLite transactions/constraints/WAL/synchronous بحسبالمنصة،backup/restore؛JSON بديلsingle writer/قفلRMW كامل/unique tmp بنفسfilesystem/flush+fsync حيثمدعوم/replace/journal/checksum/version/previous backup. لاatomic rename ضمانdurability مطلقة.

## 7. الأمن والخصوصية

آخرردمنصةGitHub: Reconnect Required؛لاتكرارsetup أوremote قبلتأكيدالمالكReconnect فيGenspark. الاعتمادالمكشوفلم يستخدمأويحفظ،الإلغاءNOT_CONFIRMED؛لاsecret أوhash لهفيrepository. حذفالنصلايلغيالاعتماد. لاforce push لإعادةكتابةالتاريخبلاخطةوتفويض.

لاpassword/session/proxy credentials فيGit/Telegram/AI/screenshots/logs/state العام؛refs/aliases فقط. 2FA/PIN عبرواجهةرسميةمحلية. لاspoiler+delete workaround. وراثةenvironment أدنىحد،لاsecret CLI args حيثتظهرللعمليات. ignore مساعدلاACL/تشفيرولاحمايةلمتتبع.

كلmessage/callback يفحصuser+chat+role،default deny،لاeval وحدuploads/mعدل. AI يرىبياناتمنقحةبconsent وحدودحجم/عمر/ميزانية/مهلة،لاaction token/shell/files/network authority؛prompt injection لايعدلpolicy. V04 يحصركلegress،flag واحدةلايثبتdisable شامل؛V01 يثبتالصورةأويرفضunsupported. Retry bounded وretry_after،state/stop أولىمنnotifications. plugin داخلJVM ليسsandbox؛allowlist/hash/license/OS permissions.

لاlive قبلإلغاءالأسراروقراراتstorage/OS/auth وإثباتidentity/fencing/journal/recovery وread-only target وإذنpilot. لاanti-ban/أرباحضمان،قواعداللعبةقدتحظرالأتمتة/RWT رغمجودةالهندسة.

## 8. التنفيذ والترحيل ودليل الاختبار

| Slice | مخرج واعتماد | بوابة |
|---|---|---|
| DOC-01/02 | تجميعالمصادر/الأدلةوالسجلوالعقودوالخطة | تغطية29F/13R1/16R2،تمييزH/D/R/P |
| DOC-03 | validate/local commit/archive | فحصفعليوبصماتوحزمةمنقحة |
| AUTH-01/PUB-01 | المالكReconnect ثمsetup وفحصremote الحالي،normal push | SHA وشجرةومحتوىبالSHA متحققة؛لاافتراضremote empty |
| S01 | بعدPUB: schemas/fixtures/pure context guards | T20 وpure T05/T26،لاStore/network/Java |
| S02 | S01+ADR-003 صريح؛Store/leases/journal/dedupe/recovery | T04/T07/T08/T09 معpersistent fake/restore |
| S03 | worker/scheduler/fake adapter/cancellation/health | T16/T17/T21/T29؛concurrency1 |
| VERIFY-01 | بعدAUTH: V01–V08 pinned source | source evidence لالive proof |
| S04 | OS/auth decisions وVذاتصلة وإذنtarget؛owned processes/read-only | T06/T10/T30/T31/T33/T34/T35 |
| S05 | إلغاءالأسرار وإذنpilot؛recipe واحدةمراقبة | T07/T12/T23/T27 وstop plan |
| S06 | Telegram aliases/RBAC/approvals/outbox | T02/T03/T29؛fake أولًا |
| S07 | AI advisory/capabilities/privacy/budget | T05/T22؛لاexecution |
| S08 | release/cache/resource admission | T14/T15/T18/T19/T32؛live canary بإذن |
| S09 | اقتصادبتفويض مستقل | T11/T13/T24؛لاfinancial operations حاليًا |

نقل D0→القرارات/الملكية؛D1→العقود/bank/UNKNOWN؛D2→state/storage/refs؛D3→الأمن/approvals/outbox؛D4→release/identity/resources؛D5→advisory/capabilities؛D6→eligibility/catalog/economy. لا تعديل source repos ولا نسختانحاكمتانمتعارضتان.

قبلcopy كود: revision/license/dependencies ومراجعةمحددة،لاvendor dump. runner hardcoded endpoint/import-time effects/exit code تعالجباختباراتعندترحيلها؛44tests لاtarget حتىتعملعلىtarget commit. لاimport حساباتحقيقيةالآن. storage migration بعدقرار: backup/checksum/restore test،dry-run schema/identity mapping،refs،quarantine ambiguous state،migration_id وtransaction/dedupe؛لاREADY افتراضية. rollback يتطلبdata/protocol compatibility وإلاstop.

لكلtest سجلID/commit/toolchain/platform/fixture/config hash/seed/command/expected/observed/exit/artifacts منقحة. fake oracle مستقل يحصيالأفعالوالهويةوالحالةلاlog SUCCESS. يبقىstore وoracle عبرrestart؛fault points قبل/بعدPREPARED/DISPATCHING/effect/response/verification/event commit/lease release. harness يمنعnetwork game/AI/Telegram؛fake clocks. schema tests لاتثبتdurability؛disk/kill/restore بعدقرارstorage. لاPASS بلاartifact ولاقضيةFIXED بمجردتوثيقها.

Definition of Done لكلslice: requirement→issue→owner→test→observed evidence،diff صغير،negative tests،nosecrets،migration/rollback عنداللزوم،commit/push/verification. القراراتالمفتوحةلاتمنعpure contracts بعدPUB لكنها تمنعالتكاملاتالتيتفترضها.
