# الرفع إلى GitHub والنشر ببورتينر

## ⚠ قبل كل شيء: لا تسجيل دخول في هذا النظام

لا صفحة واحدة تسأل عن هويّة. ولا `login_required` في الكود كلّه.
وهذا كان قراراً واعياً حين كانت الواجهة على شبكتك المحلّية.

**والخادم شيءٌ آخر.** من يعرف العنوان يستطيع:

- قراءة صفقاتك ومحفظتك وكل ما مسحه النظام
- تغيير الإعدادات وحدود المخاطرة
- تشغيل المسح والتدريب — أي استهلاك مفاتيحك عند Alpaca و Claude
- حظر الرموز وتعديل المهامّ المجدولة

ولهذا `WEB_BIND` افتراضه `127.0.0.1`: المكدّس يعمل، والواجهة
**غير مرئيّة من خارج الخادم**. ومخرجان:

**١) نفق SSH — الأبسط، وابدأ به**

```bash
ssh -L 8000:127.0.0.1:8000 user@server
```

ثمّ افتح `http://127.0.0.1:8000` على جهازك. لا شيء مكشوف، ولا
شهادة تُدار، ولا كلمة مرور إضافية.

**٢) وكيل عكسيّ — Nginx Proxy Manager وغيره**

وهو الأنظف: **لا تنشر المنفذ على المضيف أصلاً**. ضع NPM والماسح
على شبكة Docker واحدة، ووجّه NPM إلى `market-scanner-web-1:8000`
مباشرةً. فلا يُفتح شيء على الإنترنت إلّا عبر الوكيل.

وفي بورتينر: `Networks` ← أنشئ شبكة (`proxy` مثلاً) ← أضف إليها
حاويتَي NPM و`web`. ثمّ في NPM:

| الحقل | القيمة |
|---|---|
| Forward Hostname | `market-scanner-web-1` |
| Forward Port | `8000` |
| Websockets Support | مفعَّل (البثّ الحيّ) |

**وثلاثة إعدادات لازمة مع أيّ وكيل:**

```
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,scanner.example.com
TRUST_PROXY=1
DJANGO_CSRF_TRUSTED_ORIGINS=https://scanner.example.com
```

**و`DJANGO_ALLOWED_HOSTS` لا يغني عنه الوكيل.** NPM يمرّر ترويسة
`Host` كما هي — النطاق العامّ — وDjango يقارنها بقائمته ويردّ
`Bad Request (400)`. فالوكيل يتحكّم بمن **يصل**، وهذه بأيّ اسمٍ
**يُقبَل**: حارسان في طبقتين.

**و`TRUST_PROXY=1` يمنع عطباً يصعب تشخيصه:** الوكيل يُنهي TLS
ويمرّر الطلب بـ HTTP، فلا يعرف Django أنّ الأصل كان HTTPS. فتُفتح
الصفحات وتُقرأ — **ويفشل كل زرّ بـ 403**، لأنّ الطلب يحمل
`Origin: https://…` وDjango يظنّ أصله `http://`. ولا رسالة تقول
ذلك.

> ولا تجعلها `1` بلا وكيلٍ أمامك: الترويسة يرسلها أيّ زائر،
> فيوهم Django بأنّ اتّصاله مؤمَّن.

**٣) وكيل عكسيّ بكلمة مرور** — إن أردت الفتح من الجوّال. مثال
بـ Caddy، يُنشر كمكدّس ثانٍ في بورتينر:

```
scanner.example.com {
    basicauth {
        nasser <هاش-كلمة-المرور>
    }
    reverse_proxy market-scanner_web_1:8000
}
```

والهاش يُولَّد بـ `docker run --rm caddy caddy hash-password`.
وحينها يبقى `WEB_BIND=127.0.0.1` — يصل Caddy إليه عبر شبكة
Docker، ولا يصل الإنترنت مباشرةً.

**ومع الوكيل يبقى `WEB_BIND=127.0.0.1`** — أو لا تنشر المنفذ
أصلاً. و`0.0.0.0` تفتح التطبيق مباشرةً متجاوزةً الوكيل.

