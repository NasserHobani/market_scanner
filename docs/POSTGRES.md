# الانتقال إلى PostgreSQL — ببياناتك كاملة

## ما سيُنقل

قِيس على قاعدتك الآن:

| الجدول | الصفوف |
|---|---:|
| `scanresult` | 15,965 |
| `watch` | 2,957 |
| `jobrun` | 1,563 |
| `pesdetection` | 1,250 |
| `signalalert` | 776 |
| `trade` | 716 |
| `scanrun` | 559 |
| `company` | 327 |
| `setting` | 66 |
| `blockedsymbol` | 29 |
| `scheduledjob` | 10 |
| `papertrade` | 3 |
| `paperaccount` | 1 |
| **المجموع** | **24,222** |

ثلاثة عشر جدولاً، وكلّها مغطّاة — والأمر **يرفض التشغيل** إن ظهر
نموذجٌ بلا موضعٍ في ترتيب النقل، فلا يبقى جدولٌ خلفه بصمت.

**وما لا يُنقل:** الشموع ولقطات الميزات وقياسات الانضغاط — ملفّات
في `data/` لا صفوف في القاعدة، وتعمل كما هي بلا تغيير.

---

## لماذا PostgreSQL

‏SQLite يسمح بكاتبٍ **واحد**. ونظامك فيه المسح والحسم والمزامنة
وسجلّ الرصد يكتبون معاً — وهذا مصدر كل رسائل «القاعدة مقفلة»
التي رأيتها. والانتقال يزيل القيد من أصله.

**لكنّه لا يحلّ الإشباع:** المهامّ ستبقى تتزاحم على قفل المسح
الواحد إن بقيت فتراتها أقصر من مددها. اضبطها من `/jobs/`.

---

## ١) شغّل قاعدةً محلّية

بلا تثبيت شيء على ويندوز — القاعدة في حاوية:

```powershell
docker compose -f docker-compose.localdb.yml up -d
docker compose -f docker-compose.localdb.yml ps    # حتى تصير healthy
```

المنفذ **5433** لا 5432، كي لا يصطدم بـ PostgreSQL مثبَّتٍ عندك
أصلاً.

> إن كان لديك PostgreSQL مثبَّت وتفضّله، أنشئ القاعدة يدوياً:
> ```sql
> CREATE DATABASE scanner ENCODING 'UTF8' TEMPLATE template0;
> ```
> وعدّل `POSTGRES_PORT` أدناه إلى 5432.

---

## ٢) أوقف كل ما يكتب

**هذه الخطوة ليست اختيارية.** النقل أثناء الكتابة يترك صفوفاً لم
تُنقل، بلا إنذار.

أغلق خادم Django، وضع في `.env`:

```
SCHEDULER_ENGINE=off
```

---

## ٣) وجّه المشروع إلى PostgreSQL

أضف إلى `.env`:

```
POSTGRES_DB=scanner
POSTGRES_USER=scanner
POSTGRES_PASSWORD=scanner_local_dev
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5433
```

بمجرّد وجود `POSTGRES_DB` يتحوّل المشروع إليها — ويضيف اتّصالاً
ثانياً باسم `legacy` إلى ملفّ SQLite، للترحيل وحده.

ثبّت المشغّل إن لم يكن مثبّتاً:

```powershell
pip install "psycopg[binary]>=3.1"
```

---

## ٤) انقل

```powershell
python web\manage.py migrate                      # ينشئ الجداول فارغة
python web\manage.py migrate_to_postgres --check  # الأعداد، بلا كتابة
python web\manage.py migrate_to_postgres          # النقل
python web\manage.py migrate_to_postgres --verify # المقارنة بعده
```

`--verify` يطبع جدولاً بالجانبين وعلامةً لكل سطر. دليلٌ لا انطباع.

**ثمّ شغّل الفواحص على القاعدة الجديدة:**

```powershell
python run_checks.py
```

---

## لماذا نسخٌ مباشر لا `dumpdata`

