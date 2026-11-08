// Layout screenshots of docs/index.html. Usage: node shots.mjs <outdir> [chrome|webkit] [view-name regex]
// Opens docs/index.html (file://), opens each view in headless Chrome, writes one PNG per view
// and prints the measured geometry (column, sidebar, rail, overflow) as JSON lines.
import { chromium, webkit } from "/Users/yufanfei/tock-sniper/node_modules/playwright-core/index.mjs";
import { mkdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
const HERE = dirname(fileURLToPath(import.meta.url));
const DOCS = join(HERE, "..", "..", "docs");
const out = process.argv[2] || HERE;
const engine = process.argv[3] || "chrome";
mkdirSync(out, { recursive: true });
const base = "http://127.0.0.1:8765/index.html";
const VIEWS = [
  ["w1720_dy1_s5", 1720, 860, 1, "ch00_0-5"], ["w1720_ch04", 1720, 860, 1, "ch04"], ["w1720_ch04_s2", 1720, 860, 1, "ch04-2"],
  ["w1440_dy1_s5", 1440, 900, 1, "ch00_0-5"], ["w1440_ch04", 1440, 900, 1, "ch04"], ["w1440_top", 1440, 900, 1, ""],
  ["w1920_dy1_s5", 1920, 1080, 1, "ch00_0-5"], ["w1920_ch04", 1920, 1080, 1, "ch04"],
  ["w1180_ch04_s2", 1180, 800, 1, "ch04-2"],
  ["w900_dy1_s5", 900, 900, 1, "ch00_0-5"], ["w900_ch04", 900, 900, 1, "ch04"],
  ["w390_dy1_s5", 390, 844, 2, "ch00_0-5"], ["w390_ch04", 390, 844, 2, "ch04"], ["w390_ch04_open", 390, 844, 2, "ch04-2", "open"],
  ["w900_ch04_open", 900, 900, 1, "ch04-2", "open"],
];
const only = process.argv[4] ? new RegExp(process.argv[4]) : null;
// Chrome binds its singleton socket under TMPDIR; keep that inside this folder and remove it at exit.
const TMP = join(out, "_chrome_tmp");
mkdirSync(TMP, { recursive: true });
const clean = () => rmSync(TMP, { recursive: true, force: true });
process.on("exit", clean); for (const s of ["SIGINT", "SIGTERM"]) process.on(s, () => process.exit(130));
const br = engine === "webkit"
  ? await webkit.launch({ executablePath: "/Users/yufanfei/Library/Caches/ms-playwright/webkit-2370/pw_run.sh" })
  : await chromium.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", env: { ...process.env, TMPDIR: TMP + "/", MAC_CHROMIUM_TMPDIR: TMP } });
let bad = 0;
for (const [name, w, h, dsf, hash, mode] of VIEWS) {
  if (only && !only.test(name)) continue;
  const pg = await br.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: dsf });
  const errs = [];
  pg.on("pageerror", (e) => errs.push("pageerror " + e.message));
  pg.on("console", (m) => { if (m.type() === "error") errs.push("console " + m.text()); });
  await pg.goto(base + (hash ? "#" + hash : ""), { waitUntil: "load" });
  await pg.waitForTimeout(400);
  if (hash) await pg.evaluate((id) => document.getElementById(id).scrollIntoView(), hash);
  await pg.waitForTimeout(700);
  if (mode === "open") { await pg.click("#toc-btn"); await pg.waitForTimeout(400); }
  const fonts = await pg.evaluate(async()=>{await document.fonts.ready;return [...document.fonts].filter(f=>f.status=="loaded").map(f=>f.family).join(",")+" | iframes "+document.querySelectorAll("iframe").length});console.log(name,fonts);
  const geo = await pg.evaluate(() => {
    const r = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); const cs = getComputedStyle(e);
      return cs.display === "none" || cs.visibility === "hidden" ? null : [Math.round(b.left), Math.round(b.right), Math.round(b.width)]; };
    const p = document.querySelector("main section > p"), cs = p && getComputedStyle(p);
    return { vw: innerWidth, sw: document.documentElement.scrollWidth, col: r("main .col"), toc: r("#toc"), rail: r("#rail"),
      body: cs && cs.fontSize + "/" + cs.lineHeight, cjkPerLine: p ? Math.round(p.getBoundingClientRect().width / parseFloat(cs.fontSize)) : 0 };
  });
  console.log(JSON.stringify({ name, ...geo, errors: errs.length }));
  await pg.screenshot({ path: join(out, `${name}.png`) });
  if (errs.length) { bad++; console.log(errs.slice(0, 6).join("\n")); }
  await pg.close();
}
await br.close();
process.exit(bad ? 1 : 0);