---

## ١) أنشئ المستودع على GitHub

المستودع جاهزٌ محلّياً، وكل شيء مسجَّل. ما بقي هو الرفع:

```powershell
# أنشئ مستودعاً **خاصّاً** على github.com — لا عامّاً.
# الكود لا يحمل مفاتيح، لكنّه يحمل استراتيجيتك كاملة.

git remote add origin https://github.com/<اسمك>/market-scanner.git
git push -u origin main
```

**ما لا يُرفع** — يمنعه `.gitignore`: ملفّ `.env` ونسخه
الاحتياطية، وقاعدة SQLite، ومجلّد `data/` (٤٤٨ ميغابايت من
الشموع)، و`reports/`.

**وتحقّق قبل الدفع** أنّ ما سيُرفع نظيف:

```powershell
git ls-files | Select-String "^\.env"
```

يجب أن يُظهر `.env.example` و`.env.docker.example` **فقط**.

---

## ٢) جهّز المتغيّرات

ولّد كلمة مرور القاعدة على جهازك:

```powershell
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
```

احتفظ بها. ستلصقها في بورتينر بعد قليل.

> **والمفتاح السرّي لا تحتاج ضبطه.** يُولَّد عند أوّل إقلاع
> ويُحفظ في وحدة البيانات، فيثبت بين الإقلاعات وبين عمّال
> gunicorn الثلاثة. واضبطه فقط إن أردت مفتاحاً بعينه.

وقائمة المتغيّرات كاملةً في `.env.docker.example` — وهي **نفسها**
في الحالتين: `.env` محلّياً، وخانة البيئة في بورتينر.

---

## ٣) أنشئ الـStack في بورتينر

`Stacks` ← `Add stack` ← اسم `market-scanner` ← تبويب
**`Repository`**:

| الحقل | القيمة |
|---|---|
| Repository URL | `https://github.com/<اسمك>/market-scanner` |
| Repository reference | `refs/heads/main` |
| Compose path | `docker-compose.yml` |
| Authentication | فعّله للمستودع الخاصّ، بـ Personal Access Token |

**والرمز يحتاج صلاحية `repo` وحدها.** أنشئه من
`GitHub → Settings → Developer settings → Personal access tokens`،
واجعل له تاريخ انتهاء.

ثمّ في **`Environment variables`** اضغط `Advanced mode` والصق:

```
POSTGRES_PASSWORD=<ما ولّدته>
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,<عنوان خادمك>
WEB_BIND=127.0.0.1
WEB_PORT=8000
SCANNER_TIMEZONE=Asia/Riyadh
AUTO_SCAN_MARKETS=crypto,us,saudi
SEED_JOBS=1
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
SAHMK_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ANTHROPIC_API_KEY=
```

ثمّ `Deploy the stack`.

**البناء الأوّل يستغرق ٥–١٠ دقائق** — يثبّت pandas و numpy و
LightGBM. ولا تقلق إن بدا متوقّفاً.

---

## ٤) تحقّق

في بورتينر: `Containers` — ثلاث حاويات، وحالة `web` يجب أن
تصير **healthy** خلال دقيقة من إقلاعها.

ومن طرفية الخادم:

```bash
curl -s localhost:8000/healthz/          # ok
docker logs market-scanner-web-1 | tail -30
docker logs market-scanner-scheduler-1 | tail -20
```

ثمّ من جهازك: `ssh -L 8000:127.0.0.1:8000 user@server` وافتح
`http://127.0.0.1:8000`.

---

## ٥) انقل بياناتك الحالية

الخادم يبدأ فارغاً: قاعدةً بلا صفوف، ووحدةَ بيانات بلا شمعة.
وعندك ٢٤٬٦٧٩ صفّاً و١٫١٢ غيغابايت من الملفّات.

**الإجراء كلّه في [SHIP.md](SHIP.md).** ثلاثة أوامر:

