#!/usr/bin/env python3
"""Build docs/index.html (the reader's merged version) from book/*.md and the built figures.
Run from the repo root:  uv run --no-project --with markdown-it-py --with pyyaml python tools/build_site.py
Math needs KaTeX once:  cd tools && npm ci
Book math is MathML (KaTeX output "mathml") set in tools/fonts/GPUBookMath-subset.woff2; tools/subset_math_font.py makes it.
Figures keep KaTeX HTML and vendor/katex.
"""
import bisect, hashlib, html, html.parser, json, os, re, shutil, subprocess, sys
from pathlib import Path
from markdown_it import MarkdownIt

import charts

ZH_BOOK = Path("/Users/yufanfei/GolandProjects/open-kernel-challenge-triad/audit_out/w25/orch/gpu_tutor/book")
LANG = os.environ.get("BOOK_LANG", "zh")
if LANG not in ("zh", "en"):
    sys.exit("BOOK_LANG must be zh or en")
EN = LANG == "en"
FIG_OPEN = "Open figure at full size" if EN else "在新标签页查看原尺寸大图"
SRC_BOOK = Path(os.environ.get("BOOK_SRC") or ZH_BOOK)
SRC_FIGS = Path(os.environ.get("BOOK_FIGS") or ZH_BOOK / "figs")  # zh figures; the en page falls back to them
SRC_FIGS_EN = Path(os.environ.get("BOOK_FIGS_EN") or SRC_BOOK / "figs_en")  # figs_en/<id>/<id>.html
REPO = Path(__file__).resolve().parent.parent
BG_TREE = os.environ.get("BG_TREE", "1") == "1"  # background hardware skill tree (tools/bg_tree.py)
PREVIEW = os.environ.get("BOOK_OUT")  # preview build: one self-contained site per language in BOOK_OUT; writes nothing in REPO
ALT_DOCS = os.environ.get("BOOK_DOCS")  # docs/ layout (zh at the root, en/ below) in another folder; writes nothing else in REPO
DOCS = Path(PREVIEW).resolve() if PREVIEW else Path(ALT_DOCS).resolve() if ALT_DOCS else REPO / "docs"
IN_REPO = not PREVIEW and not ALT_DOCS  # the default build also refreshes REPO/book, REPO/figs and README.md
OUT = DOCS if PREVIEW else DOCS / "en" if EN else DOCS
UP = "" if PREVIEW else "../" if EN else ""  # path from the page to docs/
OTHER = ("../zh/index.html" if EN else "../en/index.html") if PREVIEW else "../index.html" if EN else "en/index.html"
ORDER = ["preface", "ch00_0", "ch00", "ch00_5", "ch01", "ch02", "ch03", "ch04", "ch05", "ch06", "ch07", "ch08", "ch09", "ch10", "appA", "appB", "appC", "appD"]
FIG_PAT = r"<!--\s*FIG\s+([\w.-]+)\s*:\s*((?:图|Figure|Fig\.)\s*(?:导[一二三]|[A-Z\d.]+)-\d+).*?-->"
POST_H = '<script>(function(){function s(){var h=Math.ceil(document.body.getBoundingClientRect().height);parent.postMessage({figH:h},"*");}window.addEventListener("load",s);new ResizeObserver(s).observe(document.body);})();</script>'
PLAYER = (SRC_FIGS / "_parts" / "player.js").read_text()
KATEX_CSS_FIG = f'<link rel="stylesheet" href="{"../" * (2 if EN and not PREVIEW else 1)}vendor/katex/katex.min.css">'
FIG_H_PATH = Path(os.environ.get("FIG_HEIGHTS") or REPO / "tools" / "fig_heights.json")  # {"<lang>/<fig id>": body height at 780 px}, from tools/fig_heights.mjs
FIG_H = json.loads(FIG_H_PATH.read_text()) if FIG_H_PATH.exists() else {}
FIG_FIX = "<style>body{display:flow-root}.iso-page{margin:16px auto 12px!important}</style>"
CSS = """
:root{--ivory:#FAF9F5;--oat:#F0EEE6;--slate:#141413;--stone:#5E5D59;--clay:#CC785C;--clay-dk:#A9583E;--rule:#DEDCD1;
--serif:"Iowan Old Style","Source Han Serif SC","Noto Serif SC","Songti SC",serif;
--sans:-apple-system,"PingFang SC","Hiragino Sans GB",system-ui,sans-serif;
--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
--rail:0px;--frame:100vw;--col:38em;--main:calc(min(100vw,var(--frame)) - 2 * var(--rail));
--fw:min(780px,var(--main) - 40px);--tw:min(960px,var(--main) - 40px)}
*{box-sizing:border-box}
html{scroll-padding-top:72px;-webkit-text-size-adjust:100%}
body{margin:0;background:var(--ivory);color:var(--slate);font:18px/1.9 var(--serif);overflow-wrap:break-word;-webkit-font-smoothing:antialiased}
main{padding:0 20px 160px;min-width:0}
.col{max-width:var(--col);margin:0 auto}
p{margin:0 0 1em;text-wrap:pretty}
a{color:inherit;text-decoration:underline;text-decoration-color:var(--clay);text-decoration-thickness:1px;text-underline-offset:.22em}
a:hover{color:var(--clay-dk)}
:focus-visible{outline:2px solid var(--clay);outline-offset:2px;border-radius:2px}
strong{font-weight:600}
h1,h2,h3{font-family:var(--serif);color:var(--slate);font-weight:600;letter-spacing:0;word-break:keep-all;overflow-wrap:anywhere;text-wrap:balance}
h2{font-size:24px;line-height:1.5;margin:2.5em 0 .8em}
h3{font-size:18px;line-height:1.7;margin:2em 0 .5em}
h2 .sn{color:var(--stone);font-weight:400;margin-right:.55em;font-variant-numeric:lining-nums tabular-nums}
code{font-family:var(--mono);font-size:.8em;background:var(--oat);padding:.1em .32em;border-radius:3px;overflow-wrap:anywhere}
td code,th code{overflow-wrap:normal}
h1 code,h2 code,h3 code{font-size:.86em;background:none;padding:0}
pre{background:var(--oat);margin:1.4em 0;padding:16px 20px;border-radius:4px;font:14px/1.6 var(--mono);white-space:pre-wrap;overflow-wrap:anywhere}
pre code{background:none;padding:0;font-size:inherit}
blockquote{margin:1.4em 0;padding:0 0 0 1.1em;border-left:2px solid var(--rule);color:var(--stone)}
hr{border:none;border-top:1px solid var(--rule);margin:2.6em 0}
ul,ol{padding-left:1.4em;margin:0 0 1em}
li{margin:.3em 0}
li>p{margin:.3em 0}
li::marker{color:var(--stone)}
.tbl{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:1.6em calc(50% - var(--tw)/2)}
table{border-collapse:collapse;width:100%;font:14px/1.65 var(--sans)}
th{text-align:left;font-weight:600;border-bottom:1px solid var(--slate);padding:6px 10px 6px 0;vertical-align:bottom}
td{border-bottom:1px solid var(--rule);padding:7px 10px 7px 0;vertical-align:top}
td,th{min-width:4.5em}
td:first-child,th:first-child{min-width:0;white-space:nowrap}
.katex{font-size:1.04em;line-height:1.2;display:inline-block;max-width:100%}
math{font-family:"GPU Book Math",var(--sans)}
mtext[mathvariant=sans-serif]{font-family:var(--sans)}
mtext[mathvariant=monospace]{font-family:var(--mono);font-size:.77em}
.katex-display{display:block;text-align:center;margin:1.2em 0;padding:4px 0;overflow-x:auto;overflow-y:hidden;line-height:1.2}
.katex-display>.katex{display:inline}
.katex-display math{display:inline math;math-style:normal}
.fig{margin:2em calc(50% - var(--fw)/2);background:var(--oat);overflow-x:auto;-webkit-overflow-scrolling:touch;contain:layout paint}
.fig iframe{display:block;width:100%;height:900px;border:0}
@media(min-width:1332px){.fig iframe{height:var(--h,900px)}}
.fig-open{display:inline-block;padding:12px 0;font-size:13px}
.book{padding:104px 0 8px}
.book h1{font-size:48px;line-height:1.25;margin:0 0 .5em}
.book .sub{font-size:21px;line-height:1.7;margin:0 0 1.2em}
.book .note{font:14px/1.7 var(--sans);color:var(--stone);margin:0}
section{padding-top:clamp(112px,16vh,168px)}
.sect{content-visibility:auto;contain-intrinsic-block-size:auto var(--hm,@SECT_1100@px)}
.sect{margin-inline:min(0px,calc(50% - var(--fw)/2));padding-inline:max(0px,calc(var(--fw)/2 - 50%))}
.sect:not(.open)>:last-child{margin-bottom:0}
.ch-head{margin:0 0 26px}
.ch-num{font:400 14px/1.5 var(--sans);color:var(--stone);margin:0 0 14px}
.ch-num .lv{margin-left:1.2em}
.ch-head h1{font-size:36px;line-height:1.38;margin:0}
.map{display:flex;flex-wrap:wrap;margin:0 0 2.6em;padding:14px 0 0;border-top:1px solid var(--rule);list-style:none;font:13px/1.7 var(--sans);color:var(--stone)}
.map li{margin:0}
.map li:not(:last-child)::after{content:"\\203A";margin:0 7px;color:#b9b7ad}
.map .here{color:var(--slate);font-weight:600}
.pn{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin:4.5em 0 0;padding-top:20px;border-top:1px solid var(--rule);font-family:var(--sans)}
.pn a{text-decoration:none;display:block;line-height:1.55}
.pn a span{display:block;font-size:13px;color:var(--stone);margin-bottom:4px}
.pn a b{font-weight:500;font-size:15px}
.pn a:hover b{color:var(--clay-dk)}
.pn .next{text-align:right;grid-column:2}
body{padding-top:52px}
.bar{position:fixed;top:0;left:0;right:0;z-index:20;display:flex;align-items:center;gap:16px;height:52px;padding:0 20px;background:var(--ivory);border-bottom:1px solid var(--rule);font:14px/1.4 var(--sans)}
.bar-book{font:600 16px/1.4 var(--serif);text-decoration:none;white-space:nowrap}
.lang{flex-shrink:0;font:500 13px/1 var(--sans);white-space:nowrap;color:var(--stone)}
.lang a{text-decoration:none;color:var(--stone)}
.lang a:hover{color:var(--clay-dk)}
.lang b{color:var(--slate);font-weight:600}
.toc-head .lang{margin-left:auto}
.bar-cur{flex:1;min-width:0;color:var(--stone);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar button,.toc-close{flex-shrink:0;white-space:nowrap;font:500 14px/1 var(--sans);color:var(--slate);background:none;border:1px solid var(--rule);border-radius:4px;padding:8px 12px;cursor:pointer}
.bar button:hover,.toc-close:hover{border-color:var(--stone)}
.toc,.rail{--hang:62px;font:14px/1.5 var(--sans);background:var(--ivory);overflow-y:auto;overscroll-behavior:contain}
.toc a,.rail a{text-decoration:none;color:var(--slate)}
.toc ol,.rail ol{list-style:none;margin:0;padding:0}
.toc li,.rail li{margin:0}
.toc-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:40px 20px 10px var(--hang)}
.toc-book{font:600 17px/24px var(--serif)}
.toc .part{margin-top:20px}
.part-name{margin:0;padding:4px 14px 4px var(--hang);font-size:13.5px;line-height:1.45;font-weight:600}
.part-name span{display:block;font-size:12.5px;font-weight:400;color:var(--stone)}
.chap>a,.secs a,.rail a{position:relative;display:block}
.chap>a{padding:5px 20px 5px var(--hang);line-height:21px}
.chap>a .n,.secs a .n,.rail a .n{position:absolute;text-align:right;color:var(--stone);font-variant-numeric:lining-nums tabular-nums;white-space:nowrap}
.chap>a .n{left:0;top:5px;width:calc(var(--hang) - 14px);font-size:13px}
.chap>a:hover .t,.secs a:hover .t,.rail a:hover .t{color:var(--clay-dk)}
.chap.on>a .t{font-weight:600}
.chap.on>a .n,.secs a.here .n,.rail a.here .n{color:var(--clay);font-weight:600}
.secs{display:none;padding:2px 0 10px!important}
.chap.on .secs{display:block}
.secs a{padding:3px 20px 3px calc(var(--hang) + 22px);font-size:13px;line-height:20px;color:var(--stone)}
.secs a .n{left:var(--hang);top:3px;width:14px}
.secs a.here,.rail a.here{color:var(--slate)}
.secs code,.rail code{background:none;padding:0;font-size:.95em}
.secs .katex,.rail .katex{font-size:1em}
.rail{display:none}
.scrim{display:none}
@media(min-width:1280px){
:root{--rail:256px;--frame:1440px}
.bar{display:none}
body{padding-top:0}
.frame{display:grid;grid-template-columns:var(--rail) minmax(0,1fr) var(--rail);max-width:var(--frame);margin:0 auto}
.toc,.rail{position:sticky;top:0;align-self:start;height:100vh;padding-bottom:48px}
.toc-head{flex-wrap:wrap}
.toc-book{flex:1 1 100%}
.toc-head .lang{margin-left:var(--hang)}
.toc-close{display:none}
.toc .chap.on .secs{display:none}
.rail{display:block;--hang:28px;font-size:13.5px;padding:40px 32px 48px 4px}
.rail-head{margin:0 0 10px;padding-left:var(--hang);font-size:13px;line-height:24px;color:var(--stone)}
.rail ol{display:none}
.rail ol.on{display:block}
.rail a{padding:4px 0 4px var(--hang);line-height:20px;color:var(--stone)}
.rail a .n{left:0;top:4px;width:calc(var(--hang) - 12px);font-size:12.5px}
main{padding:0 24px 160px}
td code{overflow-wrap:anywhere}
.sect{contain-intrinsic-block-size:auto var(--hl,@SECT_1440@px)}
}
@media(max-width:1279px){
.toc{position:fixed;top:0;bottom:0;left:0;z-index:40;width:min(420px,100%);padding-bottom:48px;transform:translateX(-100%);visibility:hidden;transition:transform .22s ease,visibility 0s .22s}
.toc-head{padding-top:20px;align-items:center}
body.toc-open{overflow:hidden}
body.toc-open .toc{transform:none;visibility:visible;transition:transform .22s ease;box-shadow:0 0 40px rgba(20,20,19,.18)}
body.toc-open .scrim{display:block;position:fixed;inset:0;z-index:30;background:rgba(20,20,19,.28)}
.book{padding-top:64px}
}
@media(max-width:600px){
body{font-size:17px;line-height:1.85}
main{padding:0 18px 120px}
.bar{padding:0 14px;gap:10px}
.bar-cur{display:none}
.bar-book{flex:1}
.toc{--hang:52px}
.book{padding-top:44px}
.book h1{font-size:32px}
.book .sub{font-size:18px}
.ch-head h1{font-size:26px}
h2{font-size:21px}
section{padding-top:88px}
:root{--fw:100vw}
pre{font-size:12px;padding:12px 14px}
table{font-size:13px}
td,th{min-width:8em}
.pn{grid-template-columns:1fr;gap:16px}
.pn .next{grid-column:1}
.sect{contain-intrinsic-block-size:auto var(--hs,@SECT_390@px)}
}
@media(prefers-reduced-motion:reduce){.toc{transition:none!important}}
"""
JS = """(function(){
var d=document,b=d.body,nav=d.getElementById("toc"),rail=d.getElementById("rail"),btn=d.getElementById("toc-btn"),cur=d.getElementById("bar-cur");
var chs=[].slice.call(d.querySelectorAll("main section[id]")),navA={},railA={},items={},lists={};
[].forEach.call(nav.querySelectorAll("a[href^='#']"),function(a){navA[a.getAttribute("href").slice(1)]=a;});
[].forEach.call(rail.querySelectorAll("a[href^='#']"),function(a){railA[a.getAttribute("href").slice(1)]=a;});
[].forEach.call(nav.querySelectorAll(".chap"),function(li){items[li.dataset.ch]=li;});
[].forEach.call(rail.querySelectorAll("ol[data-ch]"),function(ol){lists[ol.dataset.ch]=ol;});
var onCh=null,onSec=null;
function mark(a,on){if(!a)return;a.classList.toggle("here",on);if(on)a.setAttribute("aria-current","location");else a.removeAttribute("aria-current");}
var above=new Map(),heads={};
function spy(force){
  var ch=chs[0],sec=null;
  for(var i=1;i<chs.length;i++){if(above.get(chs[i]))ch=chs[i];else break;}
  var hs=ch?heads[ch.id]||(heads[ch.id]=ch.querySelectorAll(".sect>h2[id]")):[];
  for(var j=0;j<hs.length;j++){if(above.get(hs[j].parentNode))sec=hs[j];else break;}
  var c=ch&&ch.id,s=sec&&sec.id,moved=force===true||c!==onCh||s!==onSec;
  if(c!==onCh){[items,lists].forEach(function(m){if(onCh&&m[onCh])m[onCh].classList.remove("on");if(c&&m[c])m[c].classList.add("on");});onCh=c;
    cur.textContent=c&&items[c]?items[c].dataset.t:"";}
  if(s!==onSec){mark(navA[onSec],false);mark(railA[onSec],false);mark(navA[s],true);mark(railA[s],true);onSec=s;}
  if(!b.classList.contains("toc-open")){keep(nav,moved&&(navA[s]&&navA[s].offsetParent?navA[s]:navA[c]));keep(rail,moved&&railA[s]);}
}
function keep(box,a){if(!a||!a.offsetParent||box.scrollHeight<=box.clientHeight)return;var r=a.getBoundingClientRect(),n=box.getBoundingClientRect();if(r.top<n.top+60||r.bottom>n.bottom-40)reveal(box,a);}
function reveal(box,a){box.scrollTop+=a.getBoundingClientRect().top-box.getBoundingClientRect().top-box.clientHeight/3;}
var t=0;function req(){if(!t)t=requestAnimationFrame(function(){t=0;spy();});}
var line=new IntersectionObserver(function(es){es.forEach(function(e){above.set(e.target,e.isIntersecting);});req();},{rootMargin:"10000000px 0px -70% 0px"});
chs.forEach(function(s){line.observe(s);});[].forEach.call(d.querySelectorAll(".sect>h2[id]"),function(h){line.observe(h.parentNode);});
addEventListener("resize",function(){spy(true);});addEventListener("load",function(){spy(true);});
var seen=new Set(),moving=false,still=0;
function mount(f){f.src=f.dataset.src;f.removeAttribute("data-src");figs.unobserve(f);seen.delete(f);}
var figs=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting)seen.add(e.target);else seen.delete(e.target);});if(!moving)seen.forEach(mount);});
[].forEach.call(d.querySelectorAll("iframe[data-src]"),function(f){figs.observe(f);});
var warm=[].slice.call(d.querySelectorAll(".sect")),skipped=new Set(),laid=new Set(),far=[],freeing=0;
[].forEach.call(warm,function(s){s.addEventListener("contentvisibilityautostatechange",function(e){if(e.skipped){skipped.add(s);if(laid.has(s)){far.push(s);if(!freeing&&window.requestIdleCallback)freeing=requestIdleCallback(freeFar);}}else{skipped.delete(s);laid.add(s);}});});
// A skipped section keeps its layout tree, and every major GC traces it. display:none drops the tree; after one style flush the
// section comes back skipped (content-visibility:auto), at its measured height (fractional: a rounded height moves what follows),
// so nothing moves. One section per idle callback. The warm-up measures with the containment of an on-screen content-visibility:auto
// section: without it the first h2's margin (60 px) collapses through the section edge and the height is 60 px short.
function free(s,h){s.style.containIntrinsicBlockSize="auto "+h+"px";s.style.display="none";getComputedStyle(s).display;s.style.display="";laid.delete(s);}
function freeFar(){freeing=0;var s=far.shift();if(s&&skipped.has(s)&&laid.has(s))free(s,s.getBoundingClientRect().height);if(far.length)freeing=requestIdleCallback(freeFar);}
function warmUp(dl){while(warm.length&&!moving&&dl.timeRemaining()>0){var s=warm.shift();if(!skipped.has(s))continue;s.style.contentVisibility="visible";s.style.contain="layout style paint";var h=s.getBoundingClientRect().height;s.style.contentVisibility=s.style.contain="";free(s,h);}if(warm.length)requestIdleCallback(warmUp);}
if(window.requestIdleCallback)addEventListener("load",function(){var i=0;while(i<warm.length-1&&warm[i].getBoundingClientRect().bottom<0)i++;warm=warm.slice(i).concat(warm.slice(0,i));requestIdleCallback(warmUp);});
addEventListener("scroll",function(){moving=true;clearTimeout(still);still=setTimeout(function(){moving=false;seen.forEach(mount);},120);},{passive:true});
function open(){b.classList.add("toc-open");btn.setAttribute("aria-expanded","true");var a=(onSec&&navA[onSec])||(onCh&&navA[onCh]);if(a)reveal(nav,a);nav.querySelector(".toc-close").focus({preventScroll:true});}
function close(){if(!b.classList.contains("toc-open"))return;b.classList.remove("toc-open");btn.setAttribute("aria-expanded","false");btn.focus({preventScroll:true});}
[].forEach.call(d.querySelectorAll(".lang a"),function(a){a.addEventListener("click",function(e){var id=onSec||onCh;e.preventDefault();location.href=a.dataset.base+(id?"#"+id:location.hash);});});
btn.addEventListener("click",open);
nav.querySelector(".toc-close").addEventListener("click",close);
d.querySelector(".scrim").addEventListener("click",close);
nav.addEventListener("click",function(e){if(e.target.closest("a"))close();});
addEventListener("keydown",function(e){if(e.key==="Escape")close();});
})();"""
UI = {
    "zh": dict(html="zh-CN", book="GPU 是怎么工作的，以及怎么优化 GPU 性能", short="GPU 是怎么工作的", toc="目录", close="关闭", rail="本章", rail_aria="本章各节",
               sub="以一张 H200 为例，从整个大模型一级一级拆到单条指令和比特：GPU 怎样工作，时间花在哪里，怎样让它更快。",
               note="中文 GPU 教程草稿，正在逐轮审读。图都可以操作：点按钮、拖时间轴。", prev="上一章", next="下一章", pn_aria="翻章",
               tog='<b>中文</b> / <a href="{o}" data-base="{o}" hreflang="en">English</a>'),
    "en": dict(html="en", book="How a GPU Works, and How to Optimize Its Performance", short="How a GPU Works", toc="Contents", close="Close", rail="This chapter", rail_aria="Sections in this chapter",
               sub="Using one H200 as the example, we zoom from a whole large model down to a single instruction and bit: how the GPU works, where the time goes, and how to make it faster.",
               note="A draft GPU tutorial, under review round by round. Every figure is interactive: press the buttons, drag the timeline.", prev="Previous chapter", next="Next chapter", pn_aria="Chapter navigation",
               tog='<a href="{o}" data-base="{o}" hreflang="zh-CN">中文</a> / <b>English</b>'),
}[LANG]
BOOK = UI["book"]
BOOK_SHORT = UI["short"]
TMPL = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{book}</title><style>{css}</style>
<script>var wide=matchMedia("(min-width:1332px)");addEventListener("message",e=>{{if(!e.data||!e.data.figH)return;document.querySelectorAll("iframe").forEach(f=>{{if(f.contentWindow===e.source){{var h=Math.ceil(e.data.figH)+4+"px";if(wide.matches&&f.style.getPropertyValue("--h")===h)h="";if(f.style.height!==h)f.style.height=h;}}}});}});</script></head>
<body>
<header class="bar"><a class="bar-book" href="#top">{short}</a><span class="bar-cur" id="bar-cur"></span><button id="toc-btn" type="button" aria-controls="toc" aria-expanded="false">{ui_toc}</button><span class="lang">{tog}</span></header>
<div class="frame">
<nav class="toc" id="toc" aria-label="{ui_toc}"><div class="toc-head"><a class="toc-book" href="#top">{short}</a><span class="lang">{tog}</span><button class="toc-close" type="button">{ui_close}</button></div><ol>{toc}</ol></nav><div class="scrim"></div>
<main><div class="col"><header class="book" id="top"><h1>{book_nb}</h1><p class="sub">{sub}</p><p class="note">{note}</p></header>
{secs}</div></main>
<aside class="rail" id="rail" aria-label="{rail_aria}"><p class="rail-head">{ui_rail}</p>{rail}</aside>
</div><script>{js}</script></body></html>"""
# Parts as listed in book/preface.md section 3 ("目录：每一章回答哪一个问题？").
PARTS_EN = [("", ["preface"]),
            ("Orientation", ["ch00_0", "ch00", "ch00_5"]),
            ("Part 1: Six Levels of Hardware Zoom", ["ch01", "ch02", "ch03", "ch04", "ch05", "ch06"]),
            ("Part 2: The Main Operators in One Layer, and the Whole Layer", ["ch07", "ch08", "ch09"]),
            ("Part 3: Diagnosis and Across Generations", ["ch10", "appA", "appB", "appC", "appD"])]
PARTS = PARTS_EN if EN else [("", ["preface"]),
         ("导引", ["ch00_0", "ch00", "ch00_5"]),
         ("第一部分　硬件六级放大", ["ch01", "ch02", "ch03", "ch04", "ch05", "ch06"]),
         ("第二部分　一层里的主力算子与整层总装", ["ch07", "ch08", "ch09"]),
         ("第三部分　诊断与跨代", ["ch10", "appA", "appB", "appC", "appD"])]
MAP_PAT = re.compile(r"<p><strong>(?:本书地图：|Book map:)</strong>\s*(.*?)</p>", re.S)

STRAY_BOLD = re.compile(r"\*\*((?:(?!</?(?:p|li|pre|h\d)\b)[^*])+?)\*\*")
SKIP = re.compile(r"(<pre.*?</pre>)", re.S)

def fix_stray_bold(h):
    """CommonMark does not close ** after full-width punctuation; render those pairs as bold."""
    return "".join(p if i % 2 else STRAY_BOLD.sub(r"<strong>\1</strong>", p) for i, p in enumerate(SKIP.split(h)))

def escape_table_code_pipes(md_text):
    """A | inside a code span splits a table cell; escape it on table rows."""
    esc = lambda line: re.sub(r"`[^`]*`", lambda c: re.sub(r"(?<!\\)\|", r"\\|", c.group(0)), line)
    return "\n".join(esc(l) if l.lstrip().startswith("|") else l for l in md_text.split("\n"))

def map_nav(m):
    items = [x.strip() for x in m.group(1).split("→")]
    li = []
    for x in items:
        cur = re.fullmatch(r"<strong>[【\[](.*?)[】\]]</strong>", x)
        li.append(f'<li class="here">{cur.group(1)}</li>' if cur else f"<li>{x}</li>")
    return '<ul class="map">' + "".join(li) + "</ul>"

README = """# GPU 是怎么工作的，以及怎么优化 GPU 性能

