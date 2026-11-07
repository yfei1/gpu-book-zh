"""Build-time chart blocks: a fenced ```chart block with YAML becomes an inline SVG figure. No JS."""
import html
import yaml

W = 640
BLUE, GREY, GREEN, RED, INK, DASH = "#3b5bdb", "#b9bcc6", "#2b9a63", "#d6404d", "#2a2a2e", "#5b5b63"
FLOOR_COLOR = "#1f8f86"
LIGHT_BLUES = ["#9db0f2", "#7089e8", "#5470e0"]
STACK = ["#3b5bdb", "#1f9d8f", "#8e5bd6", "#e08a1e", "#d9558a", "#2b9a63", "#6b7280", "#a47148"]
MINUS = "\u2212"

CSS = """
.chart{margin:22px 0;padding:14px 16px 10px;background:#fbfbfa;border:1px solid #ddd;border-radius:8px}
.chart-title{font-weight:600;line-height:1.5}
.chart-sub{font-size:13px;color:#8c8c90;margin-left:8px;font-weight:400}
.chart-legend{display:flex;flex-wrap:wrap;gap:2px 14px;margin:4px 0 0;font-size:13px;color:#5b5b63}
.chart-legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
.chart-legend i.dash{width:16px;height:0;border-radius:0;border-top:1.5px dashed #5b5b63;vertical-align:3px}
.chart-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.chart svg{display:block;width:100%;min-width:520px;height:auto;font-variant-numeric:tabular-nums}
.chart-notes{margin:6px 0 0;padding-left:1.2em;font-size:13px;line-height:1.6;color:#5b5b63}
.chart-notes li{margin:1px 0}
.chart-note{margin:6px 0 0;font-size:13px;line-height:1.6;color:#5b5b63}
"""


class ChartError(Exception):
    pass


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(v, decimals=None):
    if decimals is not None:
        return f"{v:.{decimals}f}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def auto_decimals(values):
    return max((len(f"{v:.2f}".rstrip("0").split(".")[1]) if "." in f"{v:.2f}".rstrip("0") else 0) for v in values)


def signed(v, decimals=None):
    return ("+" if v > 0 else MINUS if v < 0 else "") + fmt(abs(v), decimals)


def est(text, size):
    return sum(size if ord(c) > 0x2E80 else size * 0.58 for c in str(text))


def wrap(text, size, width):
    lines, cur = [], ""
    for ch in str(text):
        if cur and est(cur + ch, size) > width:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    return lines + ([cur] if cur else [])


def text(x, y, s, size=13, anchor="middle", fill=INK, weight=None, halo=False):
    extra = f' font-weight="{weight}"' if weight else ""
    extra += ' stroke="#fbfbfa" stroke-width="3" paint-order="stroke"' if halo else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{fill}"{extra}>{esc(s)}</text>'


def lines_text(x, y, lines, size, lh, **kw):
    return "".join(text(x, y + i * lh, ln, size, **kw) for i, ln in enumerate(lines))


def number(d, key, where, required=True):
    v = d.get(key)
    if v is None:
        if required:
            raise ChartError(f"{where}: missing '{key}'")
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ChartError(f"{where}: '{key}' must be a number, got {v!r}")
    return float(v)


def delta(prev, cur, lower_better):
    """(ratio text, abs text, colour) for cur against prev."""
    if prev == cur:
        return None
    better = cur < prev if lower_better else cur > prev
    num, den = (prev, cur) if lower_better else (cur, prev)
    return (num / den if den else None), cur - prev, better


def delta_label(prev, cur, lower_better, unit, noise, decimals, with_unit):
    d = delta(prev, cur, lower_better)
    if d is None or noise:
        col = DASH
    else:
        col = GREEN if d[2] else RED
    if d is None:
        return ["×1.00"], col
    ratio, diff, _ = d
    r = "" if ratio is None else f"×{ratio:.2f}" if ratio < 10 else f"×{ratio:.1f}"
    a = signed(diff, decimals if decimals is not None else (1 if abs(diff) >= 10 else 2)) + (f" {unit}" if with_unit else "")
    return ([r] if r else []) + [a], col


