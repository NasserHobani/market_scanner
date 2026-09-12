/* ربط المستشار بالواجهة — بتشغيل الملف لا بقراءته.
 *
 * ═══ لماذا يُشغَّل ═══
 *
 * الفحص بالنصّ ("هل أدخل؟" موجودة في app.js) يمرّ على شيفرةٍ ميّتة.
 * فيُحمَّل advice.js في بيئةٍ مزيّفة، ويُنقَر الزرّ فعلاً، ويُفحَص
 * **ما طُلب من الشبكة**.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const DIR = path.join(__dirname, "web", "dashboard", "static", "dashboard");
const results = [];
const check = (name, cond, extra = "") => results.push([!!cond, name, extra]);

// ── بيئة متصفّح صغيرة ──
const calls = { fetch: [], post: [] };

function fakeEl() {
  const el = {
    innerHTML: "", textContent: "", disabled: false, onclick: null,
    id: "", className: "", style: {}, children: [],
    setAttribute() {}, getAttribute: () => null,
    appendChild(c) { this.children.push(c); },
    querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {}, classList: { toggle() {}, add() {} },
  };
  return el;
}

const nodes = {};
const sandbox = {
  console,
  setInterval: () => 0,
  clearInterval: () => {},
  URLSearchParams,
  Object, Array, String, Number, Math, JSON, Promise, encodeURIComponent,
  fetch: (url) => {
    calls.fetch.push(url);
    return Promise.resolve({ json: () => Promise.resolve({ ok: true,
      rate: null, causes: [], evidence: "—", population: 0 }) });
  },
};
sandbox.window = sandbox;
sandbox.document = {
  createElement: () => fakeEl(),
  body: { appendChild() {} },
  getElementById: (id) => (nodes[id] = nodes[id] || fakeEl()),
};
sandbox.window.DS = { createDrawer: () => ({ open() {}, close() {} }) };
sandbox.window.postJSON = (url, body) => {
  calls.post.push([url, body.toString()]);
  return Promise.resolve({});
};

vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(DIR, "advice.js"), "utf8"),
                sandbox, { filename: "advice.js" });

const A = sandbox.window.Advice;
check("١ الواجهة معرَّفة", !!A);
check("  وفيها المسارات الثلاثة",
      A && typeof A.settled === "function"
        && typeof A.prospective === "function"
        && typeof A.openSetup === "function");

// ── ٢) فتح إعداد: الأدلّة تُطلب فوراً، والنموذج لا يُنادى ──
A.openSetup({ symbol: "BTCUSDT", market: "crypto", timeframe: "4h",
              grade: "B", score: 30, rr: 2.4, entry: 100, stop: 95,
              target1: 110, empty: "", nothing: null });

const ev = calls.fetch.find((u) => u.indexOf("/api/advice/evidence/") === 0);
check("٢ الأدلّة تُطلب عند الفتح", !!ev, JSON.stringify(calls.fetch));
check("  ولا يُنادى النموذج بلا طلب", calls.post.length === 0,
      JSON.stringify(calls.post));

// ═══ الحقول الفارغة تُحذف ═══
//
// ``grade=`` فارغةً تصير سمةً وهميّة في الأدلّة، فتُضيّق العيّنة
// إلى الصفقات التي صنّفها النظام بلا تصنيف — وهي عادةً صفر.
check("  والفارغ لا يُرسَل",
      ev && ev.indexOf("empty=") < 0 && ev.indexOf("nothing=") < 0, ev);
check("  والأرقام تُرسَل", ev && ev.indexOf("stop=95") >= 0, ev);
check("  والنوع مُعلَن", ev && ev.indexOf("kind=prospective") >= 0, ev);

// ── ٣) الزرّ ينادي النموذج ──
const askBtn = nodes["advice-d-ask"];
check("٣ زرّ السؤال موجود", !!askBtn && typeof askBtn.onclick === "function");
if (askBtn && askBtn.onclick) {
  askBtn.onclick();
  check("  والنداء إلى المسار الصحيح",
        calls.post.length === 1
          && calls.post[0][0] === "/api/advice/prospective/",
        JSON.stringify(calls.post));
  // زرٌّ يُنقر مرّتين يبدأ مهمّتين على نموذجٍ واحد
  check("  ويُعطَّل بعد النقر", askBtn.disabled === true);
}

// ── ٤) الصفقة المحسومة ──
calls.fetch.length = 0; calls.post.length = 0;
const box = fakeEl(), vbox = fakeEl();
A.settled(91, box, vbox);
check("٤ أدلّة الصفقة بالنوع settled",
      calls.fetch.some((u) => u.indexOf("kind=settled&trade_id=91") > 0),
      JSON.stringify(calls.fetch));
check("  وتُستشار على المسار الصحيح",
      calls.post.some((c) => c[0] === "/api/advice/settled/"),
      JSON.stringify(calls.post));

// ── ٥) الماسح وصفحة الصفقات يُحمّلان الملف ──
const T = path.join(__dirname, "web", "dashboard", "templates", "dashboard");
for (const page of ["scanner.html", "trades.html"]) {
  const html = fs.readFileSync(path.join(T, page), "utf8");
  check("٥ " + page + " يُحمّل advice.js",
        html.indexOf("dashboard/advice.js") > 0);
}
// الترتيب يهمّ: app.js يقرأ window.Advice عند النقر لا عند التحميل،
// لكن التحميل المتأخّر يترك أوّل نقرةٍ على المسار القديم.
const sc = fs.readFileSync(path.join(T, "scanner.html"), "utf8");
check("  وقبل app.js",
      sc.indexOf("dashboard/advice.js") < sc.indexOf("dashboard/app.js"));

const app = fs.readFileSync(path.join(DIR, "app.js"), "utf8");
check("  وزرّ الصفّ يسأل سؤالاً", app.indexOf("هل أدخل؟") > 0);
check("  ويوجَّه إلى المستشار الجديد",
      app.indexOf("Advice.openSetup(opts)") > 0);

// ── النتيجة ──
let bad = 0;
for (const [ok, name, extra] of results) {
  if (!ok) bad++;
  console.log((ok ? "✓ " : "✗ ") + name + (ok || !extra ? "" : "  ← " + extra));
}
console.log("");
console.log(bad ? `✗ فشل ${bad} من ${results.length}`
                : `✓ ${results.length} اختباراً`);
process.exit(bad ? 1 : 0);
