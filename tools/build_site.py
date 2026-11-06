#!/usr/bin/env python3
"""Build docs/index.html (the reader's merged version) from book/*.md and the built figures.
Run from the repo root:  uv run --with markdown-it-py python tools/build_site.py
"""
import html, re, shutil
from pathlib import Path
from markdown_it import MarkdownIt

SRC_BOOK = Path("/Users/yufanfei/GolandProjects/open-kernel-challenge-triad/audit_out/w25/orch/gpu_tutor/book")
SRC_FIGS = SRC_BOOK / "figs"
REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
ORDER = ["preface", "ch00", "ch00_5", "ch01", "ch02", "ch03", "ch04", "ch05", "ch06", "ch07", "ch08", "ch09", "appA", "appB"]
FIG_PAT = r"<!--\s*FIG\s+([\w.-]+)\s*:\s*(图\s*[\d.]+-\d+).*?-->"
POST_H = '<script>(function(){function s(){var h=Math.max(document.body.scrollHeight,document.documentElement.scrollHeight);parent.postMessage({figH:h},"*");}window.addEventListener("load",s);new ResizeObserver(s).observe(document.body);})();</script>'
CSS = """
body{margin:0;background:#f2f2ef;color:#2a2a2e;font:16px/1.85 -apple-system,"PingFang SC",system-ui,sans-serif}
main{max-width:760px;margin:40px auto 120px;padding:0 24px}
h1{font-size:26px;line-height:1.4;margin:36px 0 12px}
h2{font-size:20px;line-height:1.5;margin:34px 0 10px}
code{font:13.5px ui-monospace,Menlo,monospace;background:#e8e8e4;padding:1px 4px;border-radius:4px}
h1 code,h2 code,h3 code{font-size:.85em;padding:0 3px}
pre{background:#fbfbfa;border:1px solid #ddd;padding:12px 14px;border-radius:8px;font-size:13px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}
pre code{background:none;padding:0;font-size:inherit}
blockquote{margin:14px 0;padding:8px 16px;border-left:3px solid #8a8a8f;background:#fbfbfa}
table{display:block;overflow-x:auto;border-collapse:collapse;font-size:14px;margin:14px 0}
td,th{border:1px solid #ccc;padding:5px 8px}
hr{border:none;border-top:1px solid #ddd;margin:30px 0}
ul,ol{padding-left:1.5em}
li{margin:4px 0}
li>p{margin:4px 0}
section{border-top:1px solid #ddd;margin-top:48px;padding-top:8px}
.toc{background:#fbfbfa;border:1px solid #ddd;border-radius:8px;padding:10px 18px 10px 34px;font-size:15px}
.map{display:flex;flex-wrap:wrap;gap:2px 0;margin:6px 0 14px;padding:0;list-style:none;font-size:12.5px;line-height:1.6;color:#8c8c90}
.map li{margin:0}
.map li+li::before{content:"\\203A";margin:0 7px;color:#b4b4b8}
.map .here{color:#2a2a2e;font-weight:600}
.fig{margin:22px -40px;overflow-x:auto;-webkit-overflow-scrolling:touch}
.fig iframe{display:block;width:100%;height:900px;border:0}
@media(max-width:860px){.fig{margin:22px 0}main{padding:0 14px}}
@media(max-width:600px){.fig iframe{min-width:640px}pre{font-size:11.5px}}
"""
TMPL = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPU 是怎么工作的，以及怎么优化 GPU 性能</title><style>{css}</style>
<script>addEventListener("message",e=>{{if(!e.data||!e.data.figH)return;document.querySelectorAll("iframe").forEach(f=>{{if(f.contentWindow===e.source)f.style.height=Math.ceil(e.data.figH)+4+"px";}});}});</script></head>
<body><main><h1>GPU 是怎么工作的，以及怎么优化 GPU 性能</h1><p>中文 GPU 教程草稿，正在逐轮审读。图都可以操作：点按钮、拖时间轴。</p>
<nav><ol class="toc">{toc}</ol></nav>{secs}</main></body></html>"""
MAP_PAT = re.compile(r"<p><strong>本书地图：</strong>\s*(.*?)</p>", re.S)

def map_nav(m):
    items = [x.strip() for x in m.group(1).split("→")]
    li = []
    for x in items:
        cur = re.fullmatch(r"<strong>【(.*?)】</strong>", x)
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

def write_readme(chapters, built):
    figs = []
    for nm, p in built.items():
        m = re.search(r"<title>(.*?)</title>", p.read_text())
        if m:
            figs.append((html.unescape(m.group(1)), nm))
    figs.sort(key=lambda x: (float(re.search(r"图 ([\d.]+)-(\d+)", x[0]).group(1)), int(re.search(r"图 [\d.]+-(\d+)", x[0]).group(1))))
    (REPO / "README.md").write_text(README.format(
        chapters="\n".join(f"- [{t}](book/{c}.md)" for c, t in chapters),
        figures="\n".join(f"- [{html.escape(t, quote=False)}](figs/{nm}.html)" for t, nm in figs)))

def main():
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    (DOCS / "figs").mkdir(parents=True, exist_ok=True); (REPO / "book").mkdir(exist_ok=True); (REPO / "figs").mkdir(exist_ok=True)
    built = {}
    for old in list((DOCS / "figs").glob("*.html")) + list((REPO / "figs").glob("*.html")):
        old.unlink()
    for d in sorted(SRC_FIGS.iterdir()):
        h = d / f"{d.name}.html"
        if d.is_dir() and not d.name.startswith("_") and h.exists():
            built[d.name] = h
            t = h.read_text()
            (DOCS / "figs" / h.name).write_text(t if "figH" in t else t.replace("</body>", POST_H + "</body>"))
            shutil.copy2(h, REPO / "figs" / h.name)
    def fig_rep(m):
        nm, num = m.group(1).strip(), m.group(2)
        if nm in built:
            return f'\n\n<figure class="fig"><iframe src="figs/{nm}.html" loading="lazy" title="{num}"></iframe></figure>\n\n'
        missing.append(num)
        return "\n\n"
    secs, toc, missing, chapters = [], [], [], []
    for c in ORDER:
        p = SRC_BOOK / f"{c}.md"
        if not p.exists():
            continue
        t = p.read_text(); shutil.copy2(p, REPO / "book" / p.name)
        title = next((l.lstrip("# ").strip() for l in t.splitlines() if l.startswith("# ")), c)
        t = re.sub(FIG_PAT, fig_rep, t, flags=re.S)
        t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
        chapters.append((c, title)); secs.append(f'<section id="{c}">{MAP_PAT.sub(map_nav, md.render(t))}</section>'); toc.append(f'<li><a href="#{c}">{title}</a></li>')
    (DOCS / "index.html").write_text(TMPL.format(css=CSS, toc="".join(toc), secs="".join(secs)))
    write_readme(chapters, built)
    (DOCS / ".nojekyll").write_text("")
    print("figures not drawn yet (hidden):", ", ".join(missing))
    print(f"chapters {len(secs)}, figures embedded {sum(1 for _ in re.finditer('<iframe', (DOCS/'index.html').read_text()))}")

if __name__ == "__main__":
    main()
