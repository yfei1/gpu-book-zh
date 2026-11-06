// KaTeX at build time. Usage from a figure build.mjs:
//   import { render } from "../../../gh_book/tools/katex_render.mjs";   // adjust the path
//   const html = render("T \\times K", false);   // inline; true = display
// The page that holds the html must link  ../vendor/katex/katex.min.css  (done automatically for docs/figs/*.html).
// CLI (used by build_site.py): reads [{"tex":..., "display":bool}, ...] on stdin, writes [{"html":...}|{"error":...}, ...].
import katex from "katex";

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
  const out = JSON.parse(input).map(({ tex, display }) => {
    try {
      const html = render(tex, display);
      const error = check(html);
      return error ? { error } : { html };
    } catch (e) {
      return { error: String(e.message || e) };
    }
  });
  process.stdout.write(JSON.stringify(out));
}