```powershell
python tools_ship.py                                  # حزمة 150 م.ب
scp -r ship user@server:~/scanner-ship
ssh user@server 'bash ~/scanner-ship/docker-restore.sh ~/scanner-ship'
```

السكربت يوقف `web` و`scheduler`، وينسخ ما على الخادم للتراجع،
ويستعيد، ويفكّ الشموع في الوحدة، **ثمّ يعدّ كل جدولٍ ويقارنه**
بالعدد المتوقَّع — ويخرج بخطأ إن اختلف واحد.

> وشرطُه أن تكون قد رحّلت محلّياً إلى PostgreSQL أوّلاً:
> [POSTGRES.md](POSTGRES.md).

**ولا تحذف قاعدتك القديمة** حتى يعمل الخادم أسبوعاً كاملاً.
هي سجلّ ٧٢١ صفقة وعمل أشهر.

---

## ٦) التحديث بعد تعديل الكود

```powershell
git push
```

ثمّ في بورتينر: الـStack ← `Pull and redeploy`.

ويمكن تفعيل `Automatic updates` بـ webhook فيتحدّث مع كل دفع —
لكنّ ذلك يعني أنّ خطأً تدفعه يصل الإنتاج فوراً. شغّل
`python run_checks.py` قبل كل دفعة.

**والتراجع:** بدّل `Repository reference` إلى وسمٍ سابق ثمّ
`Pull and redeploy`. وهذا وحده سببٌ كافٍ لوسم كل نشرة:

```powershell
git tag -a v1 -m "أوّل نشر"
git push --tags
```

---

## ⚠ اضبط فترات المهامّ بعد أوّل إقلاع

جدولك **مُشبَع**: `scan:us` تستغرق نحو ١٢ دقيقة للفريم الواحد
وصارت على فريمين، و`market_sync` وسيطها ١٨ دقيقة وفترتها ١٠.

من `/jobs/` بعد الإقلاع:

| المهمّة | الفترة الحالية | اجعلها |
|---|---|---|
| `scan:us` | ١٥ دقيقة | ساعة |
| `scan:crypto` | ١٥ دقيقة | ٣٠ دقيقة |
| `scan:saudi` | ١٥ دقيقة | ساعة |
| `market_sync` | ١٠ دقائق | ٣٠ دقيقة |
| `settlement` | ٣ دقائق | ١٥ دقيقة |

وبلا هذا تبقى أغلب المهامّ «تُتخطّى» — وهو ما يجعل السوق
السعودي عملياً بلا مسح.

---

## الأعطال المتوقّعة

**`env file not found`** — لن تقع الآن: `docker-compose.yml` لم
يعد يستعمل `env_file`. وإن رأيتها فأنت تنشر نسخةً قديمة من
المستودع.

**`required variable ... is missing a value`** — لن تقع الآن:
أُزيلت صيغة `${VAR:?}` من `docker-compose.yml`. كانت تُفحص وقت
**تفسير** الملفّ — قبل أن تُبنى صورة أو تُقلع حاوية — فتُسقط
النشر كلّه، ولو كان الخلل في كيفية إدخال المتغيّر لا في غيابه.

والتحقّق صار داخل الحاوية: إن نقص متغيّر تقلع ثمّ تتوقّف، وسجلّها
يقول **أيّها** ناقص وأين يُكتب:

```bash
docker logs market-scanner-web-1
```

وإن رأيت الرسالة القديمة رغم ذلك فأنت تنشر نسخةً قديمة من
المستودع — ادفع التحديث ثمّ `Pull and redeploy`.

**الحاويات تُعاد باستمرار والسجلّ يقول «متغيّرات ناقصة»** —
المتغيّرات لم تصل النشر. والسجلّ يعرض الآن **ما وصل الحاوية
فعلاً**، فانظر إليه أوّلاً:

```bash
docker logs market-scanner-web-1 | tail -30
```

فإن كانت القيم المعروضة كلّها افتراضية وما كتبتَه غائب، فالسبب
أحد اثنين:

