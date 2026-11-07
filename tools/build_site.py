#!/usr/bin/env python3
"""Build docs/index.html (the reader's merged version) from book/*.md and the built figures.
Run from the repo root:  uv run --no-project --with markdown-it-py --with pyyaml python tools/build_site.py
Math needs KaTeX once:  cd tools && npm ci
"""
import bisect, html, json, re, shutil, subprocess, sys
from pathlib import Path
from markdown_it import MarkdownIt

import charts

SRC_BOOK = Path("/Users/yufanfei/GolandProjects/open-kernel-challenge-triad/audit_out/w25/orch/gpu_tutor/book")
SRC_FIGS = SRC_BOOK / "figs"
REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
ORDER = ["preface", "ch00_0", "ch00", "ch00_5", "ch01", "ch02", "ch03", "ch04", "ch05", "ch06", "ch07", "ch08", "ch09", "ch10", "appA", "appB"]
FIG_PAT = r"<!--\s*FIG\s+([\w.-]+)\s*:\s*(图\s*(?:导[一二三]|[A-Z\d.]+)-\d+).*?-->"
POST_H = '<script>(function(){function s(){var h=Math.ceil(document.body.getBoundingClientRect().height);parent.postMessage({figH:h},"*");}window.addEventListener("load",s);new ResizeObserver(s).observe(document.body);})();</script>'
PLAYER = (SRC_FIGS / "_parts" / "player.js").read_text()
KATEX_CSS_FIG = '<link rel="stylesheet" href="../vendor/katex/katex.min.css">'
FIG_FIX = "<style>body{display:flow-root}.iso-page{margin:16px auto 12px!important}</style>"
CSS = """
body{margin:0;background:#f2f2ef;color:#2a2a2e;font:16px/1.85 -apple-system,"PingFang SC",system-ui,sans-serif}
main{max-width:760px;margin:40px auto 120px;padding:0 24px}
h1{font-size:26px;line-height:1.4;margin:36px 0 12px}
h2{font-size:20px;line-height:1.5;margin:34px 0 10px}
code{font:13.5px ui-monospace,Menlo,monospace;background:#e8e8e4;padding:1px 4px;border-radius:4px;overflow-wrap:anywhere}
td code,th code{overflow-wrap:normal}
h1 code,h2 code,h3 code{font-size:.85em;padding:0 3px}
pre{background:#fbfbfa;border:1px solid #ddd;padding:12px 14px;border-radius:8px;font-size:13px;line-height:1.55;white-space:pre-wrap;overflow-wrap:anywhere}
pre code{background:none;padding:0;font-size:inherit}
blockquote{margin:14px 0;padding:8px 16px;border-left:3px solid #8a8a8f;background:#fbfbfa}
.tbl{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:14px -40px}
table{border-collapse:collapse;font-size:13px;width:100%}
td,th{border:1px solid #ccc;padding:5px 8px;vertical-align:top;line-height:1.6}
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
.katex{font-size:1em}
.katex-display{margin:1em 0;padding:2px 0;overflow-x:auto;overflow-y:hidden}
.fig{margin:22px -40px;overflow-x:auto;-webkit-overflow-scrolling:touch}
.fig iframe{display:block;width:100%;height:900px;border:0}
@media(max-width:860px){.fig{margin:22px 0}.tbl{margin:14px 0}main{padding:0 14px}}
@media(max-width:600px){.fig iframe{min-width:640px}pre{font-size:11.5px}table{font-size:12.5px}td,th{min-width:8em}}
"""
TMPL = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GPU 是怎么工作的，以及怎么优化 GPU 性能</title><link rel="stylesheet" href="vendor/katex/katex.min.css"><style>{css}</style>
<script>addEventListener("message",e=>{{if(!e.data||!e.data.figH)return;document.querySelectorAll("iframe").forEach(f=>{{if(f.contentWindow===e.source)f.style.height=Math.ceil(e.data.figH)+4+"px";}});}});</script></head>
<body><main><h1>GPU 是怎么工作的，以及怎么优化 GPU 性能</h1><p>中文 GPU 教程草稿，正在逐轮审读。图都可以操作：点按钮、拖时间轴。</p>
<nav><ol class="toc">{toc}</ol></nav>{secs}</main></body></html>"""
MAP_PAT = re.compile(r"<p><strong>本书地图：</strong>\s*(.*?)</p>", re.S)

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
        res = subprocess.run(["node", str(REPO / "tools" / "katex_render.mjs")], input=json.dumps([{"tex": it["tex"], "display": it["display"]} for it in math]), capture_output=True, text=True, cwd=REPO)
        if res.returncode:
            sys.exit("node failed:\n" + res.stderr)
        for it, r in zip(math, json.loads(res.stdout)):
            if "error" in r:
                errors.append(f"{it['chapter']}:{it['line']}: math error: {html.unescape(r['error'])}  in  {it['tex'][:80]}")
            else:
                it["html"] = r["html"]
    for it in items:
        if it["kind"] == "C":
            try:
                it["html"] = charts.render(it["body"])
            except charts.ChartError as e:
                errors.append(f"{it['chapter']}:{it['line']}: chart error: {e}")
    return errors


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
            (DOCS / "figs" / h.name).write_text(t.replace("<head>", "<head><script>" + PLAYER + "</script>", 1).replace("</body>", FIG_FIX + KATEX_CSS_FIG + POST_H + "</body>"))
            shutil.copy2(h, REPO / "figs" / h.name)
    nums = {}
    def fig_rep(m):
        nm, num = m.group(1).strip(), m.group(2)
        if nm in built:
            nums[nm] = num
            return f'\n\n<figure class="fig"><iframe src="figs/{nm}.html" loading="lazy" title="{num}"></iframe></figure>\n\n'
        missing.append(num)
        return "\n\n"
    secs, toc, missing, chapters, items = [], [], [], [], []
    for c in ORDER:
        p = SRC_BOOK / f"{c}.md"
        if not p.exists():
            continue
        t = p.read_text(); shutil.copy2(p, REPO / "book" / p.name)
        title = next((l.lstrip("# ").strip() for l in t.splitlines() if l.startswith("# ")), c)
        t = protect(t, c, items)
        title_html = next((l.lstrip("# ").strip() for l in t.splitlines() if l.startswith("# ")), c)
        t = escape_table_code_pipes(re.sub(FIG_PAT, fig_rep, t, flags=re.S))
        t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
        chapters.append((c, title)); secs.append(f'<section id="{c}">{MAP_PAT.sub(map_nav, fix_stray_bold(md.render(t))).replace('<table>', '<div class="tbl"><table>').replace('</table>', '</table></div>')}</section>'); toc.append(f'<li><a href="#{c}">{md.renderInline(title_html)}</a></li>')
    errors = resolve(items)
    if errors:
        sys.exit("build failed:\n" + "\n".join(errors))
    vendor_katex()
    (DOCS / "index.html").write_text(substitute(TMPL.format(css=CSS + charts.CSS, toc="".join(toc), secs="".join(secs)), items))
    write_readme(chapters, built, (DOCS / "index.html").read_text(), nums)
    (DOCS / ".nojekyll").write_text("")
    print("figures not drawn yet (hidden):", ", ".join(missing))
    print(f"math expressions rendered: {sum(1 for it in items if it['kind'] == 'M')}, charts: {sum(1 for it in items if it['kind'] == 'C')}")
    print(f"chapters {len(secs)}, figures embedded {sum(1 for _ in re.finditer('<iframe', (DOCS/'index.html').read_text()))}")

if __name__ == "__main__":
    main()
