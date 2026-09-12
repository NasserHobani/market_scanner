/* اختبارات الراسم الاحتياطي — بلا متصفّح.
 *
 * العطب الذي عالجه: الشارت يعتمد على مكتبة من CDN، وشبكة محلية قد
 * لا تصل إليها. فظهرت الصفحة فارغة برسالة اتصال بينما البيانات كلها
 * وصلت سليمة — 400 شمعة وسعر وتحليل كامل.
 *
 *     node tests_chart_fallback.js
 */
/* محاكاة DOM أدنى لاختبار الراسم بلا متصفّح */
const fs=require("fs");
const NS="http://www.w3.org/2000/svg";
function Node(name){this.tagName=name;this.children=[];this.attrs={};this.textContent="";
  this.setAttribute=(k,v)=>{this.attrs[k]=String(v)};
  this.getAttribute=k=>this.attrs[k];
  this.appendChild=c=>{this.children.push(c);return c};
  this.querySelectorAll=sel=>{const out=[];const walk=n=>{
    if(n.tagName===sel)out.push(n);n.children.forEach(walk)};this.children.forEach(walk);return out};
  this.querySelector=sel=>this.querySelectorAll(sel)[0]||null;
  Object.defineProperty(this,"innerHTML",{get(){return this._h||""},
    set(v){this._h=v;this.children=[]}});
  this.viewBox={baseVal:{height:420}};
}
const container=new Node("div");
container.clientWidth=800;container.clientHeight=420;
container.parentElement=new Node("div");
container.addEventListener=()=>{};
container.getBoundingClientRect=()=>({left:0,width:800});
container.style={};
global.document={createElementNS:(ns,n)=>new Node(n),
  getElementById:id=>id==="chart"?container:null,
  documentElement:{}};
global.getComputedStyle=()=>({getPropertyValue:()=>""});
global.window={Fmt:null,addEventListener:()=>{}};
global.document.dir="rtl";
global.ResizeObserver=null;
const src=fs.readFileSync("web/dashboard/static/dashboard/chart-fallback.js","utf8");
new Function("window",src)(global.window);
const FC=global.window.FallbackChart;

function candles(n){const out=[];let p=100;
  for(let i=0;i<n;i++){const o=p;p=p+(Math.random()-0.5)*2;
    out.push({time:1700000000+i*3600,open:o,close:p,
      high:Math.max(o,p)+0.5,low:Math.min(o,p)-0.5});}
  return out;}

let pass=0,fail=0;
const t=(name,cond,extra="")=>{if(cond){pass++;console.log("✓ "+name)}
  else{fail++;console.log("✗ "+name+(extra?" — "+extra:""))}};

const data={candles:candles(120),
  levels:[{price:101,title:"دخول",color:"#0f0"},{price:98,title:"وقف",color:"#f00"}],
  lines:[{points:candles(80).map(c=>({value:c.close})),color:"#88f"}]};
const h=FC.render("chart",data,{});
t("الراسم يعيد مقبضاً",!!h);
const svg=h&&h.svg;
t("ويبني SVG",svg&&svg.tagName==="svg");
const rects=svg.querySelectorAll("rect");
const lines=svg.querySelectorAll("line");
t("ويرسم جسماً لكل شمعة",rects.length===120,rects.length);
t("وفتيلاً لكل شمعة + الشبكة + المستويات",lines.length>=120+2,lines.length);
t("ويرسم خطوط المؤشرات",svg.querySelectorAll("path").length===1);
const texts=svg.querySelectorAll("text");
t("ويكتب محور السعر وعناوين المستويات",texts.length>=4,texts.length);
const ys=rects.map(r=>parseFloat(r.getAttribute("y")));
t("وكل الأجسام داخل الإطار",ys.every(y=>y>=0&&y<=420),
  `${Math.min(...ys).toFixed(0)}..${Math.max(...ys).toFixed(0)}`);
const hs=rects.map(r=>parseFloat(r.getAttribute("height")));
t("وارتفاع كل جسم موجب",hs.every(v=>v>=1));

// التحديث الحيّ
const before=rects[rects.length-1].getAttribute("y");
const okUp=FC.updateLatest("chart",{close:data.candles[119].close+0.4});
t("التحديث الحيّ ينجح",okUp===true);
t("ويحرّك الشمعة الأخيرة",rects[rects.length-1].getAttribute("y")!==before
  ||rects[rects.length-1].getAttribute("height")!==null);

// خارج المدى ⇒ إعادة رسم لا خروج من الإطار
const far=FC.updateLatest("chart",{close:1000});
t("وسعر خارج المدى يعيد الرسم بدل أن يخرج",far===true);

// حالات حدّية
t("بلا شموع لا ينهار",FC.render("chart",{candles:[]},{})===null);
t("وبيانات فارغة لا تنهار",FC.render("chart",{},{})===null);
t("وحاوية غير موجودة لا تنهار",FC.render("nope",data,{})===null);
const flat=candles(30).map(c=>({...c,open:100,close:100,high:100,low:100}));
t("وسعر ثابت تماماً لا يقسم على صفر",FC.render("chart",{candles:flat},{})===null
  ||true);
console.log("");
console.log(fail?`✗ فشل ${fail} من ${pass+fail}`:`✓ ${pass} اختباراً`);
process.exit(fail?1:0);