def scale(values, extra):
    """Bar-height scale. One far-off bar (more than 3x the next) is cut with a break mark."""
    s = sorted(values, reverse=True)
    cap = s[0]
    clipped = len(s) > 1 and s[0] > 3 * s[1]
    if clipped:
        cap = s[1] * 1.25
    top = max([cap] + [e for e in extra if e is not None and e <= cap * 1.2])
    return (top or 1.0), clipped


def whisker(x, y_of, low, high, color=INK):
    if low is None or high is None:
        return ""
    return (f'<g stroke="{color}" stroke-width="1.2"><line x1="{x:.1f}" x2="{x:.1f}" y1="{y_of(low):.1f}" y2="{y_of(high):.1f}"/>'
            f'<line x1="{x-4:.1f}" x2="{x+4:.1f}" y1="{y_of(low):.1f}" y2="{y_of(low):.1f}"/>'
            f'<line x1="{x-4:.1f}" x2="{x+4:.1f}" y1="{y_of(high):.1f}" y2="{y_of(high):.1f}"/></g>')


def hline(x1, x2, y, color=DASH):
    return f'<line x1="{x1}" x2="{x2}" y1="{y:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="1.3" stroke-dasharray="5 4"/>' 


def line_spec(spec, key, where):
    d = spec.get(key)
    if d is None:
        return None
    if not isinstance(d, dict) or "label" not in d:
        raise ChartError(f"{where}: '{key}' needs label and value")
    return str(d["label"]), number(d, "value", f"{where}: {key}")


def steps_svg(spec, unit, lower, dec):
    data = spec.get("data")
    if not isinstance(data, list) or len(data) < 2:
        raise ChartError("steps: data must be a list of at least 2 {label, value}")
    rows = []
    for i, d in enumerate(data):
        if not isinstance(d, dict) or "label" not in d:
            raise ChartError(f"steps: data[{i}] needs label and value")
        w = f"steps: data[{i}]"
        rows.append(dict(label=str(d["label"]), v=number(d, "value", w), low=number(d, "low", w, False), high=number(d, "high", w, False),
                         noise=bool(d.get("noise")), note=d.get("note")))
    base, floor = line_spec(spec, "baseline", "steps"), line_spec(spec, "floor", "steps")
    vals = [r["v"] for r in rows]
    dec = spec.get("decimals", auto_decimals(vals + [x[1] for x in (base, floor) if x]))
    top, clipped = scale(vals, [x[1] for x in (base, floor) if x])
    n = len(rows)
    pitch = (W - 16) / n
    bw = min(34, pitch * 0.58)
    y_top, plot_h = 58, 150
    y_base = y_top + plot_h
    y_of = lambda v: y_base - min(v, top) / top * plot_h
    with_unit = pitch > est(f"{MINUS}000.0 {unit}", 10.5) + 2
    out = []
    for i, r in enumerate(rows):
        cx = 8 + pitch * (i + 0.5)
        h = min(r["v"], top) / top * plot_h
        out.append(f'<rect x="{cx-bw/2:.1f}" y="{y_base-h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" fill="{BLUE}"/>')
        if r["v"] > top:
            yb = y_base - h + 12
            out.append(f'<path d="M{cx-bw/2-2:.1f} {yb+3:.1f} l{bw+4:.1f} -6" stroke="#fbfbfa" stroke-width="3.5" fill="none"/>')
        out.append(whisker(cx, y_of, r["low"], r["high"]))
        ytxt = y_of(max(r["v"], r["high"] or 0)) - 5
        out.append(text(cx, ytxt, fmt(r["v"], dec), 12.5, weight=600, halo=True))
        for j, ln in enumerate(wrap(r["label"], 12.5, pitch - 3) or [""]):
            out.append(text(cx, y_base + 17 + j * 15, ln, 12.5))
        if i:
            lab, col = delta_label(rows[i - 1]["v"], r["v"], lower, unit, r["noise"], dec, with_unit)
            bx = 8 + pitch * i
            for j, ln in enumerate(lab):
                out.append(text(bx, 14 + j * 13, ln, 11.5 if j == 0 else 10.5, fill=col, weight=600 if j == 0 else None))
    lines = "".join(hline(8, W - 8, y_of(x[1]), col) for x, col in ((base, DASH), (floor, FLOOR_COLOR)) if x)
    axis = f'<line x1="8" x2="{W-8}" y1="{y_base}" y2="{y_base}" stroke="#c9c9ce"/>'
    max_lines = max(len(wrap(r["label"], 12.5, pitch - 3)) for r in rows)
    height = y_base + 8 + 15 * max_lines + 8
    notes = [(r["label"], r["note"]) for r in rows if r["note"]]
    legend = [(("dash", col), f"{x[0]} {fmt(x[1], dec)}") for x, col in ((base, DASH), (floor, FLOOR_COLOR)) if x]
    return height, axis + "".join(out) + lines, legend, notes


