/* دليل الشركات — جلبٌ على مرحلتين مع تقدّم مرئيّ.
 *
 * ═══ لماذا استعلام تقدّم لا انتظار ═══
 *
 * جلب تاريخ ثلاثمئة شركة يستغرق دقائق. والطلب المتزامن ينتهي بمهلة
 * الخادم، فيرى المستخدم خطأً بينما العمل يجري فعلاً — و«طال» و«فشل»
 * حالتان لا يجوز أن تبدوا واحدة.
 *
 * فالخادم يبدأ في خيط ويعود فوراً، وهذا يستعلم كل ثانيتين. والاستعلام
 * يتوقّف حين تنتهي المهمّة: مؤقّتٌ لا يُلغى يبقى يطرق الخادم إلى ما
 * لا نهاية.
 */
(function () {
  "use strict";

  var panel = document.getElementById("companies-panel");
  if (!panel) return;                       // ليس السوق السعودي

  var elFetch = document.getElementById("co-fetch");
  var elHist = document.getElementById("co-history");
  var elQuotes = document.getElementById("co-quotes");
  var elProg = document.getElementById("co-progress");
  var elBar = document.getElementById("co-progress-bar");
  var elNote = document.getElementById("co-progress-note");
  var elEta = document.getElementById("co-progress-eta");
  var elMsg = document.getElementById("co-msg");
  var elSummary = document.getElementById("co-summary");
  var elSearch = document.getElementById("co-search");
  var elSector = document.getElementById("co-sector");
  var tbody = document.querySelector("#co-table tbody");
  var elResume = document.getElementById("co-resume");
  var elCov = document.getElementById("co-cov");
  var elCovWarn = document.getElementById("co-cov-warn");
  var secBody = document.querySelector("#co-sec-table tbody");

  var timer = null;
  var MARKET = "saudi";

  function num(v, digits) {
    if (v === null || v === undefined || v === "") return "—";
    var n = Number(v);
    if (!isFinite(n)) return "—";
    return n.toLocaleString("ar-SA", {
      minimumFractionDigits: digits === undefined ? 2 : digits,
      maximumFractionDigits: digits === undefined ? 2 : digits
    });
  }

  function mmss(sec) {
    if (sec === null || sec === undefined) return "";
    var m = Math.floor(sec / 60), s = Math.round(sec % 60);
    return m > 0 ? "متبقٍّ ~" + m + " د " + s + " ث" : "متبقٍّ ~" + s + " ث";
  }

  function showProgress(job) {
    if (!job || job.state !== "running") {
      elProg.classList.add("d-none");
      return;
    }
    elProg.classList.remove("d-none");
    elBar.style.width = (job.percent || 0) + "%";
    elNote.textContent = (job.note || "") +
      (job.total ? "  (" + job.done + "/" + job.total + ")" : "");
    elEta.textContent = mmss(job.eta_seconds);
  }

  function setBusy(busy) {
    elFetch.disabled = busy;
    elHist.disabled = busy;
  }

  function poll() {
    fetch("/api/companies/status/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var running = null;
        ["info", "history"].forEach(function (k) {
          if (d[k] && d[k].state === "running") running = d[k];
        });
        showProgress(running);
        setBusy(!!running);

        if (!running) {
          stopPoll();
          var last = (d.history && d.history.state !== "idle" &&
                      d.history.elapsed >= (d.info ? d.info.elapsed : 0))
            ? d.history : d.info;
          if (last && last.state === "failed") {
            elMsg.innerHTML = '<span style="color:var(--down)">✗ ' +
              (last.note || "تعذّر") + " — " + (last.error || "") + "</span>";
          } else if (last && last.state === "done") {
            elMsg.innerHTML = '<span style="color:var(--up)">✓ ' +
              (last.note || "اكتمل") + "</span>";
          }
          load();
        }
      })
      .catch(function () { stopPoll(); });
  }

  function startPoll() {
    if (timer) return;
    timer = setInterval(poll, 2000);
    poll();
  }

  function stopPoll() {
    if (timer) { clearInterval(timer); timer = null; }
  }

  function load() {
    var qs = "?market=" + encodeURIComponent(MARKET);
    if (elSearch.value.trim()) qs += "&q=" + encodeURIComponent(elSearch.value.trim());
    if (elSector.value) qs += "&sector=" + encodeURIComponent(elSector.value);

    fetch("/api/companies/" + qs)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) return;
        elSummary.textContent = d.total
          ? d.total + " شركة · " + d.with_history + " لها تاريخ · " +
            d.without_history + " بلا تاريخ"
          : "لا شركات بعد";

        // القطاعات تُبنى مرّة: إعادة بنائها في كل تحميل تُفقد الاختيار
        if (elSector.options.length <= 1 && d.sectors.length) {
          d.sectors.forEach(function (s) {
            var o = document.createElement("option");
            o.value = s; o.textContent = s;
            elSector.appendChild(o);
          });
        }

        if (!d.rows.length) {
          tbody.innerHTML = '<tr><td colspan="7" class="muted small">' +
            (d.total ? "لا نتائج لهذا البحث."
                     : "لا شركات بعد — اضغط «جلب الشركات».") + "</td></tr>";
          return;
        }
        openRow = null;   // الجدول يُعاد بناؤه فيسقط المرجع
        tbody.innerHTML = d.rows.map(function (c) {
          var chg = c.change_pct;
          var cls = chg === null || chg === undefined ? "muted"
                  : (chg >= 0 ? "up" : "down");
          var hist = c.candles > 0
            ? '<span class="up">' + c.candles + "</span>"
            : '<span class="muted">—</span>';
          var canOpen = c.candles > 0;
          return '<tr class="co-row' + (canOpen ? " co-open" : "") +
            '" data-sym="' + c.symbol + '">' +
            "<td>" + (canOpen
              ? '<button class="btn btn-sm btn-link p-0 co-toggle" ' +
                'data-sym="' + c.symbol + '" title="اعرض الشارت والتحليل">' +
                "▸ " + c.symbol + "</button>"
              : '<span class="muted" title="لا شموع بعد">' + c.symbol +
                "</span>") +
            ' <a class="small muted" href="/symbol/' + MARKET + "/" +
              encodeURIComponent(c.symbol) + '/" title="الصفحة الكاملة">⤢</a>' +
            "</td>" +
            "<td>" + (c.name || "—") + "</td>" +
            '<td class="small muted">' + (c.sector || "—") + "</td>" +
            '<td class="text-end">' + num(c.price) + "</td>" +
            '<td class="text-end ' + cls + '">' +
              (chg === null || chg === undefined ? "—" : num(chg, 2) + "٪") +
            "</td>" +
            '<td class="text-end">' + num(c.pe, 1) + "</td>" +
            '<td class="text-end">' + hist + "</td>" +
            "</tr>";
        }).join("");
      })
      .catch(function () { /* الصفحة تبقى صالحة */ });

    loadSectors();
  }

  /* ═══ القطاعات ═══
   *
   * التغطية أوّل ما يُعرَض. جدولٌ يصف ٨٫٥٪ من السوق ويبدو كأنّه
   * يصفه كلّه أخطر من لا شيء — قارئ الجدول لا يرى ما ليس فيه.
   */
  function loadSectors() {
    fetch("/api/companies/sectors/?market=" + encodeURIComponent(MARKET))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) return;
        var c = d.coverage || {};
        elCov.textContent = "تغطية القطاع " + (c.sector || 0) + "٪ · " +
          "السعر " + (c.price || 0) + "٪ · التاريخ " + (c.history || 0) + "٪";
        elCov.className = "small " + (d.readable ? "up" : "warn");

        if (d.readable) {
          elCovWarn.classList.add("d-none");
        } else {
          elCovWarn.classList.remove("d-none");
          elCovWarn.textContent = d.note;
        }

        if (!d.sectors.length) {
          secBody.innerHTML = '<tr><td colspan="7" class="muted small">' +
            "لا قطاعات بعد — القطاع يأتي مع «جلب الشركات ومعلوماتها»." +
            "</td></tr>";
          return;
        }
        var html = d.sectors.map(function (s) {
          var med = s.median_change;
          var cls = med === null ? "muted" : (med >= 0 ? "up" : "down");
          /* العيّنة الضئيلة تُعرَض ولا يُحكَم بها: الوسيط على شركتين
             ليس وسيطاً بل حالتين. */
          var thin = s.thin
            ? ' <span class="muted" title="عيّنة دون ' + d.min_sector_n +
              '">⚠</span>' : "";
          return "<tr>" +
            "<td>" + s.sector + thin + "</td>" +
            '<td class="text-end">' + s.count + "</td>" +
            '<td class="text-end muted">' + (s.nomu || "—") + "</td>" +
            '<td class="text-end ' + cls + '">' +
              (med === null ? "—" : num(med, 2) + "٪") + "</td>" +
            '<td class="text-end small">' +
              '<span class="up">' + s.advancers + "</span> / " +
              '<span class="down">' + s.decliners + "</span></td>" +
            '<td class="text-end">' + num(s.median_pe, 1) + "</td>" +
            '<td class="text-end">' + s.with_history + "/" + s.count +
            "</td></tr>";
        }).join("");
        if (d.unclassified) {
          html += '<tr><td class="muted">(بلا قطاع)</td>' +
            '<td class="text-end muted">' + d.unclassified + "</td>" +
            '<td colspan="5" class="muted small">' +
            "لم تُجلب معلوماتها بعد</td></tr>";
        }
        secBody.innerHTML = html;
      })
      .catch(function () {});
  }

