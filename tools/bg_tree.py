#!/usr/bin/env python3
"""Background hardware skill tree for the book page. build_site.py uses it only when BG_TREE=1.

The tree is HW_TREE.json drawn as a real tree:
- the trunk is the die -> GPC -> TPC -> SM chain; the other children of the die and the GPC leave the trunk as side boughs;
- every other node with two or more children is a binary fork (extra forks carry no node), children stay in id order;
- the width of a branch is the square root of the number of nodes it carries, so branches taper like wood;
- leaf nodes sit in the crown, on three staggered rings.
A node is lit when the reader has passed the section that first teaches it (HW_TREE first_chapter / first_section).
A branch is lit when one of the nodes it carries is lit, so a lit branch can pass through a node that the book has not
taught yet; that node stays a hollow socket.
Lit parts glow: a warm halo (a gaussian blur of opaque amber discs and branch lines, so it never exceeds the amber
token) and a light inner line along each lit branch.
Rendering: one image for the locked tree and one image per unlock step (everything that lights at one section). The
browser rasterizes each image once; lighting a step only changes that image's opacity, on its own compositor layer.
The reader's position comes from an IntersectionObserver on the h2 headings, so nothing reads layout on scroll.
On a one-section step forward, a flare image of the step's halo brightens once and fades (Web Animations, opacity).
"""
import json, math, os
from pathlib import Path

DATA = Path(os.environ.get("BG_TREE_DATA") or Path(__file__).resolve().parents[2] / "chapter_cold" / "HW_TREE.json")
W, H = 1600, 1000
P = dict(
    ground=992, base=588,          # trunk foot and crown base (top of the trunk), in viewBox units
    ax=830, ay=566, theta=86,      # crown ellipse half-axes around the crown base, and the widest leaf angle from vertical
    gap=0.9,                       # extra angle units between two leaves for each fork level that separates them
    ring=(0.0, 0.42, 0.22),        # leaf stagger, as a fraction of the leaf's own twig, cycled in leaf order
    beta=0.85, bough_t0=0.35, bough_r=1.6,   # depth spacing exponent; a side bough starts at bough_t0 of its reach
    trunk_at=(0, 0.42, 0.55, 0.66, 0.74, 0.82, 0.91, 1.0),   # trunk points from foot (0) to crown base (1)
    wk=1.0, we=0.58, tip=0.55, flare=1.8,   # flare: the trunk foot is this much wider     # branch width = wk * nodes ** we; a leaf twig ends at tip * wk
    k1=0.24, k2=0.30, chord=0.8,   # curve handles; a child heading is chord * chord direction + the rest radial
    sock=(6.4, 8.0, 10.5),         # socket size for a leaf, an inner node and a trunk node
    halo=(7.5, 9.5, 12.0), blur=5.5,   # glow disc radius (leaf, inner, trunk) and its blur, viewBox units
    aura_w=(4.0, 3.0), core=(0.32, 0.5, 2.4),   # branch glow width = min(w, a) + b; inner line = clamp(k * w, lo, hi)
)


class Shoot:
    """One branch segment and the point where it ends. node is the HW_TREE id, or None for an extra fork."""
    def __init__(s, node=None, kids=()):
        s.node, s.kids, s.parent, s.trunk = node, list(kids), None, False


def _split(items, weight):
    """Split an ordered list into two contiguous non-empty parts with the closest total weight."""
    tot, acc, best = sum(weight(x) for x in items), 0, None
    for i in range(1, len(items)):
        acc += weight(items[i - 1])
        d = abs(tot - 2 * acc)
        if best is None or d < best[0]:
            best = (d, i)
    return items[:best[1]], items[best[1]:]