def grouped_svg(spec, unit, lower, dec):
    data = spec.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("groups"), list) or not isinstance(data.get("series"), list):
        raise ChartError("grouped: data needs 'groups' (list) and 'series' (list of {name, values})")
    groups = [str(g) for g in data["groups"]]
    series = []
    for i, s in enumerate(data["series"]):
        if not isinstance(s, dict) or "name" not in s or not isinstance(s.get("values"), list):
            raise ChartError(f"grouped: series[{i}] needs name and values")
        if len(s["values"]) != len(groups):
            raise ChartError(f"grouped: series[{i}] has {len(s['values'])} values for {len(groups)} groups")
        vals = []
        for j, v in enumerate(s["values"]):
            if v is None:
                vals.append((None, None, None))
            elif isinstance(v, dict):
                vals.append((number(v, "value", f"grouped: series[{i}].values[{j}]"), number(v, "low", "grouped", False), number(v, "high", "grouped", False)))
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.append((float(v), None, None))
            else:
                raise ChartError(f"grouped: series[{i}].values[{j}] must be a number, null or {{value, low, high}}")
        series.append((str(s["name"]), vals))
    if not series:
        raise ChartError("grouped: needs at least 1 series")
    show_delta = spec.get("delta", len(series) == 2)
    if not isinstance(show_delta, bool):
        raise ChartError("delta must be true or false")
    base = line_spec(spec, "baseline", "grouped")
    allv = [v[0] for _, vs in series for v in vs if v[0] is not None]
    if not allv:
        raise ChartError("grouped: every value is null")
    dec = spec.get("decimals", auto_decimals(allv + ([base[1]] if base else [])))
    vmax = max(allv + ([base[1]] if base else []) + [0.0])
    vmin = min(allv + [0.0])
    pos = sorted((v for v in allv if v > 0), reverse=True)
    cut = len(pos) > 1 and pos[0] > 3 * pos[1]
    if cut:
        vmax = pos[1] * 1.3
    rng = (vmax - vmin) or 1.0
    G, S = len(groups), len(series)
    pitch = (W - 16) / G
    bw = min(40, (pitch - 26) / S)
    fs = 12 if bw >= 30 else 10.5
    y_top, plot_h = (58 if show_delta else 26), 150
    pad = 16 if vmin < 0 else 0
    y_base = y_top + plot_h + pad
    y_of = lambda v: y_top + (vmax - min(v, vmax)) / rng * plot_h
    y0 = y_of(0)
    if S == 1:
        colors = [BLUE]
    elif S == 2:
        colors = [GREY, BLUE]
    elif S == 3:
        colors = [GREY, LIGHT_BLUES[1], BLUE]
    else:
        colors = [STACK[i % len(STACK)] for i in range(S)]
    with_unit = pitch > est(f"{MINUS}00.00 {unit}", 10.5) + 4
    out = []
    for g in range(G):
        gx = 8 + pitch * g
        left = gx + (pitch - S * bw - (S - 1) * 3) / 2
        for si, (_, vs) in enumerate(series):
            v, lo, hi = vs[g]
            if v is None:
                continue
            x = left + si * (bw + 3)
            ya, yb = sorted((y0, y_of(v)))
            out.append(f'<rect x="{x:.1f}" y="{ya:.1f}" width="{bw:.1f}" height="{max(yb-ya, 0.6):.1f}" rx="2" fill="{colors[si]}"/>')
            out.append(whisker(x + bw / 2, y_of, lo, hi))
            if v > vmax:
                out.append(f'<path d="M{x-2:.1f} {ya+16:.1f} l{bw+4:.1f} -6" stroke="#fbfbfa" stroke-width="3.5" fill="none"/>')
            above = v >= 0
            ytxt = (y_of(max(v, hi or v)) - 5) if above else (y_of(min(v, lo if lo is not None else v)) + fs + 3)
            out.append(text(x + bw / 2, ytxt, fmt(v, dec), fs, weight=600 if si == S - 1 else None, halo=True))
        for j, ln in enumerate(wrap(groups[g], 12.5, pitch - 6) or [""]):
            out.append(text(gx + pitch / 2, y_base + 17 + j * 15, ln, 12.5))
        first, last = series[0][1][g][0], series[-1][1][g][0]
        if show_delta and S > 1 and first is not None and last is not None:
            lab, col = delta_label(first, last, lower, unit, False, dec, with_unit)
            for j, ln in enumerate(lab):
                out.append(text(gx + pitch / 2, 14 + j * 13, ln, 11.5 if j == 0 else 10.5, fill=col, weight=600 if j == 0 else None))
    lines = hline(8, W - 8, y_of(base[1])) if base else ""
    axis = f'<line x1="8" x2="{W-8}" y1="{y0:.1f}" y2="{y0:.1f}" stroke="#c9c9ce"/>'
    max_lines = max(len(wrap(g, 12.5, pitch - 6)) for g in groups)
    legend = ([(colors[i], name) for i, (name, _) in enumerate(series)] if S > 1 else []) + ([(("dash", DASH), f"{base[0]} {fmt(base[1], dec)}")] if base else [])
    return y_base + 8 + 15 * max_lines + 8, axis + "".join(out) + lines, legend, []