**١) المكدّس `Limited / created outside Portainer`.** بورتينر لا
يملكه، فلا يمرّر إليه متغيّراته. أزله من طرفية الخادم ثمّ أنشئه
من جديد — انظر الفقرة أعلاه.

**٢) المتغيّرات لم تُحفظ.** افتح الـStack ← `Environment variables`
ويجب أن تراها **في الجدول** اسماً وقيمة. وإن لصقتها في
`Advanced mode` فاضغط زرّ العودة إلى الوضع البسيط **قبل** الحفظ،
وتأكّد أنّها ظهرت. ثمّ `Update the stack`.

> والمطلوب الآن **اثنان**: `POSTGRES_PASSWORD` و
> `DJANGO_ALLOWED_HOSTS`. والمفتاح السرّي يُولَّد تلقائياً.

**`Database is uninitialized and superuser password is not
specified`** — من حاوية `db`: كلمة مرور القاعدة فارغة. أضف
`POSTGRES_PASSWORD` وأعد النشر.

**`image "market-scanner:latest": already exists`** — لن تقع الآن.
كانت خدمتا `web` و`scheduler` تحملان `build:` و`image:` **نفسه**،
و‏Compose يبني ما له `build` بالتوازي — فتحاول عمليّتان كتابة
الوسم نفسه في اللحظة نفسها.

والصورتان متطابقتان أصلاً: السياق واحد والـ`Dockerfile` واحد،
والفرق `command` وحده. فصار `web` يبني، و`scheduler` يشير إلى ما
بناه.

وإن بقيت الرسالة، احذف الصورة العالقة من محاولةٍ سابقة:

```bash
docker image rm market-scanner:latest
```

ثمّ `Pull and redeploy`.

**`dependency failed to start: container ... is unhealthy`** — لن
تُسقط النشر الآن: لم تعد الخدمات معلَّقةً على فحص صحّة القاعدة.
تُقلع الحاويات، وينتظر `web` القاعدة بنفسه أربع دقائق، ويكتب في
سجلّه ما ينتظره وما يُفعل إن طال.

**والقاعدة لا تُقلع** — اقرأ سجلّها، هي التي تعرف:

```bash
docker logs market-scanner-db-1
```

وأشيع سببين:

**١) `POSTGRES_PASSWORD` فارغ.** صورة postgres ترفض إنشاء قاعدة
بلا كلمة مرور، وتقول:

```
Database is uninitialized and superuser password is not specified
```

**٢) وحدة تخزين من محاولةٍ سابقة.** القاعدة تُنشأ **مرّة واحدة**
بأوّل كلمة مرور، وتغييرها بعد ذلك لا يغيّر القاعدة — يمنع
الاتّصال بها فقط. فإن كنت جرّبت النشر بكلمة مرورٍ ثمّ غيّرتها،
احذف الوحدة وابدأ نظيفاً:

```bash
docker compose -p market-scanner down
docker volume rm market-scanner_pgdata
```

⚠ وهذا يحذف القاعدة كلّها — لا تفعله إن كنت نقلت بياناتك إليها.

**٣) القرص ممتلئ.** `df -h` على الخادم.

**المكدّس يظهر `Limited` و«This stack was created outside of
Portainer»** — بورتينر يرى حاوياتٍ تحمل وسم المشروع
`market-scanner` لكنّه لم يُنشئها، فلا يملك حذفها ولا تحديثها.

وهذا يقع بعد محاولة نشرٍ فاشلة: الحاويات تُنشأ ثمّ يسقط النشر،
فيبقى سجلّها بلا مكدّس يملكه. وهي التي تحجز المنفذ بعد ذلك.

**ولا يُحلّ من الواجهة — يُحلّ من طرفية الخادم:**

```bash
# ماذا بقي فعلاً
docker ps -a --filter label=com.docker.compose.project=market-scanner

# أزل الحاويات والشبكة — ووحدات التخزين تبقى
docker compose -p market-scanner down --remove-orphans
```

فإن لم يعمل الأمر (لا ملفّ compose في المجلّد الحالي):