def _grow(rows):
    kids = {r["id"]: [] for r in rows}
    for r in rows:
        if r["parent_id"] is not None:
            kids[r["parent_id"]].append(r["id"])
    for v in kids.values():
        v.sort()
    sub = {}
    def size(u):
        sub[u] = 1 + sum(size(v) for v in kids[u])
        return sub[u]
    root = next(r["id"] for r in rows if r["parent_id"] is None)
    size(root)

    def group(g):
        return node(g[0]) if len(g) == 1 else Shoot(None, pair(g))

    def pair(g):
        a, b = _split(g, lambda c: sub[c])
        return [group(a), group(b)]

    def node(u, trunk=False):
        c = kids[u]
        sh = Shoot(u)
        sh.trunk = trunk
        if not c:
            return sh
        big = max(c, key=lambda v: (sub[v], -v))
        if len(c) >= 2 and 2 * sub[big] > sub[u] - 1:
            # The heaviest child continues the axis; the others leave it as one bough on each side.
            left, right = _split([v for v in c if v != big], lambda v: sub[v])
            lw, rw = sum(sub[v] for v in left), sum(sub[v] for v in right)
            lead = node(big, trunk)
            if rw > lw:   # the heavier bough leaves the axis lower
                upper = Shoot(None, [group(left), lead]); lower = Shoot(None, [upper, group(right)])
            else:
                upper = Shoot(None, [lead, group(right)]); lower = Shoot(None, [group(left), upper])
            upper.trunk = lower.trunk = trunk
            sh.kids = [lower]
        else:
            sh.kids = [node(c[0], trunk)] if len(c) == 1 else pair(c)
        return sh

    tree = node(root, True)
    return tree, kids, sub


def _walk(s):
    yield s
    for k in s.kids:
        k.parent = s
        yield from _walk(k)


def layout(rows):
    tree, kids, sub = _grow(rows)
    shoots = list(_walk(tree))
    for s in reversed(shoots):                       # bottom-up: nodes carried, height
        s.w = (1 if s.node is not None else 0) + sum(k.w for k in s.kids)
        s.h = 0 if not s.kids else 1 + max(k.h for k in s.kids)
    trunk = [s for s in shoots if s.trunk]   # pre-order keeps the chain order
    crown = trunk[-1]
    # Leaf angles in left-to-right order, with a gap for each fork level between neighbours.
    leaves = [s for s in shoots if not s.kids]
    def chain(s):
        out = []
        while s is not None:
            out.append(s); s = s.parent
        return out
    pos, a = [], 0.0
    for i, s in enumerate(leaves):
        if i:
            up = {id(x): n for n, x in enumerate(chain(leaves[i - 1]))}
            n = next(m for m, x in enumerate(chain(s)) if id(x) in up)
            a += 1 + P["gap"] * (n - 1)
        pos.append(a)
    span = math.radians(P["theta"])
    for s, v in zip(leaves, pos):
        s.th = -span + 2 * span * v / pos[-1]
    for s in reversed(shoots):
        if s.kids:
            s.th = sum(k.th for k in s.kids) / len(s.kids)
    # Radial position, per region (the crown above the trunk top, and each side bough): forks are spread by depth
    # along the region, t = t0 + (1 - t0) * (depth / max depth) ** beta, so every branch forks along its length.
    for r in [crown] + [k for s in trunk[:-1] for k in s.kids if not k.trunk]:
        # A side bough reaches out in proportion to its size, so small boughs stay short.
        t1 = 1.0 if r is crown else min(1.0, P["bough_r"] * (r.w / crown.w) ** 0.35)
        t0 = 0.0 if r is crown else P["bough_t0"] * t1
        region, todo = [], [(r, 0)]
        while todo:
            s, dep = todo.pop()
            region.append((s, dep))
            todo += [(k, dep + 1) for k in s.kids]
        top = max(dep for _, dep in region) or 1
        for s, dep in region:
            s.t = t0 + (t1 - t0) * (dep / top) ** P["beta"]
    for i, s in enumerate(leaves):   # stagger: pull some leaves back along their own twig
        s.t -= P["ring"][i % len(P["ring"])] * (s.t - s.parent.t)
    cx, cy = W / 2, P["base"]
    for s in shoots:
        if not s.trunk:
            s.x, s.y = cx + s.t * P["ax"] * math.sin(s.th), cy - s.t * P["ay"] * math.cos(s.th)
    for s, f in zip(trunk, P["trunk_at"]):
        s.x, s.y = cx, P["ground"] + (P["base"] - P["ground"]) * f
    # Headings: up on the trunk; elsewhere half the chord and half the direction away from the crown base.
    for s in shoots:
        if s.trunk:
            s.d = (0.0, -1.0)
            continue
        px, py = s.parent.x, s.parent.y
        ch = _unit(s.x - px, s.y - py)
        ra = _unit((s.x - cx) / P["ax"], (s.y - cy) / P["ay"]) if s.t > 0.02 else ch
        s.d = _unit(P["chord"] * ch[0] + (1 - P["chord"]) * ra[0], P["chord"] * ch[1] + (1 - P["chord"]) * ra[1])
    return shoots, trunk, kids, sub


