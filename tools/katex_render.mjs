// KaTeX at build time. Usage from a figure build.mjs:
//   import { render } from "../../../gh_book/tools/katex_render.mjs";   // adjust the path
//   const html = render("T \\times K", false);   // inline; true = display
// The page that holds the html must link  ../vendor/katex/katex.min.css  (done automatically for docs/figs/*.html).
// CLI (used by build_site.py, with --mathml for MathML-only output): reads [{"tex":..., "display":bool}, ...] on stdin, writes [{"html":...}|{"error":...}, ...].
import katex from "katex";
import { readFileSync } from "node:fs";

// \shape{name}{dims}{dtype}  ->  name : [dims] dtype      \dt{dtype}  ->  grey dtype tag only
export const MACROS = {
  "\\dt": "\\textcolor{6b7280}{\\textsf{\\footnotesize #1}}",
  "\\shape": "#1\\,{:}\\;[#2]\\;\\dt{#3}",
};

export const OPTIONS = { output: "htmlAndMathml", throwOnError: false, strict: "ignore", trust: false, macros: MACROS, errorColor: "#cc00cc" };

// Read one {...} group starting at s[i] (s[i] === "{"); returns [content, indexAfter] or null.
function group(s, i) {
  if (s[i] !== "{") return null;
  let depth = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === "\\") { j++; continue; }
    if (s[j] === "{") depth++;
    else if (s[j] === "}" && --depth === 0) return [s.slice(i + 1, j), j + 1];
  }
  return null;
}

// A multi-letter name (topk_ids, stream\_0, W13, stream_0) is set upright; one letter or any command/superscript is left as written.
function upright(name) {
  if (/[\\^]/.test(name.replace(/\\_/g, ""))) return name;
  const m = name.match(/^([A-Za-z][A-Za-z0-9]*(?:\\_[A-Za-z0-9]+)*)(_.*)?$/);
  if (!m || m[1].replace(/\\_/g, "").length < 2) return name;
  return `\\mathrm{${m[1]}}${m[2] || ""}`;
}

// Dims are re-spaced so "T, 8192", "T,\\ 8192" and "T,\\;8192" all read the same.
const spaceDims = (d) => d.replace(/,(\s|\\[ ;,])*/g, ",\\;");

export function prepare(tex) {
  let out = "", i = 0;
  for (;;) {
    const k = tex.indexOf("\\shape{", i);
    if (k < 0) return out + tex.slice(i);
    const name = group(tex, k + 6);
    const dims = name && group(tex, name[1]);
    if (!dims) { out += tex.slice(i, k + 6); i = k + 6; continue; }
    out += `${tex.slice(i, k + 6)}{${upright(name[0])}}{${spaceDims(dims[0])}}`;
    i = dims[1];
  }
}

export function render(tex, displayMode = false) {
  return katex.renderToString(prepare(tex), { ...OPTIONS, displayMode });
}