在线阅读（合并版，图嵌在正文里）：https://yfei1.github.io/gpu-book-zh/

一本中文 GPU 教程（草稿，正在逐轮审读）。全书以 H200 为例，一章往里放大一级硬件；一个 gemv kernel 从最朴素的写法一步步演化到排行榜提交版。

## 章节

{chapters}

## 交互图

下载后用浏览器直接打开（单文件 HTML，无外部依赖）。

{figures}
"""

def write_readme(chapters, built, page, nums):
    figs = []
    for nm, p in built.items():
        m = re.search(r"<title>(.*?)</title>", p.read_text())
        if m and nm in nums:
            figs.append((nums[nm] + " " + re.sub(r"^图 (?:导[一二三]|[A-Z\d.]+)-\d+\s*", "", html.unescape(m.group(1))), nm))
    order = [m.group(1) for m in re.finditer(r'src="figs/([^"]+)\.html"', page)]
    figs.sort(key=lambda x: order.index(x[1]) if x[1] in order else len(order))
    (REPO / "README.md").write_text(README.format(
        chapters="\n".join(f"- [{t}](book/{c}.md)" for c, t in chapters),
        figures="\n".join(f"- [{html.escape(t, quote=False)}](figs/{nm}.html)" for t, nm in figs)))


FENCE = re.compile(r"[ ]{0,3}(`{3,}|~{3,})[ \t]*([^\n`]*)\n")
KATEX = REPO / "tools" / "node_modules" / "katex" / "dist"


def protect(text, chapter, items):
    """Replace math and chart blocks by placeholders so Markdown cannot touch them. Skips code and comments."""
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    out, i, n = [], 0, len(text)

    def ph(kind, **kw):
        items.append(dict(kind=kind, chapter=chapter, line=bisect.bisect_right(starts, kw.pop("pos")), **kw))
        return f"\ue000{kind}{len(items) - 1}\ue001"

    while i < n:
        c = text[i]
        if (i == 0 or text[i - 1] == "\n") and (m := FENCE.match(text, i)):
            fence, info = m.group(1), m.group(2).strip().split(" ")[0]
            close = re.compile(r"^[ ]{0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$", re.M).search(text, m.end())
            end = close.end() if close else n
            if info == "chart":
                out.append("\n\n" + ph("C", pos=i, body=text[m.end(): close.start() if close else n]) + "\n\n")
            else:
                out.append(text[i:end])
            i = end
        elif text.startswith("<!--", i):
            j = text.find("-->", i)
            j = n if j < 0 else j + 3
            out.append(text[i:j]); i = j
        elif c == "`":
            k = i
            while k < n and text[k] == "`":
                k += 1
            para_end = text.find("\n\n", k)
            para_end = n if para_end < 0 else para_end
            found, j = -1, k
            while (j := text.find("`", j, para_end)) >= 0:
                e = j
                while e < n and text[e] == "`":
                    e += 1
                if e - j == k - i:
                    found = j
                    break
                j = e
            end = k if found < 0 else found + (k - i)
            out.append(text[i:end]); i = end
        elif c == "\\":
            out.append(text[i: i + 2]); i += 2
        elif c == "$":
            display = text.startswith("$$", i)
            open_len = 2 if display else 1
            para_end = text.find("\n\n", i)
            para_end = n if para_end < 0 else para_end
            if display:
                j = text.find("$$", i + 2)
                ok = j >= 0
            else:
                nxt = text[i + 1: i + 2]
                j = i + 1
                while (j := text.find("$", j, para_end)) >= 0 and text[j - 1] == "\\":
                    j += 1
                ok = bool(nxt) and not nxt.isspace() and nxt != "$" and j >= 0 and not text[j - 1].isspace() and not text[j + 1: j + 2].isdigit()
            if ok:
                out.append(ph("M", pos=i, tex=text[i + open_len: j].strip(), display=display)); i = j + open_len
            else:
                out.append(text[i: i + open_len]); i += open_len
        else:
            j = i + 1
            while c != "\n" and j < n and text[j] not in "`\\$<\n":
                j += 1
            out.append(text[i:j]); i = j
    return "".join(out)


def resolve(items):
    """Render math with KaTeX (node) and charts (charts.py). Returns the list of error lines."""
    errors = []
    math = [it for it in items if it["kind"] == "M"]
    if math:
        if not KATEX.exists():
            sys.exit("KaTeX is missing. Run:  cd tools && npm ci")
        res = subprocess.run(["node", str(REPO / "tools" / "katex_render.mjs"), "--mathml"], input=json.dumps([{"tex": it["tex"], "display": it["display"]} for it in math]), capture_output=True, text=True, cwd=REPO)
        if res.returncode:
            sys.exit("node failed:\n" + res.stderr)
        for it, r in zip(math, json.loads(res.stdout)):
            if "error" in r:
                errors.append(f"{it['chapter']}:{it['line']}: math error: {html.unescape(r['error'])}  in  {it['tex'][:80]}")
            else:
                it["html"] = f'<span class="katex-display">{r["html"]}</span>' if it["display"] else r["html"]
    for it in items:
        if it["kind"] == "C":
            try:
                it["html"] = charts.render(it["body"])
            except charts.ChartError as e:
                errors.append(f"{it['chapter']}:{it['line']}: chart error: {e}")
    return errors


BOOK_FONT = os.environ.get("BOOK_FONT", "google")
MATH_FONT = REPO / "tools" / "fonts" / "GPUBookMath-subset"
MATH_CSS = """@font-face{font-family:"GPU Book Math";src:url('@UP@fonts/GPUBookMath-subset.woff2') format('woff2');font-display:swap}"""


def check_math_font(items):
    """The math font is a subset: fail when the book's MathML uses a character that tools/subset_math_font.py has not seen."""
    from subset_math_font import math_chars
    seen = json.loads(MATH_FONT.with_suffix(".json").read_text())
    used = set().union(*(math_chars(it["html"]) for it in items if it["kind"] == "M" and "html" in it))
    return "".join(sorted(used - set(seen["kept"]) - set(seen["absent"])))
