"""تقرير HTML: ملف واحد قابل للفرز، يُفتح على الجوال."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..formatting import price as fmt_price

TEMPLATE = """<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{refresh}<title>{title}</title><style>
:root{{color-scheme:dark}}
body{{background:#0f1115;color:#e6e6e6;font:14px/1.6 system-ui,'Segoe UI',Tahoma,sans-serif;margin:0;padding:16px}}
h1{{font-size:18px;margin:0 0 4px}} .meta{{color:#8b93a7;font-size:12px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:8px 10px;text-align:right;border-bottom:1px solid #232838;white-space:nowrap}}
th{{background:#171b26;cursor:pointer;position:sticky;top:0;user-select:none}}
th:hover{{background:#1e2433}} tr:hover td{{background:#151925}}
.buy{{color:#3ddc97;font-weight:600}} .sell{{color:#ff6b6b;font-weight:600}} .flat{{color:#8b93a7}}
.ready{{background:#132a1f}} a{{color:#6aa9ff;text-decoration:none}}
.reasons{{color:#c9b458;font-size:12px;white-space:normal;max-width:260px}}
.live{{display:inline-block;width:8px;height:8px;border-radius:50%;background:#3ddc97;margin-right:6px;animation:p 2s infinite}}
@keyframes p{{0%,100%{{opacity:1}}50%{{opacity:.25}}}}
.note{{margin-top:16px;color:#8b93a7;font-size:12px}}
</style></head><body>
<h1>{title}{live_dot}</h1><div class="meta">{meta} · الأسعار: <b id="feed">—</b></div>
<table id="t"><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>
<div class="note">الصفوف المظللة استوفت كل الشروط. اضغط عنوان أي عمود للفرز.<br>
<b>السعر الآن</b> يتحدّث لحظياً من بثّ بينانس · <b>الانزياح</b> هو ابتعاده عن إغلاق الشمعة التي بُنيت عليها الإشارة.</div>
<script>
document.querySelectorAll('#t th').forEach((th,i)=>th.onclick=()=>{{
  const tb=document.querySelector('#t tbody'),rows=[...tb.rows];
  const dir=th.dataset.d==='1'?-1:1; th.dataset.d=dir===1?'1':'0';
  rows.sort((a,b)=>{{const x=a.cells[i].dataset.v??a.cells[i].innerText,
    y=b.cells[i].dataset.v??b.cells[i].innerText;
    const nx=parseFloat(x),ny=parseFloat(y);
    return (!isNaN(nx)&&!isNaN(ny))?(nx-ny)*dir:String(x).localeCompare(String(y),'ar')*dir;}});
  rows.forEach(r=>tb.appendChild(r));}});
</script>{feed_js}</body></html>"""

COLUMNS = [
    ("symbol", "الرمز"), ("score", "النقاط"), ("decision", "القرار"),
    ("confluence", "الالتقاء"), ("reasons", "الأسباب"), ("htf", "الفريم الأعلى"),
    ("close", "إغلاق الشمعة"), ("__live", "السعر الآن"), ("__drift", "الانزياح"),
    ("rsi", "RSI"), ("rvol", "RVOL"), ("atr_pct", "ATR%"), ("blocker", "المانع"),
]


def _decision_class(text: str) -> str:
    if "شراء" in str(text):
        return "buy"
    if "بيع" in str(text):
        return "sell"
    return "flat"


def build(df: pd.DataFrame, market: str, timeframe: str,
          refresh_seconds: int | None = None, next_scan: str | None = None) -> str:
    cols = [(k, label) for k, label in COLUMNS if k.startswith("__") or k in df.columns]
    head = "".join(f"<th>{label}</th>" for _, label in cols)

    body = []
    for _, r in df.iterrows():
        cls = " class='ready'" if r.get("ready") else ""
        cells = []
        for key, _ in cols:
            v = r.get(key, "")
            if key == "__live":
                cells.append("<td class='lp'>—</td>")
                continue
            if key == "__drift":
                cells.append("<td class='lc'>—</td>")
                continue
            if key == "symbol" and r.get("chart"):
                cell = f"<td data-v='{v}'><a href='{r['chart']}' target='_blank'>{v}</a></td>"
            elif key == "decision":
                cell = f"<td class='{_decision_class(v)}'>{v}</td>"
            elif key == "htf":
                txt = {1: "صاعد ↑", -1: "هابط ↓"}.get(int(v) if pd.notna(v) else 0, "مختلط —")
                cell = f"<td data-v='{v}' class='{_decision_class('شراء' if v == 1 else 'بيع' if v == -1 else '')}'>{txt}</td>"
            elif key == "reasons":
                cell = f"<td class='reasons'>{v}</td>"
            elif isinstance(v, float):
                cell = f"<td data-v='{v}'>{fmt_price(v)}</td>"
            else:
                cell = f"<td>{v}</td>"
            cells.append(cell)
        body.append(f"<tr{cls} data-close='{r.get('close', 0)}'>" + "".join(cells) + "</tr>")

    ready_n = int(df["ready"].sum()) if "ready" in df.columns else 0
    meta = (f"{len(df)} رمزاً · {ready_n} مكتمل الشروط · "
            f"آخر تحديث {pd.Timestamp.now('UTC').strftime('%Y-%m-%d %H:%M')} UTC")
    if next_scan:
        meta += f" · المسح القادم {next_scan}"

    refresh = ""
    live_dot = ""
    if refresh_seconds:
        # تحديث الصفحة ذاتياً حتى تبقى مفتوحة أمامك بلا إعادة تحميل يدوي
        refresh = f'<meta http-equiv="refresh" content="{refresh_seconds}">\n'
        live_dot = '<span class="live" title="متابعة حية"></span>'

    return TEMPLATE.format(title=f"ماسح {market} · {timeframe}", meta=meta,
                           head=head, rows="".join(body),
                           refresh=refresh, live_dot=live_dot,
                           feed_js=FEED_JS)


def write(df: pd.DataFrame, market: str, timeframe: str, out_dir: str = "reports",
          refresh_seconds: int | None = None, next_scan: str | None = None) -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"{market}_{timeframe}.html"
    path.write_text(build(df, market, timeframe, refresh_seconds, next_scan),
                    encoding="utf-8")
    return path


FEED_JS = r'''
<script>
(function(){
 var rows=[...document.querySelectorAll('#t tbody tr')].map(function(tr){
   var a=tr.querySelector('a'); if(!a) return null;
   return {sym:a.textContent.trim(), tr:tr,
           closed:parseFloat(tr.dataset.close||'0'),
           live:tr.querySelector('.lp'), chg:tr.querySelector('.lc')};
 }).filter(Boolean).filter(function(r){return /USDT$/.test(r.sym);});
 if(!rows.length) return;
 var byS={}; rows.forEach(function(r){byS[r.sym]=r;});
 var st=document.getElementById('feed'); var hosts=[
  'wss://stream.binance.com:9443/stream?streams=',
  'wss://data-stream.binance.vision/stream?streams='];
 var hi=0, tries=0, last={};
 function fmt(v){return v>=1000?v.toLocaleString(undefined,{maximumFractionDigits:2}):v>=1?v.toFixed(4):v.toPrecision(4);}
 function conn(){
  var url=hosts[hi%hosts.length]+rows.map(function(r){return r.sym.toLowerCase()+'@miniTicker';}).join('/');
  var ws; try{ws=new WebSocket(url);}catch(e){return retry();}
  if(st){st.textContent='يتصل…';st.style.color='#8b93a7';}
  ws.onopen=function(){tries=0;if(st){st.textContent='بثّ حي';st.style.color='#3ddc97';}};
  ws.onclose=function(){hi++;retry();};
  ws.onerror=function(){if(st){st.textContent='انقطع';st.style.color='#ff6b6b';}};
  ws.onmessage=function(e){
   var d; try{d=JSON.parse(e.data).data;}catch(x){return;}
   if(!d||!d.s)return; var r=byS[d.s]; if(!r)return;
   var p=parseFloat(d.c), o=parseFloat(d.o), prev=last[d.s]; last[d.s]=p;
   if(r.live){r.live.textContent=fmt(p);
     r.live.style.color=prev===undefined?'':(p>prev?'#3ddc97':p<prev?'#ff6b6b':'');}
   if(r.chg&&o>0&&r.closed>0){
     var dr=(p-r.closed)/r.closed*100;
     r.chg.textContent=(dr>=0?'+':'')+dr.toFixed(2)+'%';
     r.chg.style.color=Math.abs(dr)>=1.5?'#e0b341':'#8b93a7';}
  };
 }
 function retry(){tries++;setTimeout(conn,Math.min(30000,1000*Math.pow(2,Math.min(tries,5))));}
 conn();
})();
</script>'''