الطريق المعتاد فيه ثلاثة مزالق في مشروعك تحديداً:

**الترميز.** `dumpdata > file` على ويندوز يمرّ عبر أنبوب، وPython
يختار ترميز المخرَج من **نوعه** لا محتواه — cp1252 — فينهار على
أوّل حرف عربي. وبياناتك عربية كلّها.

**التسلسلات.** PostgreSQL لا يحرّك عدّاد الجدول عند إدراج صفٍّ
بمفتاح صريح. فلو نُقلت ٧١٦ صفقة بمفاتيحها ولم يُضبط العدّاد لبدأ
من ١ واصطدم أوّل حفظ جديد بمفتاحٍ موجود — **بعد الترحيل بساعات
لا عنده**. الأمر يضبطها في نهايته بأداة Django نفسها.

**`contenttypes`** التي ينشئها `migrate` تصطدم بـ `loaddata`.

فالنقل مباشر: قراءةٌ من `legacy` وكتابةٌ في `default` في عملية
واحدة، على دفعاتٍ من ٥٠٠ صفّ.

---

## ودمج سجلّ WAL

قاعدتك تعمل بـ `journal_mode=WAL`: الكتابات تذهب إلى ملفٍّ جانبيّ
`dashboard.sqlite3-wal` وتُدمَج في الأصل لاحقاً. **وفيه الآن ٤٫١
ميغابايت غير مدموجة.**

القراءة تراها، فالنقل سليم. لكنّ الخطر في النسخ: من ينسخ
`dashboard.sqlite3` وحده — احتياطاً أو نقلاً إلى خادم — يفقد كل
ما في `-wal` بلا أن يظهر شيء. الملفّ يُفتح، والجداول موجودة،
والصفوف الأخيرة ناقصة.

فالأمر يدمجه قبل القراءة، ويقول ذلك في مخرَجه. وإن قال «تعذّر
الدمج — كاتبٌ آخر يعمل» فالخادم ما زال شغّالاً: أوقفه وأعد.

---

## ٥) وإلى الخادم

بعد أن تعمل محلّياً أسبوعاً:

```powershell
docker exec scanner-localdb pg_dump -U scanner -d scanner -Fc > scanner.dump
scp scanner.dump user@server:~/
```

وعلى الخادم:

```bash
docker cp ~/scanner.dump market-scanner-db-1:/tmp/
docker exec market-scanner-db-1 pg_restore -U scanner -d scanner \
    --no-owner --clean --if-exists /tmp/scanner.dump
```

---

## التراجع

احذف أسطر `POSTGRES_*` من `.env` وأعد التشغيل. يعود المشروع إلى
SQLite فوراً.

**وملفّ SQLite لا يُمسّ ولا يُحذف** — الأمر يقرأ منه ولا يكتب
فيه. احتفظ به **شهراً على الأقلّ**: هو سجلّ ٧١٦ صفقة وعمل أشهر،
وأيّ خلل يظهر بعد أسبوعين تعود إليه.

---

## الأعطال المتوقّعة

**`لا اتّصال بالقاعدة القديمة`** — `data/dashboard.sqlite3` غير
موجود، أو `POSTGRES_DB` غير مضبوط في `.env`.

**`القاعدة الأساسية ليست PostgreSQL`** — `.env` لم يُقرأ. تأكّد
أنّك تشغّل من جذر المشروع.

**`الجداول الهدف غير فارغة`** — نقلٌ سابق تمّ جزئياً. أفرغ
القاعدة وأعد:

```powershell
docker compose -f docker-compose.localdb.yml down -v
docker compose -f docker-compose.localdb.yml up -d
python web\manage.py migrate
```

**`connection refused`** — الحاوية لم تصر `healthy` بعد، أو
المنفذ في `.env` ليس 5433.

**أعداد مختلفة في `--verify`** — لم تُوقف الكتّاب. أوقف كل شيء
وأعد النقل على قاعدةٍ فارغة.