GOOGLE_CSS = """
@font-face{font-family:"Google Sans";src:url('@UP@fonts/GoogleSans-subset.woff2') format('woff2');font-weight:400 700;font-style:normal;font-display:swap}
@font-face{font-family:"Noto Sans SC";src:url('@UP@fonts/NotoSansSC-subset.woff2') format('woff2');font-weight:400 700;font-style:normal;font-display:swap}
:root{--sans:"Google Sans","Noto Sans SC",-apple-system,"PingFang SC","Hiragino Sans GB",system-ui,sans-serif;--serif:var(--sans)}
body{font-weight:400;line-height:1.85}
h1,h2,h3{font-weight:650}
"""


def vendor_fonts():
    dst, src = DOCS / "fonts", REPO / "tools" / "fonts"
    shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True)
    for f in [MATH_FONT.with_suffix(".woff2"), src / "GUST-FONT-LICENSE.txt"]:
        shutil.copy2(f, dst / f.name)
    if BOOK_FONT == "google":
        for f in [*src.glob("*.woff2"), *src.glob("OFL-*.txt")]:
            shutil.copy2(f, dst / f.name)


def vendor_katex():
    dst = DOCS / "vendor" / "katex"
    (dst / "fonts").mkdir(parents=True, exist_ok=True)
    css = (KATEX / "katex.min.css").read_text()
    css = re.sub(r',url\(fonts/[^)]+\.woff\) format\("woff"\),url\(fonts/[^)]+\.ttf\) format\("truetype"\)', "", css)
    (dst / "katex.min.css").write_text(css)
    for f in (KATEX / "fonts").glob("*.woff2"):
        shutil.copy2(f, dst / "fonts" / f.name)


