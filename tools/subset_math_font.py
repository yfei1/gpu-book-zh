#!/usr/bin/env python3
"""Subset Latin Modern Math to the characters of the book's MathML, for build_site.py.

Source font: https://mirrors.ctan.org/fonts/lm-math/opentype/latinmodern-math.otf (GUST Font License, tools/fonts/GUST-FONT-LICENSE.txt).
Run from the repo root after a build (the pages give the character list):
  uv run --no-project --with fonttools --with brotli python tools/subset_math_font.py latinmodern-math.otf docs/index.html docs/en/index.html
Writes tools/fonts/GPUBookMath-subset.woff2 and tools/fonts/GPUBookMath-subset.json. build_site.py fails when the book's
math uses a character that neither list in the JSON holds; run this script again then.
The GUST Font License requests a new name for a derived font, so the subset is named "GPU Book Math".
"""
import hashlib, html, json, re, sys
from pathlib import Path

FONTS = Path(__file__).resolve().parent / "fonts"
NAME = "GPUBookMath-subset"


# MathML Core "italic mappings" (https://w3c.github.io/mathml-core/#italic-mappings): the browser draws a one-character
# <mi> without mathvariant (UA style text-transform: math-auto) with these code points, so the font needs them, not the text.
ITALIC = {**{chr(0x41 + i): chr(0x1D434 + i) for i in range(26)}, **{chr(0x61 + i): chr(0x1D44E + i) for i in range(26)},
          "h": "\u210e", "\u0131": "\U0001d6a4", "\u0237": "\U0001d6a5",
          **{chr(0x391 + i): chr(0x1D6E2 + i) for i in range(25) if i != 0x11}, "\u03f4": "\U0001d6f3", "\u2207": "\U0001d6fb",
          **{chr(0x3B1 + i): chr(0x1D6FC + i) for i in range(25)},
          **dict(zip("\u2202\u03f5\u03d1\u03f0\u03d5\u03f1\u03d6", map(chr, range(0x1D715, 0x1D71C))))}


def _auto_italic(m):
    t = html.unescape(m.group(2)).strip()
    return m.group(0) if "mathvariant" in m.group(1) or len(t) != 1 else ITALIC.get(t, t)


def math_chars(page):
    """Characters that the browser draws inside <math> elements (not the TeX annotation); build_site.py checks with it too."""
    out = set()
    for m in re.finditer(r"<math\b.*?</math>", page, re.S):
        ml = re.sub(r"<annotation\b.*?</annotation>", "", m.group(0), flags=re.S)
        ml = re.sub(r"<mi\b([^>]*)>([^<]*)</mi>", _auto_italic, ml)
        out |= set(html.unescape(re.sub(r"<[^>]+>", "", ml)))
        if "<msqrt" in ml or "<mroot" in ml:
            out.add("\u221a")  # the radical sign is drawn from the font but is not in the text
    return out - {"\n"}


def main():
    src, pages = Path(sys.argv[1]), sys.argv[2:]
    if not pages:
        sys.exit(__doc__)
    from fontTools import subset
    from fontTools.ttLib import TTFont
    chars = set().union(*(math_chars(Path(p).read_text()) for p in pages))
    font = TTFont(src)
    cmap = font.getBestCmap()
    kept = sorted(c for c in chars if ord(c) in cmap)
    absent = sorted(c for c in chars if ord(c) not in cmap)  # CJK and others: the browser takes them from the next font
    opt = subset.Options()
    opt.flavor, opt.layout_features, opt.name_IDs, opt.notdef_outline = "woff2", ["*"], ["*"], True
    sub = subset.Subsetter(opt)
    sub.populate(unicodes=[ord(c) for c in kept])
    sub.subset(font)  # keeps the MATH table and the size variants and assembly parts of the kept glyphs
    math = font["MATH"].table
    # Subscript position as in TeX (TeXbook Appendix G, rule 18a; KaTeX, the renderer of the HTML pages): the shift of a
    # subscript on a one-character base is sub1 = 0.15 em (cmsy10 sigma16), and the base depth does not count.
    # Latin Modern Math sets 0.247 em (TeX's sub2, the shift when a superscript is present) and a 0.2 em drop below the
    # base depth, so a MathML Core browser set x_i and beta_1 lower than the HTML pages did. A subscript with a superscript
    # still moves down to keep SubSuperscriptGapMin, as TeX's sub2 does.
    math.MathConstants.SubscriptShiftDown.Value = 150
    math.MathConstants.SubscriptBaselineDropMin.Value = 0
    # Italic correction of each kept character (em): TeX adds it after a math italic letter that is not a script base;
    # MathML Core uses it only to place scripts, so katex_render.mjs adds it as a margin (MATH table, not a constant).
    upem, info = font["head"].unitsPerEm, math.MathGlyphInfo.MathItalicsCorrectionInfo
    ic = {g: r.Value for g, r in zip(info.Coverage.glyphs, info.ItalicsCorrection)} if info else {}
    gcmap = font.getBestCmap()
    italic = {c: round(ic[gcmap[ord(c)]] / upem, 4) for c in kept if ic.get(gcmap.get(ord(c)), 0) > 0}
    for rec in font["name"].names:
        s = rec.toUnicode()
        t = s.replace("LatinModernMath", "GPUBookMath").replace("Latin Modern Math", "GPU Book Math")
        if t != s:
            rec.string = t
    font.flavor = "woff2"
    font.save(FONTS / f"{NAME}.woff2")
    (FONTS / f"{NAME}.json").write_text(json.dumps({
        "source": src.name, "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "kept": "".join(kept), "absent": "".join(absent), "italic": italic}, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(kept)} characters kept, {len(font.getGlyphOrder())} glyphs, {(FONTS / f'{NAME}.woff2').stat().st_size} bytes; "
          f"{len(absent)} characters not in the font (fallback): {''.join(absent)}")


if __name__ == "__main__":
    main()