def _unit(x, y):
    n = math.hypot(x, y) or 1.0
    return x / n, y / n


def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v) >= 0.05 else "0"


def _branch(s):
    """Tapered branch from the parent point to s, as one closed outline, plus a joint disc at s."""
    p = s.parent
    x0, y0, x3, y3 = p.x, p.y, s.x, s.y
    L = math.hypot(x3 - x0, y3 - y0)
    d0 = p.d
    x1, y1 = x0 + P["k1"] * L * d0[0], y0 + P["k1"] * L * d0[1]
    x2, y2 = x3 - P["k2"] * L * s.d[0], y3 - P["k2"] * L * s.d[1]
    w0 = P["wk"] * s.w ** P["we"] * (P["flare"] if p.parent is None else 1.0)
    inner = s.w - (1 if s.node is not None else 0)
    w1 = P["wk"] * inner ** P["we"] if inner else P["tip"] * P["wk"]
    n0 = _unit(-(y1 - y0), x1 - x0) if (x1, y1) != (x0, y0) else _unit(-(y3 - y0), x3 - x0)
    n1 = _unit(-(y3 - y2), x3 - x2)
    h0, h1 = w0 / 2, w1 / 2
    hm = (h0 + h1) / 2
    pts_l = [(x0 + n0[0] * h0, y0 + n0[1] * h0), (x1 + n0[0] * hm, y1 + n0[1] * hm), (x2 + n1[0] * hm, y2 + n1[1] * hm), (x3 + n1[0] * h1, y3 + n1[1] * h1)]
    pts_r = [(x3 - n1[0] * h1, y3 - n1[1] * h1), (x2 - n1[0] * hm, y2 - n1[1] * hm), (x1 - n0[0] * hm, y1 - n0[1] * hm), (x0 - n0[0] * h0, y0 - n0[1] * h0)]
    q = lambda pt: f"{_f(pt[0])} {_f(pt[1])}"
    d = f"M{q(pts_l[0])}C{q(pts_l[1])} {q(pts_l[2])} {q(pts_l[3])}L{q(pts_r[0])}C{q(pts_r[1])} {q(pts_r[2])} {q(pts_r[3])}Z"
    if s.kids and h1 > 0.6:
        d += f"M{_f(x3 - h1)} {_f(y3)}a{_f(h1)} {_f(h1)} 0 1 0 {_f(2 * h1)} 0a{_f(h1)} {_f(h1)} 0 1 0 {_f(-2 * h1)} 0Z"
    mid = f"M{_f(x0)} {_f(y0)}C{_f(x1)} {_f(y1)} {_f(x2)} {_f(y2)} {_f(x3)} {_f(y3)}"
    return d, mid, w0


def _socket(s, kind, size):
    x, y, r = s.x, s.y, size / 2
    if kind == "PHYSICAL":
        return f'<rect x="{_f(x - r)}" y="{_f(y - r)}" width="{_f(size)}" height="{_f(size)}" rx="{_f(size / 6)}"'
    if kind == "OPERATION":
        r *= 1.25
        return f'<path d="M{_f(x)} {_f(y - r)}L{_f(x + r)} {_f(y)}L{_f(x)} {_f(y + r)}L{_f(x - r)} {_f(y)}Z"'
    return f'<circle cx="{_f(x)}" cy="{_f(y)}" r="{_f(r * 1.05)}"'