def substitute(page, items):
    page = re.sub(r"<p>\ue000C(\d+)\ue001</p>", lambda m: items[int(m.group(1))]["html"], page)
    return re.sub(r"\ue000[MC](\d+)\ue001", lambda m: items[int(m.group(1))]["html"], page)


SHORT_TOPIC = {"导引一": "一句话怎样变成下一个词元", "导引三": "最小的 CUDA 程序", "第 9 章": "一层排上 132 个 SM",
               "第 10 章": "诊断一个慢 kernel", "附录 A": "改不动的硬件限制", "附录 B": "SASS 指令速查", "附录 D": "H200 推理硬件一览"}


SHORT_TOPIC_EN = {"Intro 1": "How a sentence becomes the next token", "Intro 3": "The smallest CUDA program", "Chapter 9": "One layer on 132 SMs",
                  "Chapter 10": "Diagnosing a slow kernel", "Appendix A": "Hardware limits you cannot change", "Appendix B": "SASS instruction cheat sheet", "Appendix D": "H200 inference hardware"}


def split_title(title):
    """'第 4 章 [第 4 级]：单个 SMSP——每个周期…？' -> ('第 4 章', '第 4 级', '单个 SMSP——每个周期…？', '单个 SMSP')."""
    num, sep, rest = re.split(r"(?<=\S)([：:])\s*", title, maxsplit=1) if re.search(r"[：:]", title) else (title, "", "")
    if not sep:
        return "", "", title, title
    lv = re.search(r"\[(.*?)\]", num)
    if EN:
        topic = re.split(r"\s+[—–]\s+|—|,", rest)[0].strip()
    else:
        topic = rest.split("——")[0] if "——" in rest else rest.split("，")[0]
    num = re.sub(r"\s*\[.*?\]", "", num).strip()
    return num, lv.group(1) if lv else "", rest, (SHORT_TOPIC_EN if EN else SHORT_TOPIC).get(num, topic)