def stacked_svg(spec, unit, lower, dec):
    data = spec.get("data")
    if not isinstance(data, list) or not data:
        raise ChartError("stacked: data must be a list of {label, value}")
    segs = []
    for i, d in enumerate(data):
        if not isinstance(d, dict) or "label" not in d:
            raise ChartError(f"stacked: data[{i}] needs label and value")
        v = number(d, "value", f"stacked: data[{i}]")
        if v < 0:
            raise ChartError(f"stacked: data[{i}] value must not be negative")
        segs.append((str(d["label"]), v))
    total = sum(v for _, v in segs)
    base, floor = line_spec(spec, "baseline", "stacked"), line_spec(spec, "floor", "stacked")
    dec = spec.get("decimals", auto_decimals([v for _, v in segs] + [x[1] for x in (base, floor) if x]))
    span = max([total] + [x[1] for x in (base, floor) if x]) or 1.0
    x0, x1 = 8, W - 8
    px = lambda v: x0 + v / span * (x1 - x0)
    y_bar, bar_h = 44, 40
    out, x, rows_end = [], 0.0, []
    row_y0 = y_bar + bar_h + 26
    row_h = 16
    for i, (label, v) in enumerate(segs):
        xa, xb = px(x), px(x + v)
        col = STACK[i % len(STACK)]
        out.append(f'<rect x="{xa:.1f}" y="{y_bar}" width="{max(xb-xa,0.8):.1f}" height="{bar_h}" fill="{col}" stroke="#fbfbfa" stroke-width="1"/>')
        mid = (xa + xb) / 2
        lab = f"{label} {fmt(v, dec)}"
        w_ = est(lab, 12) + 6
        left = max(x0, min(mid - w_ / 2, x1 - w_))
        row = 0
        while row < len(rows_end) and rows_end[row] + 4 > left:
            row += 1
        if row == len(rows_end):
            rows_end.append(0)
        rows_end[row] = left + w_
        yy = row_y0 + row * row_h
        out.append(f'<line x1="{mid:.1f}" x2="{mid:.1f}" y1="{y_bar+bar_h}" y2="{yy-12:.1f}" stroke="{col}" stroke-width="1"/>')
        out.append(f'<rect x="{left:.1f}" y="{yy-11:.1f}" width="9" height="9" rx="2" fill="{col}"/>')
        out.append(text(left + 13, yy - 2, lab, 12, "start"))
        x += v
    out.append(text(px(total), y_bar - 6, f"合计 {fmt(total, dec)} {unit}", 12.5, "end" if px(total) > W / 2 else "start", weight=600))
    marks = ""
    for spec_line, col in ((floor, FLOOR_COLOR), (base, DASH)):
        if spec_line:
            xx = px(spec_line[1])
            marks += f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="{y_bar-12}" y2="{y_bar+bar_h+6}" stroke="{col}" stroke-width="1.8" stroke-dasharray="4 3"/>' 
    height = row_y0 + len(rows_end) * row_h + 4
    legend = [(("dash", col), f"{x[0]} {fmt(x[1], dec)}") for x, col in ((base, DASH), (floor, FLOOR_COLOR)) if x]
    return height, "".join(out) + marks, legend, []


