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

  global.Fmt = { price: price, percent: percent, ratio: ratio };
})(window);
