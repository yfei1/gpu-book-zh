// Measure each .sect height in a built site, for tools/build_site.py (sect_heights.json).
// Usage: build the site (docs/ layout: zh at the root, en/ below), then:  node tools/sect_heights.mjs <docs dir> tools/sect_heights.json
// Widths 390, 1100 and 1440 px: one per breakpoint range of the page CSS (<=600, 601-1279, >=1280). Each section is measured laid out,
// with the containment that content-visibility:auto gives it on screen, so the height equals the one the page shows.
// "_median" holds the median section height per language and width: the fallback for a section that has no measured height.
// Needs playwright-core (PLAYWRIGHT_CORE=<path to playwright-core/index.mjs>) and Google Chrome.
import { mkdtempSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, resolve } from "node:path";
const { chromium } = await import(process.env.PLAYWRIGHT_CORE || "playwright-core");
const [SITE, OUT] = process.argv.slice(2).map((p) => resolve(p));
const TMP = mkdtempSync(join(dirname(OUT), ".sect_heights-"));
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".png": "image/png" };
const srv = createServer((rq, rs) => { let p = join(SITE, decodeURIComponent(rq.url.split("?")[0])); try { if (statSync(p).isDirectory()) p = join(p, "index.html"); rs.setHeader("content-type", TYPES[extname(p)] || "application/octet-stream"); rs.end(readFileSync(p)); } catch { rs.statusCode = 404; rs.end(); } });
await new Promise((r) => srv.listen(0, "127.0.0.1", r));
const clean = () => { rmSync(TMP, { recursive: true, force: true }); srv.close(); };
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => { clean(); process.exit(1); });
const br = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", env: { ...process.env, TMPDIR: TMP + "/", MAC_CHROMIUM_TMPDIR: TMP } });
try {
  const res = { _median: {} };
  for (const [lang, path] of [["zh", "/index.html"], ["en", "/en/index.html"]]) for (const w of [390, 1100, 1440]) {
    const pg = await br.newPage({ viewport: { width: w, height: w === 390 ? 844 : 900 } });
    await pg.goto(`http://127.0.0.1:${srv.address().port}${path}`, { waitUntil: "load" });
    await pg.addStyleTag({ content: ".sect{content-visibility:visible!important;contain:layout style paint}" });
    await pg.evaluate(() => document.fonts.ready); await pg.waitForTimeout(500);
    const hs = await pg.evaluate(() => [...document.querySelectorAll(".sect[data-k]")].map((s) => [s.dataset.k, Math.round(s.getBoundingClientRect().height * 64) / 64]));
    for (const [k, h] of hs) (res[k] ||= {})[w] = h;
    const sorted = hs.map(([, h]) => h).sort((a, b) => a - b);
    (res._median[lang] ||= {})[w] = Math.round(sorted[sorted.length >> 1]);
    console.log(lang, w, hs.length, "sections, median", res._median[lang][w], "sum", Math.round(sorted.reduce((a, b) => a + b, 0)));
    await pg.close();
  }
  writeFileSync(OUT, "{\n" + Object.keys(res).sort().map((k) => JSON.stringify(k) + ":" + JSON.stringify(res[k])).join(",\n") + "\n}\n");
} finally { await br.close(); clean(); }
