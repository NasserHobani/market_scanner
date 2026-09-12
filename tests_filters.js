/* اختبارات تصفية اللوحة — تُشغَّل بـ:  node tests_filters.js
 *
 * تُستخرج الدوال من app.js نفسه لا نسخة منها: اختبار نسخة يمرّ بينما
 * الملف الحقيقي معطوب.
 */
const fs = require("fs");
const path = require("path");

const SRC = path.join(__dirname, "web", "dashboard", "static", "dashboard", "app.js");
const src = fs.readFileSync(SRC, "utf8");

const from = src.indexOf("function isThin");
const to = src.indexOf("function render");
if (from < 0 || to < 0) throw new Error("تعذّر استخراج دوال التصفية من app.js");
const body = src.slice(from, to);

const results = [];
const check = (name, cond, extra) => results.push([!!cond, name, extra || ""]);

// ── بيئة مصغّرة ──
const chips = [
  { attrs: { "data-l": "all" }, disabled: false, title: "" },
  { attrs: { "data-l": "high" }, disabled: false, title: "" },
  { attrs: { "data-l": "mid" }, disabled: false, title: "" },
  { attrs: { "data-l": "no-micro" }, disabled: false, title: "" },
].map(c => ({ ...c, getAttribute(k) { return this.attrs[k]; } }));

const document = {
  getElementById: () => null,
  querySelectorAll: sel => (sel.includes("data-l") ? chips : []),
};
const state = { compliance: "all", liquidity: "all", filter: "all", rows: [] };

const api = new Function("state", "document", body +
  "\nreturn { isThin, hasLiquidityData, applyFilter, emptyReason, syncLiquidityChips };"
)(state, document);

const row = o => Object.assign(
  { symbol: "X", compliance: "review", action: "none", ready: false }, o);

const NEW = [
  row({ symbol: "BTCUSDT", liquidity: "high", thin: false, quote_volume: 9e8 }),
  row({ symbol: "SOLUSDT", liquidity: "mid", thin: false, quote_volume: 2e7 }),
  row({ symbol: "LOWUSDT", liquidity: "low", thin: false, quote_volume: 2e6 }),
  row({ symbol: "EDENUSDT", liquidity: "micro", thin: true, quote_volume: 3e5 }),
];
const OLD = [
  row({ symbol: "BTCUSDT", liquidity: "unknown", thin: true, quote_volume: null }),
  row({ symbol: "SOLUSDT", liquidity: "unknown", thin: true, quote_volume: null }),
];
const MISSING = [row({ symbol: "BTCUSDT" }), row({ symbol: "SOLUSDT" })];

function filtered(rows, lq) {
  state.rows = rows;
  state.liquidity = lq;
  return api.applyFilter(rows).map(r => r.symbol);
}

// ── التعريف الموحّد لـ «رقيقة» ──
check("سيولة عالية ليست رقيقة", !api.isThin(NEW[0]));
check("micro رقيقة", api.isThin(NEW[3]));
check("unknown رقيقة", api.isThin(OLD[0]));
check("صف بلا حقل سيولة يُعدّ رقيقاً لا سليماً",
      api.isThin(MISSING[0]), "كان يمرّ من «بلا الدقيقة» خطأً");

// ── التصفية على بيانات كاملة ──
check("«الكل» لا يحذف شيئاً", filtered(NEW, "all").length === 4);
check("«عالية» تُبقي العالية وحدها",
      JSON.stringify(filtered(NEW, "high")) === '["BTCUSDT"]', filtered(NEW, "high"));
check("«متوسطة+» تشمل العالية والمتوسطة",
      JSON.stringify(filtered(NEW, "mid")) === '["BTCUSDT","SOLUSDT"]',
      filtered(NEW, "mid"));
check("«بلا الدقيقة» تستبعد micro فقط",
      JSON.stringify(filtered(NEW, "no-micro")) === '["BTCUSDT","SOLUSDT","LOWUSDT"]',
      filtered(NEW, "no-micro"));

// ── العطب الذي بلّغ عنه المستخدم ──
check("بيانات قديمة: كل فلاتر السيولة تُفرغ الجدول",
      ["high", "mid", "no-micro"].every(l => filtered(OLD, l).length === 0));
state.rows = OLD; state.liquidity = "high";
check("والسبب يُشرح بدل «لا نتائج» المبهمة",
      /مسح/.test(api.emptyReason()), api.emptyReason().slice(0, 40));
state.rows = NEW; state.liquidity = "high";
check("أمّا مع بيانات سليمة فالرسالة عادية",
      api.emptyReason() === "لا نتائج تطابق التصفية", api.emptyReason());

// ── الإصلاح الثاني ──
check("صفوف بلا الحقل لا تمرّ من «بلا الدقيقة»",
      filtered(MISSING, "no-micro").length === 0, filtered(MISSING, "no-micro"));

// ── كشف وجود البيانات ──
check("يكشف وجود السيولة", api.hasLiquidityData(NEW) === true);
check("ويكشف غيابها", api.hasLiquidityData(OLD) === false);
check("وغيابها التام", api.hasLiquidityData(MISSING) === false);
check("ومصفوفة فارغة", api.hasLiquidityData([]) === false);
check("حجم صفري يُعدّ بياناً موجوداً",
      api.hasLiquidityData([row({ quote_volume: 0 })]) === true);

// ── تعطيل الرقائق ──
state.rows = OLD; api.syncLiquidityChips();
check("الرقائق تُعطَّل حين لا سيولة في البيانات",
      chips.slice(1).every(c => c.disabled) && !chips[0].disabled);
check("ومعها سبب في التلميح", /مسح/.test(chips[1].title), chips[1].title);
state.rows = NEW; api.syncLiquidityChips();
check("وتُفعَّل مع بيانات سليمة", chips.every(c => !c.disabled));

const bad = results.filter(r => !r[0]);
for (const [ok, name, extra] of results) {
  console.log((ok ? "✓ " : "✗ ") + name + (!ok && extra ? " — " + extra : ""));
}
console.log();
console.log(bad.length ? `✗ فشل ${bad.length} من ${results.length}`
                       : `✓ ${results.length} اختباراً`);
process.exit(bad.length ? 1 : 0);
