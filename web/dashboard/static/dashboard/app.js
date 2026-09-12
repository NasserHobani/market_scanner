/* تحديث حي للوحة.
 *
 * قاعدة محفوظة من المحرك: الإشارات تُقيَّم عند إغلاق الشمعة فقط.
 * هذا الملف لا يقيّم شيئاً — يعرض ما حسبه الخادم ويسحب الجديد دورياً.
 * العدّاد التنازلي يخبرك متى ستتغيّر الأرقام فعلاً.
 */
(function () {
  "use strict";

  var POLL_MS = 15000;
  var QUOTE_MS = 20000;   // الأسهم: سحب من الخادم بدل البثّ
  var state = {
    rows: [], sortKey: "score", sortDir: -1, runId: null, countdown: null,
    livePrice: {}, liveChange: {}, filter: "all", compliance: "all",
    liquidity: "all",
    // تنويه الفريم: يصل من الخادم حين يخالف المعروضُ المطلوب
    notice: null
  };

  /* نصوص الخادم تحمل الفريم المطلوب — وهو من شريط العنوان.
     والحصر في UI_TIMEFRAMES يقطع الخطر من مصدره، وهذا حزامٌ ثانٍ. */
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var COMPLIANCE = {
    compliant:     { label: "متوافق مبدئياً", cls: "up" },
    non_compliant: { label: "غير متوافق",     cls: "down" },
    review:        { label: "يحتاج مراجعة",   cls: "warn" },
    unknown:       { label: "غير مصنّف",      cls: "dim" }
  };
  var feed = null;
  var isStreaming = window.MARKET === "crypto";   // العملات وحدها لها بثّ WebSocket

  var tbody = document.getElementById("tbody");
  var cdEl = document.getElementById("countdown");
  var dot = document.getElementById("dot");

  function fmt(v, digits) {
    if (v === null || v === undefined || v !== v) return "—";
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return digits === undefined ? String(n) : n.toFixed(digits);
  }

  // تنسيق موحّد مع الخادم — Fmt من format.js
  var price = function (v) { return window.Fmt ? window.Fmt.price(v) : String(v); };

  function scoreClass(s) { return s >= 25 ? "up" : s <= -25 ? "down" : "dim"; }

  /* السيولة غير المعروفة تُعامَل معاملة الرقيقة، لا معاملة الجيّدة.
     الاعتماد على r.thin وحدها كان يمرّر صفوفاً بلا الحقل أصلاً (من مسح
     قديم) عبر فلتر «بلا الدقيقة» — أي أن الفلتر يعِد بما لا يضمنه. */
  function isThin(r) {
    return r.thin === true || !r.liquidity || r.liquidity === "unknown";
  }

  /* هل في البيانات معلومة سيولة أصلاً؟ صفوف ما قبل هذه الميزة ليس
     فيها حجم، فكل فلاتر السيولة تُفرغ الجدول — وهذا يبدو عطلاً
     بينما هو نقص بيانات يحلّه مسح جديد. */
  function hasLiquidityData(rows) {
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].quote_volume !== null && rows[i].quote_volume !== undefined) {
        return true;
      }
    }
    return false;
  }

  function applyFilter(rows) {
    var c = state.compliance;
    if (c === "ok") {
      rows = rows.filter(function (r) { return r.compliance === "compliant"; });
    } else if (c === "review") {
      rows = rows.filter(function (r) { return r.compliance === "review"; });
    } else if (c === "hide-bad") {
      rows = rows.filter(function (r) { return r.compliance !== "non_compliant"; });
    }

    var lq = state.liquidity;
    if (lq === "high") {
      rows = rows.filter(function (r) { return r.liquidity === "high"; });
    } else if (lq === "mid") {
      rows = rows.filter(function (r) {
        return r.liquidity === "high" || r.liquidity === "mid";
      });
    } else if (lq === "no-micro") {
      rows = rows.filter(function (r) { return !isThin(r); });
    }

    var f = state.filter;
    var out = f === "reco" ? rows.filter(function (r) { return r.action !== "none"; })
      : f === "now" ? rows.filter(function (r) { return r.action === "now"; })
      : f === "pending" ? rows.filter(function (r) { return r.action === "pending"; })
      : f === "ready" ? rows.filter(function (r) { return r.ready; })
      : rows;
    var el = document.getElementById("filter-count");
    if (el) el.textContent = out.length + " من " + rows.length;
    return out;
  }

  /* ─────────────────────────── الترقيم
   *
   * المشكلة ليست عدد الصفوف بل عدد **الخلايا**: مسح واحد على 1h أعطى
   * 307 صفوف × 21 عموداً ≈ 6400 خلية، والمسح الكبير يتجاوز ألف صفّ.
   * المتصفّح يبني عقدة DOM لكل خلية، ثم يعيد حساب التخطيط عند كل
   * تحديث سعر حيّ — فيظهر التعليق في التمرير لا في الفلترة.
   *
   * ولهذا لا تكفي مكتبة جدول جاهزة: DataTables ترقّم ما هو **مرسوم
   * أصلاً**، أي أنها تبني الـ DOM كاملاً أولاً ثم تخفي أغلبه. وهنا
   * الرسم نفسه هو الكلفة.
   *
   * الترقيم هنا يقع **بعد** الفلترة وقبل الرسم، فتبقى الفلاتر عاملة
   * على المجموعة كاملة لا على الصفحة المعروضة — وهو الفرق بين فلتر
   * صحيح وفلتر مضلّل. ووحدة الفلترة نفسها لم تُمسّ، فاختباراتها
   * العشرون تبقى صالحة.
   */
  var PAGE_SIZES = [50, 100, 250, 0];   // 0 = الكل
  var page = { index: 0, size: 100 };

  function pageSlice(rows) {
    if (!page.size) return rows;
    var pages = Math.max(1, Math.ceil(rows.length / page.size));
    if (page.index >= pages) page.index = pages - 1;
    if (page.index < 0) page.index = 0;
    var from = page.index * page.size;
    return rows.slice(from, from + page.size);
  }

  function drawPager(total) {
    var host = document.getElementById("pager");
    if (!host) return;
    if (!page.size || total <= page.size) { host.innerHTML = ""; return; }
    var pages = Math.ceil(total / page.size);
    var from = page.index * page.size + 1;
    var to = Math.min(total, (page.index + 1) * page.size);
    host.innerHTML =
      '<div class="d-flex align-items-center gap-2 flex-wrap py-2">' +
        '<button class="btn btn-sm btn-outline-secondary" data-page="prev"' +
          (page.index === 0 ? " disabled" : "") + ">السابق</button>" +
        '<span class="small muted">' + from + "–" + to + " من " + total +
          "  ·  صفحة " + (page.index + 1) + " من " + pages + "</span>" +
        '<button class="btn btn-sm btn-outline-secondary" data-page="next"' +
          (page.index >= pages - 1 ? " disabled" : "") + ">التالي</button>" +
      "</div>";
  }

  function bindPager() {
    var host = document.getElementById("pager");
    if (host) {
      host.addEventListener("click", function (e) {
        var b = e.target.closest("[data-page]");
        if (!b || b.disabled) return;
        page.index += b.getAttribute("data-page") === "next" ? 1 : -1;
        render();
        // الرجوع لأعلى الجدول: تغيير الصفحة والمستخدم في أسفلها
        // يترك عينه على صفّ لا علاقة له بما طلب
        var t = document.getElementById("tbody");
        if (t && t.parentElement) t.parentElement.scrollIntoView({ block: "start" });
      });
    }
    var sel = document.getElementById("page-size");
    if (sel) {
      sel.value = String(page.size);
      sel.addEventListener("change", function () {
        page.size = parseInt(sel.value, 10) || 0;
        page.index = 0;
        render();
      });
    }
  }

  // أي تغيير في الفلترة يعيدنا للصفحة الأولى: البقاء على الصفحة
  // السابعة بعد فلتر أبقى صفّين يعني شاشة فارغة بلا سبب ظاهر
  function resetPage() { page.index = 0; }

  function cellId(symbol, kind) {
    return "lp-" + kind + "-" + symbol.replace(/[^A-Za-z0-9]/g, "");
  }

  function drift(symbol, closed) {
    /* الفارق بين السعر الآن وإغلاق الشمعة التي بُنيت عليها الإشارة.
       يخبرك كم ابتعد السوق عن نقطة القرار قبل أن تدخل. */
    var live = state.livePrice[symbol];
    if (live === undefined || !closed) return null;
    return (live - closed) / closed * 100;
  }

  function htfCell(r) {
    if (r.htf === 1) return '<span class="up">صاعد ↑</span>';
    if (r.htf === -1) return '<span class="down">هابط ↓</span>';
    return '<span class="dim">مختلط —</span>';
  }

  /* سبب الفراغ يُقال صراحة: «لا نتائج» أمام فلتر سيولة على بيانات
     بلا سيولة يترك المستخدم يظن أن الزر معطّل. */
  function emptyReason() {
    /* ═══ الفريم المطلوب غير المعروض ═══
     *
     * الخادم يستبدل الفريم غير الممسوح بأحدث ما مُسح فعلاً. وكان
     * ذلك يجري **بصمت**: من اختار «4 ساعات» للسوق الأمريكي يرى
     * بياناتٍ يومية بلا كلمة — فيبدو الزرّ معطوباً وهو يعمل كما
     * بُرمج. وهذا ما بُلّغ عنه بـ «الفريم 4 ساعات لا يعمل».
     *
     * فالسبب يُقدَّم على كل سببٍ آخر: هو الذي يفسّر الشاشة. */
    if (state.notice && state.notice.why) {
      return esc(state.notice.why);
    }
    if (state.liquidity !== "all" && !hasLiquidityData(state.rows)) {
      return "نتائج هذا المسح محفوظة قبل إضافة بيانات السيولة، " +
             "فلا يمكن ترشيحها بها.<br>" +
             '<span style="font-size:12px">اضغط «امسح الآن» ليُجلب حجم ' +
             "التداول لكل رمز، ثم جرّب الفلتر مجدداً.</span>";
    }
    return "لا نتائج تطابق التصفية";
  }

  /* شريطٌ فوق الجدول حين يخالف المعروضُ المطلوب — لأنّ الجدول قد
     يمتلئ بصفوفٍ من فريمٍ آخر، فلا يكفي تعليل الفراغ وحده. */
  function paintTimeframeNotice() {
    var host = document.getElementById("tf-notice");
    if (!host) return;
    var n = state.notice;
    if (!n || !n.substituted) { host.innerHTML = ""; host.hidden = true; return; }
    host.hidden = false;
    host.innerHTML =
      '<div class="ds-insight ds-insight--warn" role="status">' +
      '<span class="ds-insight__mark"></span><div class="ds-insight__body">' +
      '<p class="ds-insight__title">المعروض فريم ' + esc(n.served) +
      "، لا " + esc(n.requested) + "</p>" +
      '<p class="ds-insight__text">' + esc(n.why) + "</p>" +
      "</div></div>";
  }

  /* رقائق السيولة تُعطَّل حين لا تملك البيانات ما تُرشَّح به — زرّ
     معطَّل مع سبب أوضح من زرّ يعمل ولا يفعل شيئاً. */
  function syncLiquidityChips() {
    var ok = hasLiquidityData(state.rows);
    document.querySelectorAll(".chip[data-l]").forEach(function (chip) {
      if (chip.getAttribute("data-l") === "all") return;
      chip.disabled = !ok;
      chip.title = ok ? "" : "يحتاج مسحاً جديداً ليُجلب حجم التداول";
    });
  }

  function render() {
    if (!tbody) return;
    syncLiquidityChips();
    var rows = state.rows.slice().sort(function (a, b) {
      var x = a[state.sortKey], y = b[state.sortKey];
      if (typeof x === "string" || typeof y === "string") {
        return String(x || "").localeCompare(String(y || ""), "ar") * state.sortDir;
      }
      return ((x || 0) - (y || 0)) * state.sortDir;
    });

    rows = applyFilter(rows);
    var matched = rows.length;
    rows = pageSlice(rows);
    drawPager(matched);

    var html = rows.map(function (r) {
      var act = r.action === "now" ? "act act-now"
              : r.action === "pending" ? "act act-pending" : "act act-none";
      var comp = COMPLIANCE[r.compliance] || COMPLIANCE.unknown;
      // العنوان يحمل النص الكامل لأن الخلية سطر واحد بقصّ
      var t = function (v) { return v ? ' title="' + String(v).replace(/"/g, "&quot;") + '"' : ""; };

      return '<tr class="' + (r.ready ? "ready" : "") + '">' +
        '<td><a href="' + r.url + '">' + r.symbol + "</a></td>" +
        '<td' + t(r.trigger) + '><span class="' + act + '">' + (r.headline || "—") +
          (r.grade && r.grade !== "—" ? " " + r.grade : "") + "</span></td>" +
        '<td class="num ' + scoreClass(r.score) + '" style="font-weight:600">' + fmt(r.score, 1) + "</td>" +
        '<td class="num">' + price(r.entry) + "</td>" +
        '<td class="num down">' + price(r.stop) + "</td>" +
        '<td class="num up">' + price(r.target1) + "</td>" +
        '<td class="num">' + (r.rr ? window.Fmt.ratio(r.rr) : "—") + "</td>" +
        '<td class="' + (r.confluence >= 2 ? "up" : r.confluence === 1 ? "warn" : "dim") + '">' +
          r.confluence + "/3</td>" +
        '<td class="reasons"' + t(r.reasons) + ">" + (r.reasons || "—") + "</td>" +
        '<td class="dim extra" style="font-size:12px"' + t(r.chart_pattern) + ">" +
          (r.chart_pattern || "—") + "</td>" +
        '<td class="dim extra" style="font-size:12px"' + t(r.elliott) + ">" +
          (r.elliott || "—") + "</td>" +
        "<td>" + htfCell(r) + "</td>" +
        '<td class="num">' + price(r.close) + "</td>" +
        '<td class="num" id="' + cellId(r.symbol, "p") + '">—</td>' +
        '<td class="num extra" id="' + cellId(r.symbol, "c") + '">—</td>' +
        '<td class="num" id="' + cellId(r.symbol, "d") + '">—</td>' +
        '<td class="num extra">' + fmt(r.rsi, 1) + "</td>" +
        '<td class="num extra">' + fmt(r.atr_pct, 2) + "</td>" +
        '<td class="' + comp.cls + '" style="font-size:12px"' + t(r.compliance_reason) + ">" +
          comp.label + "</td>" +
        '<td class="dim" style="font-size:12px"' + t(r.blocker) + ">" + (r.blocker || "—") + "</td>" +
        '<td class="num ' + (isThin(r) ? "warn" : "dim") + '"' +
          t((r.liquidity_label || "غير معروفة") +
            (isThin(r) ? " — سيولة ضعيفة: الانزلاق قد يبتلع الربح" : "")) +
          ">" + (r.volume_text || "—") + "</td>" +
        '<td><button type="button" class="btn btn-sm btn-outline-primary ai-scan-analyze" ' +
          'data-symbol="' + r.symbol + '" data-market="' + (r.market || window.MARKET || "crypto") + '" ' +
          'data-tf="' + (r.timeframe || window.TIMEFRAME || "4h") + '" ' +
          'title="احتمال النجاح من سجلّك، ثمّ حكم بقرار وشرط إبطال">' +
          'هل أدخل؟</button></td>' +
        '<td><a href="' + r.chart_url + '" target="_blank" rel="noopener">TV ↗</a></td>' +
        /* الحظر من مكان رؤية الرمز: من رأى رمزاً لا يجيزه يحظره
           في ثانية. وإلزامُه بفتح صفحةٍ أخرى ونسخ الرمز يعني
           أنّه لن يفعل — فيبقى الرمز يُمسح ويُوصى به. */
        '<td><button type="button" class="btn btn-sm btn-outline-danger ' +
          'sym-block" data-symbol="' + r.symbol + '" data-market="' +
          (r.market || window.MARKET || "crypto") + '" ' +
          'title="احظره شرعياً — يُستبعد من المسح والتحليل">⃠</button></td>' +
        "</tr>";
    }).join("");

    tbody.innerHTML = html || '<tr><td colspan="23" class="empty">' +
      emptyReason() + "</td></tr>";
    applyLivePrices();
    if (feed && isStreaming) {
      feed.setSymbols(state.rows.map(function (r) { return r.symbol; }));
    }
  }

  function applyLivePrices() {
    state.rows.forEach(function (r) {
      paintPrice(r.symbol, state.livePrice[r.symbol], 0);
      paintChange(r.symbol, state.liveChange[r.symbol]);
      paintDrift(r.symbol, drift(r.symbol, r.close));
    });
  }

  function paintPrice(symbol, value, direction) {
    var el = document.getElementById(cellId(symbol, "p"));
    if (!el || value === undefined) return;
    el.textContent = price(value);
    el.className = direction > 0 ? "up" : direction < 0 ? "down" : "";
    if (direction !== 0) {
      el.style.transition = "none";
      el.style.background = direction > 0 ? "rgba(61,220,151,.18)" : "rgba(255,107,107,.18)";
      setTimeout(function () {
        el.style.transition = "background .6s";
        el.style.background = "";
      }, 30);
    }
  }

  function paintChange(symbol, value) {
    var el = document.getElementById(cellId(symbol, "c"));
    if (!el || value === undefined || value === null) return;
    el.textContent = (value >= 0 ? "+" : "") + value.toFixed(2) + "%";
    el.className = value > 0 ? "up" : value < 0 ? "down" : "dim";
  }

  function paintDrift(symbol, value) {
    var el = document.getElementById(cellId(symbol, "d"));
    if (!el || value === null) return;
    el.textContent = (value >= 0 ? "+" : "") + value.toFixed(2) + "%";
    // الابتعاد الكبير عن سعر الإشارة يعني أن نقطة الدخول لم تعد كما كانت
    el.className = Math.abs(value) >= 1.5 ? "warn" : "dim";
  }

  function setCard(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  /* مصدر قائمة الرموز.

     ظلّ السوق الأمريكي يُمسَح على عشرة أسهم — قائمة الملف الاحتياطية —
     بينما الإعداد يقول «كل سهم فوق عشرين مليون دولار يومياً». والسبب
     أن الارتداد كان يُكتب إلى stderr، والمسح يعمل في خيط فلا يقرأه أحد.

     البانر يظهر عند التدهور فقط: التحذير الدائم يُدرَّب المستخدم على
     تجاهله، فيضيع معه ما يستحقّ الانتباه. */
  function paintUniverse(run) {
    var el = document.getElementById("universe-note");
    if (!el) return;
    if (!run || !run.universe_degraded) { el.classList.add("d-none"); return; }
    el.textContent = "⚠ " + (run.universe_note || "قائمة الرموز محدودة")
      + " — شغّل: python tools_check_universe.py " + (window.MARKET || "");
    el.classList.remove("d-none");
  }

  function poll() {
    var q = "/api/results/?market=" + encodeURIComponent(window.MARKET);
    if (window.TIMEFRAME) q += "&tf=" + encodeURIComponent(window.TIMEFRAME);
    return fetch(q)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (dot) dot.style.background = "#3ddc97";
        state.rows = d.results || [];
        if (d.countdown && d.countdown.seconds !== null) {
          state.countdown = d.countdown.seconds;
        }
        state.notice = d.notice || null;
        paintTimeframeNotice();
        if (d.run) {
          var isNew = state.runId !== null && d.run.id !== state.runId;
          state.runId = d.run.id;
          setCard("c-scanned", d.run.scanned);
          setCard("c-ready", d.run.ready);
          setCard("c-failed", d.run.failed);
          setCard("c-dur", d.run.duration);
          setCard("c-time", new Date(d.run.started_at)
            .toISOString().substring(11, 16));
          paintUniverse(d.run);
          if (isNew) flash();
        }
        render();
      })
      .catch(function () {
        // انقطاع مؤقت لا يمسح الجدول — نبدّل لون المؤشر فقط
        if (dot) dot.style.background = "#ff6b6b";
      });
  }

  function flash() {
    document.body.style.transition = "background .4s";
    document.body.style.background = "#141c18";
    setTimeout(function () { document.body.style.background = ""; }, 400);
  }

  function tickCountdown() {
    if (state.countdown === null || cdEl === null) return;
    if (state.countdown <= 0) { cdEl.textContent = "يُحسب الآن…"; return; }
    state.countdown -= 1;
    var s = state.countdown;
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    cdEl.textContent = (h ? h + "س " : "") + m + "د " + String(sec).padStart(2, "0") + "ث";
  }

  document.querySelectorAll("#tbl th[data-k]").forEach(function (th) {
    th.addEventListener("click", function () {
      var k = th.getAttribute("data-k");
      state.sortDir = state.sortKey === k ? -state.sortDir : -1;
      state.sortKey = k;
      render();
    });
  });

  if (typeof window.INITIAL_COUNTDOWN === "number") {
    state.countdown = window.INITIAL_COUNTDOWN;
  }

  var feedEl = document.getElementById("feed-status");

  /* العملات: بثّ WebSocket مباشر.
     الأسهم: لا بثّ مجاني من Yahoo، فنسحب من خادمنا كل 20 ثانية.
     المخرَج على الشاشة واحد — الفرق في المصدر والتأخير فقط. */
  function pollQuotes() {
    // تُعاد الوعدة ليعرف الحارس متى انتهى الطلب فيجدول التالي بعده
    return fetch("/api/quotes/?market=" + encodeURIComponent(window.MARKET))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.streaming) return;
        var q = d.quotes || {};
        var n = 0;
        Object.keys(q).forEach(function (sym) {
          var prev = state.livePrice[sym];
          state.livePrice[sym] = q[sym].price;
          state.liveChange[sym] = q[sym].change_pct;
          var dir = prev === undefined ? 0 : (q[sym].price > prev ? 1 : q[sym].price < prev ? -1 : 0);
          paintPrice(sym, q[sym].price, dir);
          paintChange(sym, q[sym].change_pct);
          var row = state.rows.filter(function (r) { return r.symbol === sym; })[0];
          if (row) paintDrift(sym, drift(sym, row.close));
          n += 1;
        });
        if (feedEl) {
          if (d.error) {
            feedEl.textContent = "تعذّر جلب الأسعار";
            feedEl.style.color = "var(--down)";
          } else if (n) {
            feedEl.textContent = "مؤجّلة (خادم)";
            feedEl.style.color = "var(--warn)";
            feedEl.title = "Yahoo لا توفّر بثّاً مجانياً — الأسعار مؤجّلة عادة 15 دقيقة";
          } else {
            feedEl.textContent = "لا أسعار";
            feedEl.style.color = "var(--dim)";
          }
        }
      })
      .catch(function () {
        if (feedEl) { feedEl.textContent = "انقطع"; feedEl.style.color = "var(--down)"; }
      });
  }

  if (!isStreaming) {
    pollQuotes();
    // ‏EVERY لا setInterval: هذا الطلب ينتظر نداء شبكة إلى المزوّد،
    // وقد يتجاوز العشرين ثانية فتتراكم الطلبات على الخادم.
    EVERY(QUOTE_MS, pollQuotes);
  }

  if (isStreaming && typeof window.LiveFeed === "function") {
    feed = new window.LiveFeed({
      onTick: function (t) {
        state.livePrice[t.symbol] = t.price;
        state.liveChange[t.symbol] = t.changePct;
        paintPrice(t.symbol, t.price, t.direction);
        paintChange(t.symbol, t.changePct);
        var row = state.rows.filter(function (r) { return r.symbol === t.symbol; })[0];
        if (row) paintDrift(t.symbol, drift(t.symbol, row.close));
      },
      onStatus: function (st) {
        if (!feedEl) return;
        var map = {
          live: ["بثّ حي", "var(--up)"],
          connecting: ["يتصل…", "var(--dim)"],
          reconnecting: ["يعيد الاتصال…", "var(--warn)"],
          error: ["انقطع البثّ", "var(--down)"],
          idle: ["بلا بثّ", "var(--dim)"]
        };
        var v = map[st] || map.idle;
        feedEl.textContent = v[0];
        feedEl.style.color = v[1];
      }
    });
  }
  bindPager();
  poll();
  EVERY(POLL_MS, poll);
  setInterval(tickCountdown, 1000);

  // ── التصفية ──────────────────────────────────────────────
  /* فلتر السيولة: بعد خفض عتبة الحجم صارت أزواج بمئات الآلاف تظهر،
     وهي التي تحتاج استبعاداً سريعاً حين تبحث عن قابل للتنفيذ فعلاً. */
  document.querySelectorAll(".chip[data-l]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      if (chip.disabled) return;
      document.querySelectorAll(".chip[data-l]").forEach(function (c) {
        c.classList.remove("active");
      });
      chip.classList.add("active");
      state.liquidity = chip.getAttribute("data-l");
      resetPage();
      render();
    });
  });

  document.querySelectorAll(".chip[data-c]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      document.querySelectorAll(".chip[data-c]").forEach(function (c) {
        c.classList.remove("active");
      });
      chip.classList.add("active");
      state.compliance = chip.getAttribute("data-c");
      resetPage();
      render();
    });
  });

  document.querySelectorAll(".chip[data-f]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      document.querySelectorAll(".chip[data-f]").forEach(function (c) {
        c.classList.remove("active");
      });
      chip.classList.add("active");
      state.filter = chip.getAttribute("data-f");
      resetPage();
      render();
    });
  });

  // ── المسح اليدوي ─────────────────────────────────────────
  var scanBtn = document.getElementById("scan-now");
  var scanState = document.getElementById("scan-state");
  var manualError = null;   // يبقى ظاهراً حتى المحاولة التالية

  function pollScanStatus() {
    return fetch("/api/scan/status/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!scanState) return;
        if (manualError && !d.running) return;   // لا تمحُ سبب الفشل
        if (d.running) {
          manualError = null;
          scanState.textContent = "يمسح " + (d.market || "") +
            (d.elapsed ? " · " + Math.round(d.elapsed) + "ث" : "");
          scanState.style.color = "var(--warn)";
          if (scanBtn) scanBtn.disabled = true;
        } else {
          if (scanBtn) scanBtn.disabled = false;
          scanState.textContent = d.last_error ? "فشل: " + d.last_error.slice(0, 60)
            : d.auto ? "المسح التلقائي يعمل" : "";
          scanState.style.color = d.last_error ? "var(--down)" : "var(--dim)";
        }
      })
      .catch(function () {});
  }

  function fail(msg, btn) {
    manualError = msg;
    if (scanState) {
      scanState.textContent = msg;
      scanState.style.color = "var(--down)";
    }
    if (btn) btn.disabled = false;
  }

  function startScan(btn) {
    if (!window.MARKET) { fail("لا سوق محدّد — أعد تحميل الصفحة", btn); return; }
    manualError = null;
    if (btn) btn.disabled = true;
    var body = new URLSearchParams({ market: window.MARKET });
    if (window.TIMEFRAME) body.set("timeframe", window.TIMEFRAME);
    window.postJSON("/api/scan/", body)
      .then(function (d) {
        if (!d.ok) {
          fail((d.code === "MARKET_DATA_STALE" ? "بيانات متأخرة: " : "") +
               (d.reason || "تعذّر البدء"), btn);
          return;
        }
        if (btn && btn.id === "scan-empty") {
          btn.textContent = "يفحص… ستُحدَّث الصفحة تلقائياً";
          waitThenReload();
        }
        setTimeout(pollScanStatus, 500);
      })
      .catch(function (e) {
        fail("تعذّر الاتصال بالخادم: " + (e && e.message ? e.message : e), btn);
      });
  }

  /* في حالة الفراغ لا جدول يتحدّث بالسحب الدوري، فننتظر انتهاء الدورة
     ثم نعيد التحميل — وإلا بقيت الصفحة فارغة رغم اكتمال المسح. */
  function waitThenReload() {
    var tries = 0;
    var timer = setInterval(function () {
      tries += 1;
      fetch("/api/scan/status/")
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.running && tries > 2) {
            clearInterval(timer);
            location.reload();
          }
        })
        .catch(function () {});
      if (tries > 120) clearInterval(timer);
    }, 3000);
  }

  if (scanBtn) {
    scanBtn.addEventListener("click", function () { startScan(scanBtn); });
  }
  var emptyBtn = document.getElementById("scan-empty");
  if (emptyBtn) {
    emptyBtn.addEventListener("click", function () { startScan(emptyBtn); });
  }

  // مزامنة بيانات يدوية — تزايدية فقط، ليست شرطاً قبل كل مسح
  var syncBtn = document.getElementById("sync-now");
  if (syncBtn) {
    syncBtn.addEventListener("click", function () {
      if (!window.MARKET) { fail("لا سوق محدّد", syncBtn); return; }
      syncBtn.disabled = true;
      if (scanState) {
        scanState.textContent = "جاري تحديث البيانات…";
        scanState.style.color = "var(--warn)";
      }
      window.postJSON("/api/market-data/sync/", new URLSearchParams({ market: window.MARKET }))
        .then(function (d) {
          if (!d.ok) {
            fail(d.reason || "تعذّرت المزامنة", syncBtn);
            return;
          }
          var tries = 0;
          var timer = setInterval(function () {
            tries += 1;
            fetch("/api/market-data/sync/worker/")
              .then(function (r) { return r.json(); })
              .then(function (st) {
                if (!st.running && tries > 1) {
                  clearInterval(timer);
                  syncBtn.disabled = false;
                  if (scanState) {
                    scanState.textContent = "اكتملت مزامنة البيانات";
                    scanState.style.color = "var(--up)";
                  }
                } else if (scanState && st.running) {
                  scanState.textContent = "جاري تحديث البيانات…";
                }
              })
              .catch(function () {});
            if (tries > 60) {
              clearInterval(timer);
              syncBtn.disabled = false;
            }
          }, 2000);
        })
        .catch(function (e) {
          fail("تعذّر الاتصال: " + (e && e.message ? e.message : e), syncBtn);
        });
    });
  }

  pollScanStatus();
  EVERY(5000, pollScanStatus);


  // ── إظهار الأعمدة الثانوية ────────────────────────────────
  var colsBtn = document.getElementById("cols-toggle");
  var tbl = document.getElementById("tbl");
  if (colsBtn && tbl) {
    colsBtn.addEventListener("click", function () {
      var compact = tbl.classList.toggle("compact");
      colsBtn.classList.toggle("active", !compact);
      colsBtn.textContent = compact ? "كل الأعمدة" : "الأعمدة الأساسية";
      // ‏+52px لعمود الحظر المضاف
      tbl.style.minWidth = compact ? "1546px" : "1974px";
    });
  }

  if (tbody) {
    tbody.addEventListener("click", function (e) {
      var blk = e.target.closest(".sym-block");
      if (blk) {
        e.preventDefault();
        var sym = blk.getAttribute("data-symbol");
        /* التأكيد لأنّ الأثر واسع: يُستبعد من المسح كلّه لا من
           هذا الصفّ. والتراجع من صفحة «الرموز المحظورة». */
        if (!window.confirm("حظر " + sym + " شرعياً؟\n" +
              "سيُستبعد من المسح والتحليل وفتح الصفقات.\n" +
              "يمكن رفع الحظر من صفحة «الرموز المحظورة».")) return;
        blk.disabled = true;
        window.postJSON("/api/blocked/add/", new URLSearchParams({
          market: blk.getAttribute("data-market"), symbols: sym,
          scope: "base", reason: "غير جائز شرعاً",
        })).then(function (d) {
          /* ═══ الفشل يُفحص من الحمولة لا من الرفض ═══
           *
           * ‏postJSON **لا يرفض أبداً**: يعيد ``{ok:false, reason}``
           * عند الخطأ. فـ ``.catch`` وحده شبكةٌ لا يقع فيها شيء —
           * والفشل كان يمرّ كأنّه نجاح.
           *
           * وهذا ما جعل رمزين يُحظران وواحداً يُسجَّل: الثاني فشل
           * وبدا ناجحاً.
           */
          if (!d || d.ok === false) {
            blk.disabled = false;
            blk.style.color = "var(--ds-risk)";
            var why = (d && d.reason) || "سبب غير معروف";
            blk.title = "تعذّر الحظر: " + why;
            window.alert("تعذّر حظر " + sym + "\n" + why);
            return;
          }
          var added = (d.added && d.added.length) ? d.added.length : 0;
          var tr = blk.closest("tr");
          if (tr) {
            tr.style.opacity = "0.4";
            tr.title = added ? "حُظر — يختفي عند التحديث" : "محظور سلفاً";
          }
          blk.textContent = added ? "✓" : "مسبقاً";
        }).catch(function (err) {
          /* انقطاع شبكة — وهذا وحده ما يصل هنا */
          blk.disabled = false;
          blk.style.color = "var(--ds-risk)";
          window.alert("تعذّر الاتصال أثناء حظر " + sym + "\n" + err);
        });
        return;
      }
      var btn = e.target.closest(".ai-scan-analyze");
      if (!btn) return;
      e.preventDefault();
      var sym = btn.getAttribute("data-symbol");
      var opts = {
        symbol: sym,
        market: btn.getAttribute("data-market"),
        timeframe: btn.getAttribute("data-tf"),
      };
      if (window.Advice) {
        // صفّ الماسح يحمل الأرقام كاملةً — تُمرَّر كي تُبنى
        // الأدلّة على إعدادٍ مطابق لا على السوق وحده.
        var r = state.rows.find(function (x) { return x.symbol === sym; });
        if (r) {
          opts.grade = r.grade === "—" ? "" : r.grade;
          opts.action = r.action;
          opts.score = r.score;
          opts.rr = r.rr;
          opts.entry = r.entry;
          opts.stop = r.stop;
          opts.target1 = r.target1;
          opts.close = r.close;
          opts.source = "auto";
          opts.side = "buy";
        }
        Advice.openSetup(opts);
      } else if (window.AIExplain) {
        AIExplain.runManualAnalysis(opts);
      }
    });
  }
})();