```bash
docker rm -f $(docker ps -aq \
  --filter label=com.docker.compose.project=market-scanner)
docker network rm market-scanner_default 2>/dev/null
```

ثمّ في بورتينر: احذف المكدّس `Limited` من القائمة إن بقي، وأنشئه
من جديد كما في الخطوة ٣.

**⚠ وإن كنت جرّبت النشر بكلمات مرورٍ مختلفة**، احذف وحدة القاعدة
أيضاً قبل أن تعيد — فهي تُنشأ **مرّة واحدة** بأوّل كلمة مرور،
وتغييرها بعدها يمنع الاتّصال ولا يغيّرها:

```bash
docker volume rm market-scanner_pgdata
```

وهذا آمنٌ ما دمت لم تنقل بياناتك إليها بعد.

**`Bind for 0.0.0.0:8000 failed: port is already allocated`** —
شيءٌ آخر على الخادم يحجز المنفذ. وبعد محاولات نشرٍ فاشلة يكون
غالباً **حاويةً باقية من محاولةٍ سابقة**.

اعرف ما يحجزه:

```bash
docker ps -a --filter publish=8000
sudo ss -tlnp | grep :8000
```

فإن كانت حاويةً من هذا المكدّس، أزل المكدّس كلّه ثمّ أعد النشر:

```bash
docker compose -p market-scanner down --remove-orphans
```

> `down` وحده لا يحذف وحدات التخزين — بياناتك تبقى. والحذف يحتاج
> `-v` صراحةً.

وإن كان خدمةً أخرى تحتاجها، غيّر المنفذ بدل أن تقتلها: في
بورتينر ← `Environment variables` ← `WEB_PORT=8080` ← أعد النشر.

**⚠ ولاحظ `0.0.0.0` في الرسالة:** تعني أنّ `WEB_BIND` عندك
`0.0.0.0` — أي أنّ الواجهة ستكون مفتوحةً للإنترنت كلّه، **بلا
تسجيل دخول**. اقرأ أوّل هذه الوثيقة قبل أن تُكمل.

**`/app/docker-scheduler.sh: Permission denied`** — لن تقع الآن.
كان `chmod +x` في `Dockerfile` يذكر نقطة الدخول وحدها، فعملت
وبدا كل شيء سليماً — ثمّ سقط المجدول وحده وأُعيد بلا توقّف.

والسبب أنّ Git لا يحفظ بتَّ التنفيذ على ويندوز: الملفّات تصل
الصورة بوضع `644`. فصار `chmod +x /app/docker-*.sh`، وضُبط
البتّ في Git أيضاً لمن يشغّلها بلا Docker.

**`Bad Request (400)`** — عنوان الخادم غير مذكور في
`DJANGO_ALLOWED_HOSTS`. أضفه وأعد النشر.

**اللوحة بلا نمطٍ ولا رسوم** — فشل `collectstatic`. اقرأ
`docker logs market-scanner-web-1 | head -40`.

**الحاوية `unhealthy`** — `/healthz/` يسأل القاعدة. تحقّق أنّ
`db` تعمل وأنّ كلمة المرور في المتغيّرات تطابق التي أُنشئت بها
القاعدة أوّل مرّة. وتغيير `POSTGRES_PASSWORD` بعد الإنشاء **لا**
يغيّر القاعدة — يمنع الاتّصال بها فقط.

**كل مهمّة تعمل مرّتين** — مجدولان. `docker ps` يجب أن يُظهر
حاوية `scheduler` **واحدة**.

**المجدول يعيد التشغيل باستمرار** — اقرأ سجلّه. الأرجح أنّ
الهجرات لم تكتمل: `RUN_MIGRATIONS=0` فيه عمداً، وهو ينتظر الويب.

**القرص يمتلئ** — السجلّات محدودة بـ 20م × 5 لكل خدمة. والمتبقّي
غالباً `data/` (الشموع). و`docker system prune -a` يحذف الصور
القديمة لا البيانات.