def keep_units(h):
    """Turn spaces into no-break spaces and allow a break only after '\uff0c\uff1a\uff1b\u3001\u2014\u2014' (outside tags), for keep-all headings."""
    if EN:
        return h
    return re.sub(r"(<[^>]*>)|( )|(\u2014\u2014|[\uff0c\uff1a\uff1b\u3001])", lambda m: m.group(1) or ("\u00a0" if m.group(2) else m.group(3) + "<wbr>"), h)


def number_sections(c, body):
    """Give each '<h2>N. title</h2>' an id and a number span; return the section list for the contents."""
    out = []
    def rep(m):
        n = re.match(r"(\d+)\.\s+(.*)", m.group(1), re.S)
        sid = f"{c}-{len(out) + 1}"
        num, text = (n.group(1), n.group(2)) if n else ("", m.group(1))
        out.append((sid, num, text))
        return f'<h2 id="{sid}">' + (f'<span class="sn">{num}</span>' if num else "") + f"{keep_units(text)}</h2>"
    return "\ue002" + re.sub(r"<h2>(.*?)</h2>", rep, body, flags=re.S) + "\ue003", out  # wrap_sects() runs once math is rendered



class _TopBlocks(html.parser.HTMLParser):
    """Offsets and element counts of the top-level blocks in an HTML fragment."""
    VOID = {"br", "hr", "img", "wbr", "input", "meta", "link", "col", "source"}

    def __init__(self, text):
        super().__init__(convert_charrefs=False)
        self.starts = [0] + [m.end() for m in re.finditer("\n", text)]
        self.depth, self.blocks = 0, []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if self.depth == 0:
            line, col = self.getpos()
            self.blocks.append([self.starts[line - 1] + col, tag, 0])
        if self.blocks:
            self.blocks[-1][2] += 1
        if tag not in self.VOID:
            self.depth += 1

    def handle_startendtag(self, tag, attrs):
        if self.depth == 0:
            line, col = self.getpos()
            self.blocks.append([self.starts[line - 1] + col, tag, 0])
        self.blocks[-1][2] += 1

    def handle_endtag(self, tag):
        if tag not in self.VOID:
            self.depth -= 1