def unlock_positions(rows, order):
    """s_node: 1-based page ordinal of the h2 that first teaches each node. order is the list of h2 ids on the page."""
    idx = {sid: i + 1 for i, sid in enumerate(order)}
    out = {}
    for r in rows:
        sid = f'{r["first_chapter"]}-{int(r["first_section"].lstrip("§"))}'
        if sid not in idx:
            raise SystemExit(f"bg_tree: node {r['id']} first section {sid} is not an h2 on the page")
        out[r["id"]] = idx[sid]
    return out


# Paint tokens, written as @name@ in the image sources and filled in by the page script (so ?lit= and ?unlit= work).
# The per-channel minimum of all paint is rgb(237,218,164) (rim R, G; aura B): #5E5D59 keeps 4.76:1 over it, so no blend
# of these colours with each other or the paper (any opacity, any overlap) drops muted text below 4.5:1, at any ?glow=.
TOK = dict(paper="#FAF9F5", unlit="#F6F5F1", lit="#F4E8C8", rim="#EDDAA9", core="#FFFDF5", aura="#F2DCA4", glow="0.6")
DUR = 3  # seconds: one-time brighten and opacity fade


def _bbox(pts, pad):
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    return [min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad]


def _union(a, b):
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])] if a else b


def _img(box, body, blur=True):
    x, y, w, h = box[0], box[1], box[2] - box[0], box[3] - box[1]
    vb = f"{_f(x)} {_f(y)} {_f(w)} {_f(h)}"
    filt = (f"<defs><filter id='b' filterUnits='userSpaceOnUse' x='{_f(x)}' y='{_f(y)}' width='{_f(w)}' height='{_f(h)}' "
            f"color-interpolation-filters='sRGB'><feGaussianBlur stdDeviation='{P['blur']}'/></filter></defs>") if blur else ""
    return f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='{vb}' preserveAspectRatio='none'>{filt}{body}</svg>"


