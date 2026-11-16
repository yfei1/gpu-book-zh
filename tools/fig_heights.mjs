// Measure each figure's height at the 780 px desktop column, for tools/build_site.py (FIG_HEIGHTS).
// Usage: BOOK_OUT=<dir>/zh and <dir>/en preview builds, then:  node tools/fig_heights.mjs <dir> tools/fig_heights.json
// Needs playwright-core (PLAYWRIGHT_CORE=<path to playwright-core/index.mjs>) and Google Chrome.
import { mkdtempSync, rmSync, writeFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
const { chromium } = await import(process.env.PLAYWRIGHT_CORE || "playwright-core");
const [SITE, OUT] = process.argv.slice(2).map(p => resolve(p));
const TMP = mkdtempSync(join(dirname(OUT), ".fig_heights-"));
const clean = () => rmSync(TMP, { recursive: true, force: true });
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => { clean(); process.exit(1); });
const br = await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: false,
  env: { ...process.env, TMPDIR: TMP + "/", MAC_CHROMIUM_TMPDIR: TMP }, args: ["--headless=new", "--no-first-run"] });
try {
  const pg = await (await br.newContext({ viewport: { width: 780, height: 900 } })).newPage();
  const res = {};
  for (const lang of ["zh", "en"]) for (const f of readdirSync(join(SITE, lang, "figs")).filter(f => f.endsWith(".html")).sort()) {
    await pg.goto(pathToFileURL(join(SITE, lang, "figs", f)).href, { waitUntil: "load" });
    await pg.evaluate(() => document.fonts.ready); await pg.waitForTimeout(400);
    res[`${lang}/${f.slice(0, -5)}`] = await pg.evaluate(() => Math.ceil(document.body.getBoundingClientRect().height));
  }
  writeFileSync(OUT, JSON.stringify(res, Object.keys(res).sort(), 0).replace(/,"/g, ',\n"') + "\n");
} finally { await br.close(); clean(); }