# A .sect is laid out in one task when it first comes into view. MEASURED at 4x CPU throttle (ux_review/perf/HOST_PERF.md):
# 12.4 ms + 0.0157 ms per element, so 2390 elements fit in the 50 ms long-task limit. Split larger ones before a <p>
# (margin-top 0, so the split does not change the layout).
SECT_NODES = 2390


def sect_chunks(part):
    """Split one h2 part into chunks of at most SECT_NODES elements, cut only before a top-level <p>."""
    cuts, acc = [], 0
    for off, tag, n in _TopBlocks(part).blocks:
        if tag == "p" and acc and acc + n > SECT_NODES:
            cuts.append(off); acc = 0
        acc += n
    bounds = [0] + cuts + [len(part)]
    return [part[a:b] for a, b in zip(bounds, bounds[1:])]


# A skipped .sect takes its contain-intrinsic-block-size. tools/sect_heights.mjs measures each one in a built site at the 3 widths of
# the page's breakpoints (<=600, 601-1279, >=1280 px: 390, 1100, 1440); the key is the chunk's hash. A changed chunk falls back to the
# measured median section height of its language and width ("_median" in the JSON); with no JSON, to 3700px (the earlier constant).
SECT_H_PATH = REPO / "tools" / "sect_heights.json"
SECT_H = json.loads(SECT_H_PATH.read_text()) if SECT_H_PATH.exists() else {}
SECT_BAKED = []