// MathML-only output for the book text (build_site.py). Chrome implements MathML Core, which ignores mathvariant
// except "normal" on <mi>, so letters and digits of a styled <mi>/<mn> become Unicode math alphanumerics (the font
// has those glyphs). A styled <mtext> keeps its mathvariant as a CSS hook (build_site.py sets the font).
const ALNUM = {  // [A-Z/a-z start, 0-9 start or 0]
  "bold": [0x1D400, 0x1D7CE], "italic": [0x1D434, 0], "bold-italic": [0x1D468, 0],
  "sans-serif": [0x1D5A0, 0x1D7E2], "bold-sans-serif": [0x1D5D4, 0x1D7EC], "sans-serif-italic": [0x1D608, 0],
  "sans-serif-bold-italic": [0x1D63C, 0], "monospace": [0x1D670, 0x1D7F6],
};
export const MTEXT_VARIANTS = ["sans-serif", "monospace"];
function styled(text, variant) {
  const [az, d] = ALNUM[variant];
  return [...text].map((c) => {
    const k = c.charCodeAt(0);
    if (variant === "italic" && c === "h") return "\u210E";
    if (k >= 65 && k <= 90) return String.fromCodePoint(az + k - 65);
    if (k >= 97 && k <= 122) return String.fromCodePoint(az + 26 + k - 97);
    if (d && k >= 48 && k <= 57) return String.fromCodePoint(d + k - 48);
    return c;
  }).join("");
}
// KaTeX writes \, \: \; as space characters in <mtext> and \! \negmedspace \negthickspace as that space plus U+2063; the
// browser draws the character (\, is 0.2em in the font, and \! becomes a positive space). TeX's widths: 3, 4 and 5 mu.
const TEX_SPACE = { "\u2009": 0.1667, "\u2005": 0.2222, "\u205f": 0.2222, "\u2005\u200a": 0.2778 };
export function fixMathML(html) {
  return html
    .replace(/<mtext>(\u2009|\u2005|\u205f|\u2005\u200a)(\u2063?)<\/mtext>/g, (m, sp, neg) => `<mspace width="${neg ? "-" : ""}${TEX_SPACE[sp]}em"/>`)
    .replace(/<(mi|mn) mathvariant="([a-z-]+)">([^<]*)<\/\1>/g, (m, tag, v, text) => {
      if (v === "normal") return m;
      if (!ALNUM[v]) throw new Error(`mathvariant="${v}" has no Unicode mapping in katex_render.mjs`);
      return `<${tag}>${styled(text, v)}</${tag}>`;
    })
    // \bmod and \pmod: KaTeX puts an <mrow> of letters inside <mo>; MathML token elements hold text only.
    .replace(/<mo([^>]*)><mrow>((?:<mi mathvariant="normal">[^<]<\/mi>)+)<\/mrow><\/mo>/g, (m, a, letters) => `<mo${a}>${letters.replace(/<[^>]+>/g, "")}</mo>`)
    // \bar: U+02C9 is not in Latin Modern Math; U+00AF is, as a fixed-width accent like TeX's.
    .replace(/<mo>\u02C9<\/mo>/g, '<mo stretchy="false">\u00AF</mo>');
}
// A small tree for KaTeX's MathML (well-formed: elements, attributes, text).
function parseML(s) {
  const root = { tag: "", attrs: "", kids: [] }, stack = [root];
  for (const m of s.matchAll(/<(\/?)([a-zA-Z][\w-]*)((?:\s+[\w:-]+="[^"]*")*)\s*(\/?)>|([^<]+)/g)) {
    const top = stack[stack.length - 1];
    if (m[5] !== undefined) top.kids.push(m[5]);
    else if (m[1]) stack.pop();
    else { const el = { tag: m[2], attrs: m[3], kids: [], self: !!m[4] }; top.kids.push(el); if (!el.self) stack.push(el); }
  }
  return root;
}
const ser = (n) => typeof n === "string" ? n : !n.tag ? n.kids.map(ser).join("") : n.self ? `<${n.tag}${n.attrs}/>` : `<${n.tag}${n.attrs}>${n.kids.map(ser).join("")}</${n.tag}>`;
const text = (n) => (typeof n === "string" ? n : n.kids.map(text).join("")).replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&").trim();
const REL = new Set([..."=<>≤≥≈≠≡∼≃≅≪≫∈∉⊂⊆⊃⊇→←↔⇒⇐⇔⟹⟸⟺↦∝∣∥:"]), BIN = new Set([..."+−×÷⋅⊙⊕⊗±∓∗∘∙∧∨∩∪∖"]), PUNCT = new Set([...",;"]);
const isOp = (n, set) => typeof n !== "string" && n.tag === "mo" && set.has(text(n));
const SCRIPTED = new Set(["msub", "msup", "msubsup", "munder", "mover", "munderover", "mmultiscripts"]);
// TeX drops the medium and thick spaces around binary operators and relations (and the space after punctuation) in
// script and scriptscript style; MathML Core keeps the operator dictionary spacing at every depth, so k=0 under a sum
// would read "k = 0". Zero them where TeX is in script style: scripts, limits, and fraction parts of a text-style fraction.
function scriptSpacing(n, level, compact) {
  if (typeof n === "string") return;
  if (n.tag === "mo" && level > 0 && !/\s[lr]space=/.test(n.attrs) && [REL, BIN, PUNCT].some((s) => isOp(n, s))) n.attrs += ' lspace="0em" rspace="0em"';
  if (n.tag === "mstyle") {
    const d = n.attrs.match(/displaystyle="(true|false)"/), l = n.attrs.match(/scriptlevel="(\d+)"/);
    if (d) compact = d[1] === "false";
    if (l) level = +l[1];
  }
  n.kids.forEach((k, i) => {
    if (SCRIPTED.has(n.tag) && i > 0) scriptSpacing(k, level + 1, true);
    else if (n.tag === "mfrac") scriptSpacing(k, compact ? level + 1 : level, true);
    else if (n.tag === "mroot" && i === 1) scriptSpacing(k, level + 2, true);
    else scriptSpacing(k, level, compact);
  });
}
// KaTeX's HTML output may wrap an inline formula after a top-level relation or binary operator; one <math> element never
// wraps. Split the top-level row there into several <math> elements, so a long formula still wraps in a narrow column.
const GLUE = (n) => typeof n !== "string" && (n.tag === "mspace" || (n.tag === "mtext" && text(n) === ""));
function splitInline(math) {
  const sem = math.kids.find((k) => k.tag === "semantics"), row = sem && sem.kids[0];
  if (!row || row.tag !== "mrow") return null;
  const kids = row.kids, parts = [];
  let cur = [];
  for (let i = 0; i < kids.length; i++) {
    cur.push(kids[i]);
    if (!(isOp(kids[i], REL) || isOp(kids[i], BIN)) || ORD_OP.test(kids[i].attrs) || i === 0 || isOp(kids[i - 1], REL) || isOp(kids[i - 1], BIN)) continue;
    let j = i + 1;
    while (j < kids.length && GLUE(kids[j])) j++;
    if (j >= kids.length || isOp(kids[j], REL) || isOp(kids[j], BIN)) continue;
    if (!/\sform=/.test(kids[i].attrs)) kids[i].attrs += ' form="infix"';  // keeps the infix spacing at the end of its row
    cur.push(...kids.slice(i + 1, j)); i = j - 1;
    parts.push(cur); cur = [];
  }
  if (!parts.length) return null;
  parts.push(cur);
  // No <mrow> around a part: an <mrow> of <mtext> and one <mo> is an embellished operator in MathML Core, and would take
  // the operator's spacing outside itself ("base=" + space instead of "base = ").
  return parts.map((p) => `<math${math.attrs}>${p.map(ser).join("")}</math>`).join("<wbr>");
}
// KaTeX writes \mathrm{stream\_out} as one upright <mi> per letter; one <mi> per word sets the same glyphs (a multi-letter
// <mi> is upright) with kerning, in one element instead of ten.
const LETTER = (n) => typeof n !== "string" && n.tag === "mi" && n.attrs === ' mathvariant="normal"' && n.kids.length === 1 && [...n.kids[0]].length === 1;
// One-letter italic <mi> (no attribute; the browser applies math-auto). Find in page does not match across MathML tokens, so
// \mathit{acc} as <mi>a</mi><mi>c</mi><mi>c</mi> is not found by "acc"; one <mi> with the math-italic letters is (window.find).
const ITALIC_LETTER = (n) => typeof n !== "string" && n.tag === "mi" && n.attrs === "" && n.kids.length === 1 && /^[A-Za-z]$/.test(n.kids[0]);
// Only children of row-like elements form a run; <msub>, <mfrac>, <munder>... have fixed child positions (MathML Core).
const ROWLIKE = new Set(["math", "mrow", "msqrt", "mstyle", "mpadded", "mphantom", "menclose", "mtd", "merror"]);
// An italic run is merged only when it is a whole group (\mathit{acc}, _{norm}: an <mrow> of italic letters only), a name.
// Letters in a longer row, or a whole formula ($PV$), are a product: TeX puts each letter's italic correction between them.
// \mathit{acc} as a whole formula is a name too (TeX sets \mathit in a text font: no correction between the letters).
function mergeLetters(n, mathit, top = false) {
  if (typeof n === "string") return;
  if (!ROWLIKE.has(n.tag)) { n.kids.forEach((k) => mergeLetters(k, mathit, n.tag === "semantics" || n.tag === "math")); return; }
  const els = n.kids.filter((k) => typeof k !== "string"), name = (mathit || !top) && n.tag === "mrow" && els.length > 1 && els.every(ITALIC_LETTER);
  const out = [];
  for (const k of n.kids) {
    const last = out[out.length - 1];
    if (LETTER(k) && last && (LETTER(last) || last.merged === "normal")) { last.kids[0] += k.kids[0]; last.attrs = ""; last.merged = "normal"; }
    else if (name && ITALIC_LETTER(k) && last && (ITALIC_LETTER(last) || last.merged === "italic")) {
      if (!last.merged) last.kids[0] = styled(last.kids[0], "italic");
      last.kids[0] += styled(k.kids[0], "italic"); last.merged = "italic";
    } else out.push(k);
  }
  n.kids = out;
  n.kids.forEach((k) => mergeLetters(k, mathit));
}
// KaTeX's MathML drops the class of \mathrel{+}: "+=" got binary + relation spacing ("acc + ="). TeX puts no space between two
// relations and a thick space (0.2778em, the "=" spacing in MathML Core) outside them.
function relPlus(n) {
  if (typeof n === "string") return;
  const k = n.kids;
  for (let i = 0; i + 1 < k.length; i++)
    if (k[i].tag === "mo" && k[i].kids[0] === "+" && k[i + 1].tag === "mo" && k[i + 1].kids[0] === "=") { k[i].attrs += ' lspace="0.2778em" rspace="0em"'; k[i + 1].attrs += ' lspace="0em"'; }
  k.forEach(relPlus);
}
// TeX spacing (TeXbook Appendix G, the inter-atom space table and rules 5 and 6), set as explicit lspace/rspace on each binary,
// relation and punctuation <mo> of a row. MathML Core takes the space from its operator dictionary instead, which differs from
// TeX: "×" and "⋅" get 0.1667em instead of 0.2222em, ":" gets 0, and a binary operator keeps its space where TeX makes it
// ordinary (first in a row or after an operator, relation, opening or punctuation: unary "−"; last in a row or before a
// relation, closing or punctuation: "8.3×"), and a relation keeps its space at the edge of a row ("= 2" as a whole formula).
// Script levels are done before (scriptSpacing): TeX has no such space there.
const THIN = "0.1667em", MED = "0.2222em", THICK = "0.2778em";
const OPEN = new Set([..."([{⟨⌊⌈"]), CLOSE = new Set([...")]}⟩⌋⌉"]), LARGE = new Set([..."∑∏∫∬∮⋃⋂⨁⨂"]);
const ORD_OP = /form="prefix"|lspace="0em" rspace="0em"/;
const FAPPLY = "⁡";  // KaTeX writes \log, \ln, \max as <mi>log</mi><mo>&#x2061;</mo> (function application)
const endsApply = (n) => n.tag === "mrow" && n.kids.length > 1 && isOp(n.kids[n.kids.length - 1], new Set([FAPPLY]));
function atomClass(n, next) {
  if (n.tag === "annotation" || n.tag === "mspace" || (n.tag === "mtext" && text(n) === "")) return null;
  if (SCRIPTED.has(n.tag)) { const base = n.kids.find((k) => typeof k !== "string"); return base && (endsApply(base) ? "op" : atomClass(base, null)) || "ord"; }
  if (n.tag !== "mo") return next && next.tag === "mo" && text(next) === FAPPLY ? "op" : endsApply(n) ? "op" : "ord";
  const t = text(n);
  if (t === FAPPLY) return null;
  if (/\slspace="0em"/.test(n.attrs) && /\srspace="0em"/.test(n.attrs)) return "ord";  // KaTeX's {:} and other ord groups
  if (/\sfence="false"/.test(n.attrs)) return "ord";  // \big( is an ordinary atom in TeX; \bigl( and \left( are opening ones
  return REL.has(t) ? "rel" : BIN.has(t) ? "bin" : PUNCT.has(t) ? "punct" : OPEN.has(t) ? "open" : CLOSE.has(t) ? "close" : LARGE.has(t) ? "op" : t === "…" ? "inner" : "ord";
}
const setSpace = (d, l, r, prefix) => { d.attrs += `${prefix ? ' form="prefix"' : ""} lspace="${l}" rspace="${r}"`; };
function texSpacing(n) {
  if (typeof n === "string") return;
  if (ROWLIKE.has(n.tag) || n.tag === "semantics") {
    const els = n.kids.filter((k) => typeof k !== "string");
    const atoms = els.map((k, i) => [k, atomClass(k, els[i + 1])]).filter(([, c]) => c !== null);
    atoms.forEach(([d, c], i) => {
      if (d.tag !== "mo" || /\s[lr]space=/.test(d.attrs)) return;
      const p = i > 0 ? atoms[i - 1][1] : null, x = i + 1 < atoms.length ? atoms[i + 1][1] : null;
      if (c === "bin") {
        if (p === null || ["bin", "op", "rel", "open", "punct"].includes(p)) { setSpace(d, "0em", "0em", true); atoms[i][1] = "ord"; }
        else if (x === null || ["rel", "close", "punct"].includes(x)) { setSpace(d, "0em", "0em"); atoms[i][1] = "ord"; }
        else setSpace(d, MED, MED);
      } else if (c === "rel") setSpace(d, p === null || ["rel", "open", "punct"].includes(p) ? "0em" : THICK, x === null || ["rel", "close", "punct"].includes(x) ? "0em" : THICK);
      else if (c === "punct") setSpace(d, "0em", x === null ? "0em" : THIN);
      else if (c === "open" || c === "close" || OPEN.has(text(d)) || CLOSE.has(text(d))) setSpace(d, "0em", "0em");  // the neighbour owns the space
    });
    // A function name (op) is followed by a thin space when an ordinary, operator or inner atom follows (TeX: \log x, \log_2 e).
    const out = [];
    n.kids.forEach((k, i) => {
      out.push(k);
      if (typeof k === "string") return;
      const a = atoms.findIndex(([d]) => d === k), nx = a >= 0 && a + 1 < atoms.length ? atoms[a + 1][1] : null;
      const thin = nx !== null && ["ord", "op", "inner"].includes(nx);
      if (k.tag === "mo" && text(k) === FAPPLY && !/\s[lr]space=/.test(k.attrs)) {
        const after = atoms.find(([d]) => n.kids.indexOf(d) > i);
        if (after && ["ord", "op", "inner"].includes(after[1])) k.attrs += ` rspace="${THIN}"`;
      } else if (a >= 0 && SCRIPTED.has(k.tag) && atoms[a][1] === "op" && endsApply(k.kids.find((c) => typeof c !== "string")) && thin)
        out.push({ tag: "mspace", attrs: ` width="${THIN}"`, kids: [], self: true });
    });
    n.kids = out;
  }
  n.kids.forEach(texSpacing);
}
// Italic correction (font MATH table, written by subset_math_font.py): TeX adds it after a math italic letter, so a slanted
// "W" does not touch the next word and "T =" keeps its gap. MathML Core uses it only to place a superscript, so add it as
// a margin after each italic <mi> that is not a script base. The base of <msup> gets it too: TeX sets the superscript after the
// correction, and Chrome does not (V^\top was 3 px narrower than the HTML pages). <msub> and <msubsup> bases do not: TeX sets
// the subscript at the letter's edge.
const FONT_INFO = JSON.parse(readFileSync(new URL("./fonts/GPUBookMath-subset.json", import.meta.url), "utf8"));
const ITALIC_IC = FONT_INFO.italic || {};
const AUTO = {  // MathML Core italic mapping of a one-character <mi> (text-transform: math-auto), for the letters TeX sets italic
  ...Object.fromEntries([...Array(26)].flatMap((_, i) => [[String.fromCharCode(65 + i), String.fromCodePoint(0x1D434 + i)], [String.fromCharCode(97 + i), String.fromCodePoint(0x1D44E + i)]])),
  h: "ℎ", ...Object.fromEntries([...Array(25)].map((_, i) => [String.fromCharCode(0x3B1 + i), String.fromCodePoint(0x1D6FC + i)])),
};
// Only math italic letters (TeX's cmmi, a math font): an upright name such as "lse" or \mathrm{f} gets no correction.
const MATH_ITALIC = (c) => { const k = c.codePointAt(0); return (k >= 0x1D434 && k <= 0x1D467) || k === 0x210E || (k >= 0x1D6E2 && k <= 0x1D71B); };
function italicCorrection(n, isBase) {
  if (typeof n === "string") return;
  if (n.tag === "mi" && !isBase && !/\s(mathvariant|style)=/.test(n.attrs)) {
    const t = [...text(n)], last = t.length === 1 ? AUTO[t[0]] || t[0] : t[t.length - 1], ic = MATH_ITALIC(last) && ITALIC_IC[last];
    if (ic) n.attrs += ` style="margin-inline-end:${ic}em"`;
  }
  n.kids.forEach((k, i) => italicCorrection(k, SCRIPTED.has(n.tag) && n.tag !== "msup" && i === 0));
}
// "…" is not in the MathML Core operator dictionary, so it gets the default 0.2778em on both sides. TeX makes \ldots an inner
// atom: a thin space (0.1667em) next to an ordinary or punctuation atom; next to an operator the operator's own space applies.
function dotsSpacing(n) {
  if (typeof n === "string") return;
  const k = n.kids.filter((x) => typeof x !== "string");
  k.forEach((d, i) => {
    if (d.tag !== "mo" || d.kids[0] !== "\u2026" || /\s[lr]space=/.test(d.attrs)) return;
    const prev = k[i - 1], next = k[i + 1];
    const l = !prev || prev.tag === "mo" ? "0em" : "0.1667em";
    const r = !next || (next.tag === "mo" && next.kids[0] !== ",") ? "0em" : "0.1667em";
    d.attrs += ` lspace="${l}" rspace="${r}"`;
  });
  n.kids.forEach(dotsSpacing);
}
// P' is <msup><mi>P</mi><mo>′</mo></msup> in KaTeX's MathML. The font's U+2032 is already a raised glyph (TeX's \prime is not),
// so as a superscript it sat high and apart from the letter; set after the letter, it looks as in the HTML pages.
const PRIMES = /^[′″‴]+$/;
function primes(n) {
  if (typeof n === "string") return;
  n.kids = n.kids.map((k) => {
    if (typeof k === "string" || k.tag !== "msup") return k;
    const [base, sup, ...rest] = k.kids.filter((c) => typeof c !== "string");
    const marks = sup && (sup.tag === "mo" ? [sup] : sup.tag === "mrow" ? sup.kids.filter((c) => typeof c !== "string") : []);
    if (rest.length || !marks || !marks.length || !marks.every((m) => m.tag === "mo" && PRIMES.test(text(m)))) return k;
    return { tag: "mrow", attrs: "", kids: [base, { tag: "mo", attrs: ' lspace="0em" rspace="0em"', kids: [marks.map(text).join("")] }] };
  });
  n.kids.forEach(primes);
}
function restructure(html, displayMode, tex = "") {
  const tree = parseML(html), span = tree.kids[0], math = span && span.kids && span.kids[0];
  if (!math || math.tag !== "math") return html;
  primes(math);
  if (tex.includes("\\mathrel{+}=")) relPlus(math);
  mergeLetters(math, tex.includes("\\mathit{"));
  dotsSpacing(math);
  scriptSpacing(math, 0, !displayMode);
  texSpacing(math);
  italicCorrection(math, false);
  const split = displayMode ? null : splitInline(math);
  return split ? `<span${span.attrs}>${split}</span>` : ser(tree);
}

export function checkMathML(html) {
  const v = html.match(/<(mi|mn|mo)\b[^>]*mathvariant="(?!normal")([^"]*)"/) || html.match(/<mtext\b[^>]*mathvariant="([^"]*)"/);
  if (v && !(v[0].startsWith("<mtext") && MTEXT_VARIANTS.includes(v[1]))) return `unsupported ${v[0]}`;
  if (/<mo\b[^>]*><m/.test(html)) return "element inside <mo>";
  return null;
}
export function renderMathML(tex, displayMode = false) {
  return restructure(fixMathML(katex.renderToString(prepare(tex), { ...OPTIONS, output: "mathml", displayMode })), displayMode, tex);
}

export function check(html) {
  const bad = html.match(/<mstyle mathcolor="#cc00cc"><mtext>([^<]*)<\/mtext>/);
  if (bad) return `undefined or invalid command ${bad[1]}`;
  const m = html.match(/class="katex-error"[^>]*title="([^"]*)"/);
  return m ? m[1].replace(/&quot;/g, '"').replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">") : null;
}

if (process.argv[1] && import.meta.url === new URL(process.argv[1], "file://").href) {
  let input = "";
  process.stdin.setEncoding("utf8");
  for await (const chunk of process.stdin) input += chunk;
  const mathml = process.argv.includes("--mathml");
  const out = JSON.parse(input).map(({ tex, display }) => {
    try {
      const html = mathml ? renderMathML(tex, display) : render(tex, display);
      const error = check(html) || (mathml && checkMathML(html));
      return error ? { error } : { html };
    } catch (e) {
      return { error: String(e.message || e) };
    }
  });
  process.stdout.write(JSON.stringify(out));
}
