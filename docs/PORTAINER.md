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

**٢) وكيل عكسيّ بكلمة مرور** — إن أردت الفتح من الجوّال. مثال
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

**لا تضع `WEB_BIND=0.0.0.0` قبل أن تفعل أحدهما.**

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

ولّد المفتاح السرّي وكلمة مرور القاعدة على جهازك:

```powershell
python -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50))"
python -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))"
```

احتفظ بهما. ستلصقهما في بورتينر بعد قليل.

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
DJANGO_SECRET_KEY=<ما ولّدته>
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

الخادم يبدأ بقاعدةٍ فارغة. ولنقل الـ١٣٬٢٩٠ صفّاً التي عندك،
اتّبع `docs/POSTGRES.md` للترحيل المحلّي أوّلاً، ثمّ:

```powershell
pg_dump -U postgres -d scanner -Fc -f scanner.dump
scp scanner.dump user@server:~/
```

وعلى الخادم:

```bash
docker cp ~/scanner.dump market-scanner-db-1:/tmp/
docker exec market-scanner-db-1 pg_restore -U scanner -d scanner \
    --no-owner --clean --if-exists /tmp/scanner.dump
```

**والشموع لا تُنقل** — ٤٤٨ ميغابايت تُبنى من جديد مع أوّل
مزامنة. وإن أردت توفير وقت المزامنة الأولى فانسخها إلى الوحدة:

```bash
docker cp ./data/. market-scanner-web-1:/app/data/
```

**ولا تحذف قاعدتك القديمة** حتى يعمل الخادم أسبوعاً كاملاً.
هي سجلّ ٦٢٤ صفقة وعمل أشهر.

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

**`required variable DJANGO_SECRET_KEY is missing`** — لم تُلصق
المتغيّرات في خانة البيئة، أو لصقتها بعد الضغط على Deploy.

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