def sect_css(css):
    med = SECT_H.get("_median", {}).get(LANG, {})
    for w in ("390", "1100", "1440"):
        css = css.replace(f"@SECT_{w}@", str(med.get(w, 3700)))
    return css


def wrap_sects(body):
    out = []
    for part in re.split(r'(?=<h2 id=")', body):
        if not part.strip():
            continue
        chunks = sect_chunks(part)
        for i, c in enumerate(chunks):
            k = f"{LANG}/{hashlib.sha1(c.encode()).hexdigest()[:12]}"
            h = SECT_H.get(k)
            SECT_BAKED.append(bool(h))
            style = f' style="--hs:{h["390"]}px;--hm:{h["1100"]}px;--hl:{h["1440"]}px"' if h else ""
            out.append(f'<div class="sect{" open" if i + 1 < len(chunks) else ""}" data-k="{k}"{style}>{c}</div>')
    return "".join(out)


def short_num(label):
    """'第 4 章' -> '4', '附录 A' -> 'A', '导引一' -> '导一' (the book's own short form, as in '图 导一-1')."""
    m = re.fullmatch(r"第\s*(\d+)\s*章|附录\s*([A-Z])|导引([一二三])|Chapter\s+(\d+)|Appendix\s+([A-Z])|Intro\s+(\d)", label)
    if not m:
        return label
    g = m.groups()
    return g[0] or g[1] or (g[2] and "导" + g[2]) or g[3] or g[4] or "I" + g[5]


def toc_html(heads):
    """Return (contents for the left nav, per-chapter section lists for the right rail)."""
    by_id = {h[0]: h for h in heads}
    parts, rail = [], []
    for name, ids in PARTS:
        lis = []
        for c in ids:
            if c not in by_id:
                continue
            _, label, topic, plain, sec_list = by_id[c]
            secs = "".join(f'<li><a href="#{sid}"><span class="n">{num}</span><span class="t">{text}</span></a></li>' for sid, num, text in sec_list)
            lis.append(f'<li class="chap" data-ch="{c}" data-t="{html.escape(plain)}"><a href="#{c}" aria-label="{html.escape(plain)}"><span class="n">{short_num(label)}</span><span class="t">{topic}</span></a>'
                       + (f'<ol class="secs">{secs}</ol>' if secs else "") + "</li>")
            rail.append(f'<ol data-ch="{c}">{secs}</ol>')
        if lis:
            key, _, title = name.rpartition(": " if EN else "　")
            head = f'<p class="part-name">' + (f"<span>{key}</span>" if key else "") + f"{title}</p>" if name else ""
            parts.append(f'<li class="part">{head}<ol>{"".join(lis)}</ol></li>')
    missing = set(by_id) - {c for _, ids in PARTS for c in ids}
    if missing:
        sys.exit("chapters not in PARTS: " + ", ".join(sorted(missing)))
    return "".join(parts), "".join(rail)


def nowrap_code(html):
    """Short inline code stays on one line."""
    def mark(m):
        return '<code class="nw">' if len(re.sub(r"<[^>]+>|&\w+;", "x", m.group(1))) <= 24 else "<code>"
    parts = re.split(r"(<pre\b.*?</pre>)", html, flags=re.S)
    return "".join(s if s.startswith("<pre") else re.sub(r"<code>(?=((?:(?!</code>).)*)</code>)", mark, s, flags=re.S) for s in parts)


def check_control_chars():
    """Fail on any control character other than newline in a source .md (a lost TeX backslash shows up as TAB/BEL)."""
    bad = []
    for p in sorted(SRC_BOOK.glob("*.md")):
        for n, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            for ch in sorted({c for c in line if ord(c) < 32 or ord(c) == 127}):
                bad.append(f"{p}:{n}: control character U+{ord(ch):04X}")
    if bad:
        sys.exit("source contains control characters (TeX backslash lost?):\n" + "\n".join(bad))