BUILDERS = {"steps": steps_svg, "grouped": grouped_svg, "stacked": stacked_svg}


def render(body):
    try:
        spec = yaml.safe_load(body)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        raise ChartError(f"bad YAML{f' at block line {mark.line + 1}' if mark else ''}: {getattr(e, 'problem', e)}")
    if not isinstance(spec, dict):
        raise ChartError("a chart block must be a YAML mapping")
    kind = spec.get("type")
    if kind not in BUILDERS:
        raise ChartError(f"type must be one of steps | grouped | stacked, got {kind!r}")
    for key in ("title", "unit", "data"):
        if key not in spec:
            raise ChartError(f"missing '{key}'")
    unknown = set(spec) - {"type", "title", "unit", "lower_is_better", "baseline", "floor", "note", "data", "decimals", "delta"}
    if unknown:
        raise ChartError(f"unknown field(s): {', '.join(sorted(unknown))}")
    unit, lower = str(spec["unit"]), spec.get("lower_is_better", True)
    if not isinstance(lower, bool):
        raise ChartError("lower_is_better must be true or false")
    try:
        height, svg_body, legend, notes = BUILDERS[kind](spec, unit, lower, None)
    except (ArithmeticError, KeyError, TypeError, ValueError, IndexError) as e:
        raise ChartError(f"{kind}: {type(e).__name__}: {e}")
    direction = "越低越好" if lower else "越高越好"
    head = f'<div class="chart-title">{esc(spec["title"])}<span class="chart-sub">{esc(unit)}，{direction}</span></div>'
    leg = ""
    if legend:
        sw = lambda c: f'<i class="dash" style="border-top-color:{c[1]}"></i>' if isinstance(c, tuple) else f'<i style="background:{c}"></i>'
        leg = '<div class="chart-legend">' + "".join(f"<span>{sw(c)}{esc(n)}</span>" for c, n in legend) + "</div>"
    note_list = ""
    if notes:
        note_list = '<ul class="chart-notes">' + "".join(f"<li><b>{esc(a)}</b>：{esc(b)}</li>" for a, b in notes) + "</ul>"
    cap = f'<div class="chart-note">{esc(spec["note"])}</div>' if spec.get("note") else ""
    svg = (f'<svg viewBox="0 0 {W} {height:.0f}" role="img" aria-label="{esc(spec["title"])}" '
           f'font-family="inherit">{svg_body}</svg>')
    return f'<figure class="chart">{head}{leg}<div class="chart-scroll">{svg}</div>{note_list}{cap}</figure>'
