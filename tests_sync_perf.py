# -*- coding: utf-8 -*-
"""عنق المزامنة — وكان القرص لا الشبكة.

═══ ما كان ═══

لكل زوجٍ في الدورة، حتى حين لا شيء يُجلَب:

    ١. ``load_market`` يفتح YAML ويحلّله
    ٢. ``storage.load`` يقرأ ويحلّل ١٥٠٠ شمعة (18.76ms مقيسة)
    ٣. ``status_store.update_pair`` يقرأ ملفّ الحالة **كاملاً**،
       يعدّل مفتاحاً، ويعيد كتابته كاملاً — تحت قفلٍ واحد

والثالث هو الأسوأ: الملفّ يحمل **كل** الأزواج (١٥٨٨ في السجلّ).
فدورةٌ على خمسة آلاف زوج تعني خمسة آلاف قراءةٍ وكتابةٍ لملفٍّ
بميغابايتات — عملٌ تربيعيّ، وغيغابايتات من الإدخال والإخراج.

والقفل يُسلسل الخيوط العشرة، فلا تنفع في هذا الجزء أصلاً.

═══ ولماذا لم يُلاحَظ ═══

«المزامنة بطيئة» تُفسَّر بالشبكة تلقائياً. فرُفعت الخيوط وقُلّلت
الرموز — وكلاهما علاجٌ لعَرَضٍ ليس هو السبب.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.market_sync import status_store as ST  # noqa: E402
from scanner.market_sync.config import MarketSyncConfig  # noqa: E402
from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

SVC = ROOT / "scanner" / "market_sync" / "service.py"
code = code_of(SVC)
src = source_of(SVC)


# ═══════════ ١) الكتابة تُجمَّع ═══════════
st_code = code_of(ROOT / "scanner" / "market_sync" / "status_store.py")
st_src = source_of(ROOT / "scanner" / "market_sync" / "status_store.py")
c("١ واجهة التجميع", "def batch_begin" in st_code
  and "def batch_flush" in st_code)
c("  والمفرد يبقى فورياً", "if _BUFFERING:" in st_code)
c("  والسبب موثَّق", "عملٌ تربيعيّ" in st_src)
c("  والقفل يُسلسل الخيوط", "يُسلسل الخيوط العشرة" in st_src)

# وتعمل فعلاً — لا بقراءة المصدر وحدها
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "status.json"
    cfg = MarketSyncConfig(status_path=str(path))

    ST.batch_begin()
    for i in range(50):
        ST.update_pair("crypto", f"S{i}USDT", "4h", {"mode": "t"},
                       config=cfg)
    # ═══ لا يُكتَب شيء قبل الإفراغ ═══
    c("  ولا كتابة قبل الإفراغ", not path.exists(), "كُتب مبكّراً")
    n = ST.batch_flush(config=cfg)
    c("  والإفراغ يكتب الكلّ", n == 50, str(n))
    c("  والملفّ وُجد", path.exists())

    data = ST.load_status(cfg)
    c("  والأزواج محفوظة", len(data.get("pairs") or {}) == 50,
      str(len(data.get("pairs") or {})))

    # وبعد الإفراغ يعود المفرد فورياً
    ST.update_pair("crypto", "ZUSDT", "4h", {"mode": "t"}, config=cfg)
    c("  والمفرد بعده يُكتب فوراً",
      "crypto|ZUSDT|4h" in (ST.load_status(cfg).get("pairs") or {})
      or len(ST.load_status(cfg).get("pairs") or {}) == 51)

    # وإفراغٌ بلا تجميع لا يرمي
    c("  والإفراغ الفارغ آمن", ST.batch_flush(config=cfg) == 0)


# ═══════════ ٢) التجميع يُفرَغ ولو رمى شيء ═══════════
#
# تجميعٌ يبقى مفتوحاً يبتلع كل تحديثٍ بعده بلا كتابة — وهو أسوأ
# من البطء: بياناتٌ تُزامَن ولا تُسجَّل.
sm = code.split("def sync_market")[1][:2000] if "def sync_market" in code else ""
c("٢ التجميع يبدأ", "status_store.batch_begin()" in sm, sm[:120])
c("  ويُفرَغ في ‎finally‎",
  ("finally:" in sm and "batch_flush" in sm
   and sm.index("finally:") < sm.index("batch_flush")), sm[-300:])
c("  وسببه مكتوب", "يترك التجميع" in src)


# ═══════════ ٣) الذيل قبل الملفّ كاملاً ═══════════
c("٣ فحصٌ رخيص قبل القراءة", "def _skip_if_current" in code)
_sk = code.split("def _skip_if_current")[1][:1400]
c("  يقرأ الذيل", "last_time_on_disk" in _sk)
c("  ولا يحمّل الملفّ", "storage.load" not in _sk)
# ═══ والشكّ يُسقِط إلى المسار الكامل ═══
#
# قرارٌ مبنيّ على قراءةٍ ناقصة أسوأ من قراءةٍ كاملة بطيئة.
c("  والغائب يعيد None", "return None" in _sk)
c("  وسببه", "أسوأ من قراءةٍ كاملة بطيئة" in src)
# ويُنادى قبل ``storage.load`` في المسار الفعليّ
_su = code.split("def _sync_unlocked")[1][:1200]
c("  ويُنادى قبل التحميل",
  ("_skip_if_current" in _su and "storage.load" in _su
   and _su.index("_skip_if_current") < _su.index("storage.load")),
  _su[:200])
# و‎force‎ يتخطّاه: من طلب الجلب صراحةً يريده
c("  و‎force‎ يتخطّاه", "if not force:" in _su)


# ═══════════ ٤) ملفّ السوق يُقرأ مرّةً ═══════════
c("٤ ذاكرةٌ لملفّ السوق", "_cfg_cache" in code and "def _market_cfg" in code)
c("  ويُستعمل في المزامنة — كطريقة", "self._market_cfg(cfg_dir, market)" in code)
# ═══ والاسم المجرّد ممنوع ═══
#
# ‏``_market_cfg`` طريقةٌ لا دالّة. ونداؤها مجرّدةً رمى ‏NameError‏ في
# كل زوج — «نجح 0 · فشل 4620» أيّاماً. والفحص السابق كان يطابق
# ‏"_market_cfg(cfg_dir, market)"‏ فيجدها داخل الخاطئة نفسها ويمرّ.
import re as _re
c("  ولا نداءَ مجرّداً لها",
  not _re.search(r"(?<![.\w])_market_cfg\(", code.replace("def _market_cfg(", "")))
c("  وسببه", "خمسة آلاف تحليلٍ لملفٍّ واحد" in src)


# ═══════════ ٥) والمتخطّى يُعلَن ═══════════
#
# «٤٢٦٥ نجحت» لا تفرّق بين جلبٍ تمّ وزوجٍ لم يكن له شيء. والرقمان
# مختلفان تماماً في تفسير الزمن.
c("٥ المتخطّى يُعدّ", '"skipped_current"' in code)
c("  والمجلوب كذلك", '"fetched"' in code)
c("  وعدد الكتابات", '"status_writes"' in code)
c("  وسببه", "في تفسير الزمن" in src)


# ═══════════ ٥ب) الاتّصال يُعاد استعماله ═══════════
#
# ═══ القياس صحّح التشخيص ═══
#
# قلتُ «العنق ليس الشبكة بل القرص». والقياس على الخادم:
#
#     كتابة حالة زوج     135ms  →  291ث في الدورة
#     طلبٌ شبكيّ واحد     997ms  → 2146ث في الدورة
#
# فالشبكة سبعة أضعاف القرص. وكان تشخيصي ناقصاً.
#
# و٩٩٧ مللي ثانية لحمولةٍ بضعة كيلوبايتات لا تفسّرها البيانات:
# ``urlopen`` يفتح اتّصالاً **جديداً لكل طلب** — بحث DNS، ومصافحة
# TCP، ومصافحة TLS. أربع دورات ذهابٍ وإياب قبل أوّل بايت.
hp = ROOT / "scanner" / "adapters" / "http_pool.py"
c("٥ب مجمّع الاتّصالات موجود", hp.exists())
hp_code = code_of(hp) if hp.exists() else ""
hp_src = source_of(hp) if hp.exists() else ""
c("  بجلسةٍ واحدة", "requests.Session()" in hp_code)
c("  وحجمُ مجمّعٍ يبلغ الخيوط", "pool_maxsize=POOL_SIZE" in hp_code)
c("  والقياس موثَّق", "997 مللي ثانية" in hp_src)
# ═══ ولا إعادة محاولةٍ مزدوجة ═══
#
# المنادي يعيد المحاولة ويبدّل المضيف. وإعادةٌ ثانية في المحوّل
# تضاعف الانتظار بلا أن يعلم المنادي.
c("  ولا إعادة في المحوّل", "max_retries=0" in hp_code)
c("  وسببه", "فتصير مهلةُ عشرين ثانية ستّين" in hp_src)
# ═══ والاستثناء يُترجَم ═══
#
# ``requests.ConnectionError`` لا يلتقطه ``except URLError`` —
# فيهرب من كل طبقات إعادة المحاولة المكتوبة فوقه.
c("  والاستثناء يُترجَم", "urllib.error.URLError(str(exc)" in hp_code)
c("  و‎HTTPError‎ كذلك", "urllib.error.HTTPError(" in hp_code)
# ═══ وارتدادٌ إن غابت ``requests`` ═══
c("  وارتدادٌ إلى urllib", "_urllib_json" in hp_code)
c("  أبطأ لا معطوباً", "أبطأ لا معطوباً" in hp_src)

# والمحوّلات الثلاثة تستعمله
for name in ("binance.py", "yahoo.py", "alpaca.py"):
    a = code_of(ROOT / "scanner" / "adapters" / name)
    c(f"  و{name} تستعمله", "http_pool.get_json" in a)
    c(f"    ولا ‎urlopen‎ في ‎_get‎",
      "urlopen" not in a.split("def _get")[1][:1600]
      if "def _get" in a else False)
    # ═══ والترويسة لا تُسقَط عند النقل ═══
    #
    # هذا عطبٌ وقع: نقلتُ ``_get`` إلى المجمّع فأسقطتُ
    # ``headers=UA``. وياهو ترفض من لا ترويسةَ متصفّحٍ له، فردّت
    # على كل رمزٍ أمريكيٍّ وسعوديّ — والأثر لم يكن رسالة خطأ بل
    # شاشتَي المسح والمراقبة شبه فارغتين.
    #
    # فمن يُعرّف ``UA`` يجب أن يمرّرها. وتعريفُها بلا تمريرٍ هو
    # بالضبط شكل العطب.
    if "UA = {" in a:
        c(f"    و‎UA‎ تُمرَّر لا تُهمَل",
          "headers=UA" in a or "**UA" in a,
          "عُرّفت ولم تُمرَّر")

# ═══ والمفتاح لا يدخل الجلسة ═══
#
# جلسةٌ واحدة تخدم المحوّلات الثلاثة. ووضعُ مفتاح Alpaca في
# ترويساتها يرسله إلى Binance وYahoo — تسريبٌ صامت.
c("  والترويسات للطلب لا للجلسة",
  "headers=headers or None" in hp_code)
c("  وسببه", "تسريبٌ صامت" in hp_src)
alp = code_of(ROOT / "scanner" / "adapters" / "alpaca.py")
c("  و‎Alpaca‎ تمرّرها للطلب", "headers=headers)" in alp)

# ═══ وحدّ Alpaca يتقاسمه الخيوط ═══
#
# «نجح 4512 · فشل 108 · أكثر الأسباب: Alpaca 429». الباقة ٢٠٠ طلب
# في الدقيقة للحساب، وأربعة خيوطٍ بلا مسافة تبلغ ألفاً.
c("  و‎Alpaca‎ تنتظر دورها قبل كل طلب",
  "_wait_turn()" in alp.split("def _get")[1][:1500])
import threading as _th, time as _tm
from scanner.adapters import alpaca as _A
_A._GAP, _A._next_slot[0] = 0.05, 0.0
_ts = []
def _w():
    for _ in range(4):
        _A._wait_turn(); _ts.append(_tm.monotonic())
_ths = [_th.Thread(target=_w) for _ in range(3)]
[x.start() for x in _ths]; [x.join() for x in _ths]
_ts.sort()
c("    والمسافة محترمةٌ عبر الخيوط",
  min(b - a for a, b in zip(_ts, _ts[1:])) >= 0.045,
  f"{min(b - a for a, b in zip(_ts, _ts[1:])):.3f}")


# ═══════════ ٦) أداة القياس ═══════════
tool = ROOT / "tools_sync_profile.py"
c("٦ أداة القياس موجودة", tool.exists())
if tool.exists():
    t = source_of(tool)
    c("  تقيس الأجزاء الأربعة",
      all(k in t for k in ("last_time_on_disk", "storage.load",
                           "update_pair", "adapter")))
    # ولا تلمس ملفّ الإنتاج
    c("  ولا تكتب على الإنتاج", "tempfile.mkdtemp" in t)
    c("  والشبكة اختيارية", "--net" in t)
    c("  وتقول أين الأثقل", "الأثقل" in t)


sys.exit(c.report())