/* ═══ الشارت والتحليل داخل الصفّ ═══
   *
   * الرسم من ``/api/chart/`` نفسه الذي تستعمله صفحة الرمز — لا حساب
   * ثانٍ ولا مصدر ثانٍ. ومصدران يرسمان السهم نفسه يختلفان يوماً ما،
   * وحينها لا يُعرَف أيّهما الصادق.
   *
   * والرسم شموعٌ حقيقية لا خطّ إغلاق: الخطّ يُخفي الفتيل، والفتيل هو
   * موضع الوقف غالباً.
   */
  var openRow = null;

  function drawCandles(cv, candles) {
    var ctx = cv.getContext("2d");
    var W = cv.width, H = cv.height;
    ctx.clearRect(0, 0, W, H);
    if (!candles || candles.length < 2) return;

    var n = Math.min(candles.length, 180);
    var view = candles.slice(candles.length - n);
    var hi = -Infinity, lo = Infinity;
    view.forEach(function (k) {
      if (k.high > hi) hi = k.high;
      if (k.low < lo) lo = k.low;
    });
    if (!isFinite(hi) || !isFinite(lo) || hi === lo) return;
    var pad = (hi - lo) * 0.06;
    hi += pad; lo -= pad;

    var w = W / n;
    var body = Math.max(1, Math.min(w * 0.62, 9));
    function y(v) { return H - ((v - lo) / (hi - lo)) * H; }

    view.forEach(function (k, i) {
      var x = i * w + w / 2;
      var up = k.close >= k.open;
      ctx.strokeStyle = up ? "#3ddc97" : "#ff6b6b";
      ctx.fillStyle = ctx.strokeStyle;
      ctx.beginPath();
      ctx.moveTo(x, y(k.high));
      ctx.lineTo(x, y(k.low));
      ctx.stroke();
      var yo = y(k.open), yc = y(k.close);
      var top = Math.min(yo, yc);
      ctx.fillRect(x - body / 2, top, body, Math.max(1, Math.abs(yc - yo)));
    });
  }

  function fmtOrDash(v, d) { return num(v, d); }

  function renderAnalysis(d) {
    var reco = d.recommendation || {};
    function chip(label, value, cls) {
      return '<span class="me-3"><span class="muted">' + label +
        '</span> <span class="' + (cls || "") + '">' + value + "</span></span>";
    }
    var decisionCls = /شراء|صاعد/.test(d.decision || "") ? "up"
                    : (/بيع|هابط/.test(d.decision || "") ? "down" : "");
    var html = '<div class="small mb-2">' +
      chip("النقاط", fmtOrDash(d.score, 1)) +
      chip("القرار", d.decision || "—", decisionCls) +
      chip("الالتقاء", d.confluence === undefined ? "—" : d.confluence) +
      chip("الفريم الأعلى", d.htf_text || (d.htf ? "موافق" : "—")) +
      chip("RSI", fmtOrDash(d.rsi, 1)) +
      chip("RVOL", fmtOrDash(d.rvol, 2)) +
      chip("ATR٪", fmtOrDash(d.atr_pct, 2)) +
      chip("شموع", d.candles_count || "—") +
      "</div>";

    /* «مكتمل الشروط» و«حُجب ولماذا» أهمّ من النقاط: النقاط رقمٌ
       يُقارَن، والحاجب سببٌ يُعالَج. */
    if (d.ready) {
      html += '<div class="small up mb-2">✓ مكتمل الشروط</div>';
    } else if (d.blocker) {
      html += '<div class="small warn mb-2">⛔ حُجب: ' + d.blocker + "</div>";
    }

    if (reco && reco.action) {
      html += '<div class="small mb-2">' +
        chip("التوصية", reco.action, "fw-semibold") +
        chip("دخول", fmtOrDash(reco.entry)) +
        chip("وقف", fmtOrDash(reco.stop), "down") +
        chip("هدف", fmtOrDash((reco.targets || [])[0]), "up") +
        chip("ع/م", fmtOrDash(reco.rr, 2)) +
        (reco.grade ? chip("التقدير", reco.grade) : "") +
        "</div>";
      if (reco.trigger) {
        html += '<div class="small muted">' + reco.trigger + "</div>";
      }
    }
    return html;
  }

  function toggleRow(sym, tr) {
    // صفٌّ واحد مفتوح: فتح الجميع يحوّل الجدول إلى صفحة لا تُقرأ،
    // ويطلب عشرات الشارتات دفعةً واحدة.
    if (openRow && openRow.sym === sym) {
      openRow.el.remove();
      openRow = null;
      tr.querySelector(".co-toggle").textContent = "▸ " + sym;
      return;
    }
    if (openRow) {
      openRow.el.remove();
      var prev = tbody.querySelector('.co-toggle[data-sym="' + openRow.sym + '"]');
      if (prev) prev.textContent = "▸ " + openRow.sym;
      openRow = null;
    }

    var det = document.createElement("tr");
    det.innerHTML = '<td colspan="7">' +
      '<div class="small muted mb-1">يُحمَّل الشارت والتحليل…</div>' +
      '<canvas width="900" height="180" ' +
      'style="width:100%;height:180px"></canvas>' +
      '<div class="co-analysis mt-2"></div></td>';
    tr.parentNode.insertBefore(det, tr.nextSibling);
    openRow = { sym: sym, el: det };
    tr.querySelector(".co-toggle").textContent = "▾ " + sym;

    fetch("/api/chart/" + MARKET + "/" + encodeURIComponent(sym) + "/")
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var note = det.querySelector(".small");
        if (d.error) {
          note.innerHTML = '<span style="color:var(--down)">✗ ' +
            d.error + "</span>";
          return;
        }
        note.textContent = sym + " · " + (d.timeframe || "") + " · " +
          (d.candles_count || 0) + " شمعة";
        drawCandles(det.querySelector("canvas"), d.candles);
        det.querySelector(".co-analysis").innerHTML = renderAnalysis(d);
      })
      .catch(function (e) {
        det.querySelector(".small").innerHTML =
          '<span style="color:var(--down)">✗ ' + e + "</span>";
      });
  }

  tbody.addEventListener("click", function (e) {
    var btn = e.target.closest(".co-toggle");
    if (!btn) return;
    e.preventDefault();
    toggleRow(btn.getAttribute("data-sym"), btn.closest("tr"));
  });

  elFetch.addEventListener("click", function () {
    elMsg.textContent = "";
    var body = new URLSearchParams({
      market: MARKET,
      quotes: elQuotes.checked ? "1" : "0",
      fundamentals: elQuotes.checked ? "1" : "0",
      only_missing: elResume.checked ? "1" : "0"
    });
    setBusy(true);
    window.postJSON("/api/companies/fetch/", body)
      .then(function (d) {
        if (d && d.already) elMsg.textContent = "جلبٌ جارٍ بالفعل.";
        startPoll();
      })
      .catch(function (e) {
        setBusy(false);
        elMsg.innerHTML = '<span style="color:var(--down)">✗ ' + e + "</span>";
      });
  });

  elHist.addEventListener("click", function () {
    elMsg.textContent = "";
    var body = new URLSearchParams({ market: MARKET, only_missing: "1" });
    setBusy(true);
    window.postJSON("/api/companies/history/", body)
      .then(function (d) {
        if (d && d.already) elMsg.textContent = "جلبٌ جارٍ بالفعل.";
        startPoll();
      })
      .catch(function (e) {
        setBusy(false);
        elMsg.innerHTML = '<span style="color:var(--down)">✗ ' + e + "</span>";
      });
  });

  var searchTimer = null;
  elSearch.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(load, 250);   // لا طلب على كل حرف
  });
  elSector.addEventListener("change", load);

  // الحالة عند فتح الصفحة: مهمّةٌ بدأت في تبويب آخر يجب أن تُرى هنا.
  fetch("/api/companies/status/")
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if ((d.info && d.info.state === "running") ||
          (d.history && d.history.state === "running")) startPoll();
    })
    .catch(function () {});
  load();
})();