def layers(rows, order):
    """The locked-tree image and one image per unlock step, as SVG sources with @token@ colours."""
    s_node = unlock_positions(rows, order)
    kind = {r["id"]: r["kind"] for r in rows}
    shoots, _, _, _ = layout(rows)
    for s in reversed(shoots):
        s.s = min(([s_node[s.node]] if s.node is not None else []) + [k.s for k in s.kids])
    pad = 3 * P["blur"] + P["halo"][2]
    seg, sock, halo, box = {}, {}, {}, {}
    for s in reversed(shoots):            # children first, as before: a parent's joint disc covers its children's bases
        if s.parent is None:
            continue
        d, mid, w0 = _branch(s)
        cw = min(max(P["core"][0] * w0, P["core"][1]), P["core"][2])
        aw = min(w0, P["aura_w"][0]) + P["aura_w"][1]
        seg.setdefault(s.s, []).append((s, d, mid, cw, aw))
        b = _bbox([(s.parent.x, s.parent.y), (s.x, s.y)], pad + w0 * P["flare"])
        box[s.s] = _union(box.get(s.s), b)
    for s in shoots:
        if s.node is None:
            continue
        i = 2 if s.trunk else 1 if s.kids else 0
        sock[s.node] = (s, _socket(s, kind[s.node], P["sock"][i]))
        halo.setdefault(s_node[s.node], []).append(f"<circle cx='{_f(s.x)}' cy='{_f(s.y)}' r='{_f(P['halo'][i])}'/>")
        box[s_node[s.node]] = _union(box.get(s_node[s.node]), _bbox([(s.x, s.y)], pad))
    def sk(node, k):   # a socket as it looks once the reader is at step k
        lit = s_node[node] <= k
        return sock[node][1].replace('"', "'") + (" fill='@core@' stroke='@rim@'/>" if lit else " fill='@paper@' stroke='@unlit@'/>")
    def glow(k):
        circ = "".join(halo.get(k, []))
        lines = "".join(f"<path stroke-width='{_f(aw)}' d='{mid}'/>" for _, _, mid, _, aw in seg.get(k, []))
        return f"<g fill='@aura@'>{circ}</g><g fill='none' stroke='@aura@' stroke-linecap='round'>{lines}</g>"
    steps = []
    for k in sorted(box):
        wood = "".join(f"<path d='{d}'/>" for _, d, _, _, _ in seg.get(k, []))
        core = "".join(f"<path stroke-width='{_f(cw)}' d='{mid}'/>" for _, _, mid, cw, _ in seg.get(k, []))
        # Sockets on this step's branches are redrawn in their state at k, so this step's wood does not hide them;
        # a later step that lights one of them sits above and redraws it lit.
        nodes = sorted({n for n, (s, _) in sock.items() if s_node[n] == k}
                       | {x.node for s, *_ in seg.get(k, []) for x in (s, s.parent) if x.node is not None})
        b = [round(v, 1) for v in (max(box[k][0], 0), max(box[k][1], 0), min(box[k][2], W), min(box[k][3], H))]
        body = (f"<g filter='url(#b)' opacity='@glow@'>{glow(k)}</g><g fill='@lit@'>{wood}</g>"
                f"<g fill='none' stroke='@core@' stroke-linecap='round'>{core}</g><g stroke-width='1.3'>{''.join(sk(n, k) for n in nodes)}</g>")
        steps.append(dict(s=k, n=sum(1 for n in s_node if s_node[n] == k), b=[b[0], b[1], round(b[2] - b[0], 1), round(b[3] - b[1], 1)],
                          src=_img(b, body), fsrc=_img(b, f"<g filter='url(#b)'>{glow(k)}</g>")))
    base_wood = "".join(f"<path d='{d}'/>" for k in sorted(seg) for _, d, _, _, _ in seg[k])
    base = _img([0, 0, W, H], f"<g fill='@unlit@'>{base_wood}</g><g stroke-width='1.3'>{''.join(sk(n, 0) for n in sorted(sock))}</g>", blur=False)
    return dict(tok=TOK, dur=DUR, base=base, steps=steps)


CSS = """
:root{--bgt-dur:3s}
html{background:var(--ivory)}body{background:transparent}
.bgt{display:none;position:fixed;left:0;right:0;z-index:-1;pointer-events:none;user-select:none;overflow:hidden}
.bgt-box{position:absolute;bottom:0;left:0;right:0;margin:0 auto;aspect-ratio:16/10}
.bgt img{position:absolute;display:block;max-width:none}
.bgt .st,.bgt .fl{opacity:0;will-change:opacity}.bgt .st.on{opacity:1}
.bgt.fade .st{transition:opacity var(--bgt-dur) linear}
@media(min-width:1024px){.bgt{display:block;top:52px;height:calc(100vh - 52px)}.bgt-box{width:min(100%,calc((100vh - 52px) * 1.6))}}
@media(min-width:1280px){.bgt{top:0;height:100vh}.bgt-box{width:min(100%,160vh)}.toc,.rail{background:transparent}}
@media(prefers-reduced-motion:reduce){.bgt .st{transition:none!important}}
@media print{.bgt{display:none!important}}
"""