def main():
    check_control_chars()
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    (OUT / "figs").mkdir(parents=True, exist_ok=True)
    if not EN and IN_REPO:
        (REPO / "book").mkdir(exist_ok=True); (REPO / "figs").mkdir(exist_ok=True)
    built = {}
    for old in list((OUT / "figs").glob("*.html")) + ([] if EN or not IN_REPO else list((REPO / "figs").glob("*.html"))):
        old.unlink()
    def emit(h, zh=not EN):
        t = h.read_text()
        if zh:
            t = t.replace('<html lang="en">', '<html lang="zh-Hans">', 1)
        (OUT / "figs" / h.name).write_text(t.replace("<head>", "<head><script>" + PLAYER + "</script>", 1).replace("</body>", FIG_FIX + KATEX_CSS_FIG + POST_H + "</body>"))
    en_figs = set()
    for d in sorted(SRC_FIGS.iterdir()):
        h = d / f"{d.name}.html"
        if d.is_dir() and not d.name.startswith("_") and h.exists():
            built[d.name] = h
            he = SRC_FIGS_EN / d.name / f"{d.name}.html"
            if EN and he.exists():
                emit(he); en_figs.add(d.name)
            elif not EN:
                emit(h)
                if IN_REPO:
                    shutil.copy2(h, REPO / "figs" / h.name)
            elif PREVIEW:  # the en preview carries its own copy of the zh figure it falls back to
                emit(h, zh=True); en_figs.add(d.name)
    nums = {}
    def fig_rep(m):
        nm, num = m.group(1).strip(), m.group(2)
        if nm in built:
            nums[nm] = num
            src = f"figs/{nm}.html" if nm in en_figs or not EN else f"../figs/{nm}.html"
            h = FIG_H.get(f"{LANG}/{nm}")
            style = f' style="--h:{h + 4}px"' if h else ""
            # sandbox without allow-same-origin: the figure gets an opaque origin, so Chrome runs it in its own renderer process and its boot cannot block host scrolling.
            return f'\n\n<figure class="fig"><iframe data-src="{src}" title="{num}" sandbox="allow-scripts"{style}></iframe><a class="fig-open" href="{src}" target="_blank" rel="noopener">{FIG_OPEN}</a></figure>\n\n'
        missing.append(num)
        return "\n\n"
    heads, bodies, missing, chapters, items = [], [], [], [], []
    for c in ORDER:
        p = SRC_BOOK / f"{c}.md"
        if not p.exists():
            continue
        t = p.read_text()
        if not EN and IN_REPO:
            shutil.copy2(p, REPO / "book" / p.name)
        title = next((l.lstrip("# ").strip() for l in t.splitlines() if l.startswith("# ")), c)
        t = protect(t, c, items)
        title_html = next((l.lstrip("# ").strip() for l in t.splitlines() if l.startswith("# ")), c)
        t = re.sub(r"^# .*\n", "", t, count=1, flags=re.M)
        t = escape_table_code_pipes(re.sub(FIG_PAT, fig_rep, t, flags=re.S))
        t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
        body = MAP_PAT.sub(map_nav, fix_stray_bold(md.render(t))).replace('<table>', '<div class="tbl"><table>').replace('</table>', '</table></div>')
        body, sec_list = number_sections(c, body)
        label, level, question, topic = split_title(title_html)
        plain = " ".join(x for x in (split_title(title)[0], re.sub(r"[$`]", "", split_title(title)[3])) if x)
        chapters.append((c, title)); heads.append((c, label, md.renderInline(topic), plain, sec_list))
        kicker = f'<p class="ch-num">{label}' + (f'<span class="lv">{level}</span>' if level else "") + "</p>" if label else ""
        bodies.append(f'<header class="ch-head">{kicker}<h1>{keep_units(md.renderInline(question))}</h1></header>{body}')
    secs = []
    for i, (c, *_ ) in enumerate(heads):
        pn = "".join(f'<a class="{cls}" href="#{h[0]}"><span>{word}</span><b>{h[1] + (" " if EN else "　") if h[1] else ""}{h[2]}</b></a>'
                     for cls, word, h in (("prev", UI["prev"], heads[i - 1] if i else None), ("next", UI["next"], heads[i + 1] if i + 1 < len(heads) else None)) if h)
        secs.append(f'<section id="{c}">{bodies[i]}<nav class="pn" aria-label="{UI["pn_aria"]}">{pn}</nav></section>')
    toc, rail = toc_html(heads)
    errors = resolve(items)
    if errors:
        sys.exit("build failed:\n" + "\n".join(errors))
    vendor_katex()
    vendor_fonts()
    css, js, tree = MATH_CSS.replace("@UP@", UP) + sect_css(CSS) + (GOOGLE_CSS.replace("@UP@", UP) if BOOK_FONT == "google" else "") + charts.CSS + ".nw{white-space:nowrap}", JS, ""
    if BG_TREE:
        import bg_tree
        tcss, tree, js = bg_tree.build([sid for *_, sec_list in heads for sid, _, _ in sec_list], JS)
        css += tcss
    page = TMPL.format(lang=UI["html"], up=UP, tog=UI["tog"].format(o=OTHER), ui_toc=UI["toc"], ui_close=UI["close"], ui_rail=UI["rail"], rail_aria=UI["rail_aria"], sub=UI["sub"], note=UI["note"], book=BOOK, book_nb=keep_units(BOOK), css=css, js=js, short=BOOK_SHORT, toc=toc, rail=rail, secs="".join(secs))
    if tree:
        page = page.replace("<body>\n", "<body>\n" + tree, 1)
    page = re.sub("\ue002(.*?)\ue003", lambda m: wrap_sects(m.group(1)), substitute(page, items), flags=re.S)
    (OUT / "index.html").write_text(nowrap_code(page))
    if not EN and IN_REPO:
        write_readme(chapters, built, (OUT / "index.html").read_text(), nums)
    (DOCS / ".nojekyll").write_text("")
    print("figures not drawn yet (hidden):", ", ".join(missing))
    if new := check_math_font(items):
        sys.exit(f"math font subset lacks {new!r}: run tools/subset_math_font.py on the built pages, then build again")
    print(f"math expressions rendered: {sum(1 for it in items if it['kind'] == 'M')}, charts: {sum(1 for it in items if it['kind'] == 'C')}")
    print(f"section heights baked {sum(SECT_BAKED)}/{len(SECT_BAKED)} ({SECT_H_PATH.name}; run tools/sect_heights.mjs on a built site to refresh)")
    print(f"chapters {len(secs)}, figures embedded {sum(1 for _ in re.finditer('<iframe', (OUT/'index.html').read_text()))}")

if __name__ == "__main__":
    main()
