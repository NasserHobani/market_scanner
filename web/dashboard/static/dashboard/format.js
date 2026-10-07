/* تنسيق الأسعار — نسخة مطابقة لـ scanner/formatting.py
 *
 * التطابق مقصود: لو اختلف تنسيق الخادم عن المتصفح لظهر السعر نفسه
 * برقمين مختلفين في الجدول والشارت، وهو أسوأ من التنسيق السيئ.
 */
(function (global) {
  "use strict";

  var SIG = 3;

  function trim(text) {
    if (text.indexOf(".") === -1) return text;
    return text.replace(/0+$/, "").replace(/\.$/, "");
  }

  function price(value, digits) {
    digits = digits || SIG;
    if (value === null || value === undefined) return "—";
    var v = Number(value);
    if (!isFinite(v)) return "—";
    if (v === 0) return "0";

    var m = Math.abs(v);
    if (m >= 1000) {
      return v.toLocaleString("en-US", { minimumFractionDigits: 2,
                                         maximumFractionDigits: 2 });
    }
    if (m >= 1) return trim(v.toFixed(digits));

    var leadingZeros = -Math.floor(Math.log10(m)) - 1;
    return trim(v.toFixed(leadingZeros + digits));
  }

  function percent(value, digits) {
    if (value === null || value === undefined) return "—";
    var v = Number(value);
    if (!isFinite(v)) return "—";
    return (v >= 0 ? "+" : "") + v.toFixed(digits === undefined ? 2 : digits) + "%";
  }

  function ratio(value) {
    if (value === null || value === undefined) return "—";
    var v = Number(value);
    if (!isFinite(v)) return "—";
    return "1:" + trim(v.toFixed(2));
  }

  /* ═══════════════════════════════════════════════════════════
   *  الوقت — بتوقيت الرياض دائماً
   * ═══════════════════════════════════════════════════════════
   *
   * ═══ العطب ═══
   *
   * ``Django`` يخزّن بـUTC (‏USE_TZ) ويعرض بالمحلّي في القوالب.
   * أمّا الـAPI فيُخرج ISO بـ‎+00:00‎، وكانت الشاشات تقصّه نصّاً:
   *
   *     String(r.started_at).replace("T", " ").slice(0, 19)
   *
   * فتُعرَض الساعة **بتوقيت غرينتش**: صفقةٌ دخلت الثامنة مساءً
   * تظهر «17:00». وتقارنها بشارتك فلا تتطابق، فتظنّ البيانات
   * خاطئة — والبيانات صحيحة والعرض كاذب.
   *
   * ═══ ولماذا الرياض صراحةً لا «المحلّي» ═══
   *
   * «المحلّي» توقيت الجهاز. ولوحةٌ تُفتح من هاتفٍ في سفرٍ تعرض
   * أوقاتاً تختلف عن الحاسوب — والشموع والصفقات مرجعها واحد.
   * فالمنطقة مثبّتة، والعرض واحدٌ أينما فُتح.
   */
  var TZ = "Asia/Riyadh";

  function _parse(v) {
    if (v === null || v === undefined || v === "") return null;
    if (v instanceof Date) return isNaN(v.getTime()) ? null : v;
    if (typeof v === "number") {
      // ثوانٍ أم ميلي ثانية؟ ما دون عشرة مليارات ثوانٍ
      return new Date(v < 1e10 ? v * 1000 : v);
    }
    var s = String(v).trim();
    /* ═══ نصٌّ بلا منطقة يُقرأ **محلّياً** ═══
     *
     * ``new Date("2026-10-07T12:00:00")`` يفترضه توقيت الجهاز،
     * و``…Z`` يفترضه UTC. ومصدرنا UTC دائماً، فيُلحَق ‎Z‎ لما
     * لا يحمل منطقة — وإلّا انزاح الوقت بفارق منطقة القارئ. */
    if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(s) &&
        !/[zZ]$|[+-]\d{2}:?\d{2}$/.test(s)) {
      s = s.replace(" ", "T") + "Z";
    }
    var d = new Date(s);
    return isNaN(d.getTime()) ? null : d;
  }

  function _fmt(v, opts) {
    var d = _parse(v);
    if (!d) return "—";
    try {
      return new Intl.DateTimeFormat("en-GB", Object.assign(
        { timeZone: TZ, hour12: false }, opts)).format(d);
    } catch (e) {
      return d.toISOString().slice(0, 16).replace("T", " ");
    }
  }

  /** «2026-10-07 15:42» بتوقيت الرياض */
  function dateTime(v) {
    return _fmt(v, { year: "numeric", month: "2-digit", day: "2-digit",
                     hour: "2-digit", minute: "2-digit" })
      .replace(",", "");
  }

  /** «15:42» */
  function timeOnly(v) {
    return _fmt(v, { hour: "2-digit", minute: "2-digit" });
  }

  /** «2026-10-07» */
  function dateOnly(v) {
    return _fmt(v, { year: "numeric", month: "2-digit", day: "2-digit" });
  }

  /** «قبل ٣ دقائق» — والمرجع لحظة القراءة لا منطقةٌ بعينها */
  function ago(v) {
    var d = _parse(v);
    if (!d) return "—";
    var s = Math.round((Date.now() - d.getTime()) / 1000);
    var past = s >= 0;
    s = Math.abs(s);
    var txt = s < 60 ? s + "ث"
      : s < 3600 ? Math.round(s / 60) + "د"
        : s < 86400 ? Math.round(s / 3600) + "س"
          : Math.round(s / 86400) + "ي";
    return (past ? "قبل " : "بعد ") + txt;
  }

  global.Fmt = {
    price: price, percent: percent, ratio: ratio,
    dateTime: dateTime, timeOnly: timeOnly, dateOnly: dateOnly,
    ago: ago, tz: TZ,
  };
})(window);