# The position is the number of h2 headings above the reading line (30 % of the viewport height), the same rule as
# spy(): an IntersectionObserver whose root reaches from far above the page (1e7 px, more than the page height) down to
# that line. A one-section step fades once the page has loaded; the first state, link jumps, back/forward and
# multi-section steps snap. The page cannot see a wheel over a figure iframe, so it arms on the load event instead.
JS = r"""(function(){
var d=document,root=d.getElementById("bgt"),data=d.getElementById("bgt-data");if(!root||!data)return;
var box=root.firstElementChild,D=JSON.parse(data.textContent),tok=D.tok,q=new URLSearchParams(location.search),hex=/^[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/;
["lit","unlit"].forEach(function(k){var v=q.get(k);if(v&&hex.test(v))tok[k]="#"+v;});
var g=parseFloat(q.get("glow"));if(g>=0&&g<=1)tok.glow=String(g);
var du=parseFloat(q.get("dur"));if(du>=0)d.documentElement.style.setProperty("--bgt-dur",du+"s");else du=D.dur;
root.dataset.glow=tok.glow;root.dataset.dur=du;
function url(src){return URL.createObjectURL(new Blob([src.replace(/@(\w+)@/g,function(_,k){return tok[k];})],{type:"image/svg+xml"}));}
function place(i,b){var s=i.style;s.left=b[0]/16+"%";s.top=b[1]/10+"%";s.width=b[2]/16+"%";s.height=b[3]/10+"%";}
function img(cls,b,src){var i=new Image();i.className=cls;i.alt="";i.decoding="async";place(i,b);if(src)i.src=url(src);box.appendChild(i);return i;}
img("base",[0,0,1600,1000],D.base);
var st=D.steps.map(function(t){var i=img("st",t.b,t.src);i.dataset.s=t.s;i.dataset.n=t.n;return i;});
var fl=img("fl",[0,0,1600,1000]),flare=null,still=matchMedia("(prefers-reduced-motion: reduce)");
var hs=[].slice.call(d.querySelectorAll("main h2[id]")),past=hs.map(function(){return false;}),at=new Map(),to={},prev=-1,armed=false,jump=false;
hs.forEach(function(h,i){at.set(h.closest(".sect")||h,i);to[h.id]=i+1;});
[].forEach.call(d.querySelectorAll("main section[id]"),function(s){var h=s.querySelector("h2[id]");to[s.id]=h?to[h.id]-1:0;});
function target(h){var p=to[h.slice(1)];if(p!==undefined&&p!==prev)jump=true;}
addEventListener("load",function(){requestAnimationFrame(function(){armed=true;});});
addEventListener("popstate",function(){target(location.hash);});addEventListener("hashchange",function(){target(location.hash);});
d.addEventListener("click",function(e){var a=e.target.closest&&e.target.closest("a[href^='#']");if(a)target(a.getAttribute("href"));});
function sync(pos){
  if(pos===prev)return;
  var step=armed&&!jump&&prev>=0&&Math.abs(pos-prev)===1&&!still.matches;
  root.classList.toggle("fade",step);
  if(flare){flare.cancel();flare=null;}
  for(var i=0;i<st.length;i++)st[i].classList.toggle("on",+st[i].dataset.s<=pos);
  if(step&&pos>prev)for(var j=0;j<D.steps.length;j++){var t=D.steps[j];if(t.s===pos){
    if(!t.furl)t.furl=url(t.fsrc);fl.src=t.furl;place(fl,t.b);
    flare=fl.animate([{opacity:0},{opacity:+tok.glow,offset:.35},{opacity:0}],{duration:du*1000,easing:"ease-in-out"});}}
  prev=pos;jump=false;
}
var io=new IntersectionObserver(function(es){es.forEach(function(e){past[at.get(e.target)]=e.isIntersecting;});
  var p=0;for(var i=0;i<past.length;i++)if(past[i])p++;sync(p);},{rootMargin:"10000000px 0px -70% 0px"});
hs.forEach(function(h){io.observe(h.closest(".sect")||h);});
})();
"""


def build(order, js):
    """Return (css, html, js) for the page. order: h2 ids in page order. The tree script runs on its own; js is unchanged."""
    data = json.dumps(layers(json.loads(DATA.read_text()), order), separators=(",", ":"))
    html = f'<div class="bgt" id="bgt" aria-hidden="true"><div class="bgt-box"></div></div><script type="application/json" id="bgt-data">{data}</script>\n'
    return CSS, html, js + "\n" + JS
