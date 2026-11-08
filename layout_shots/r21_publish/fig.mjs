
import { chromium } from "/Users/yufanfei/tock-sniper/node_modules/playwright-core/index.mjs";
import { mkdirSync, rmSync } from "node:fs";
const TMP="layout_shots/r21_publish/_t"; mkdirSync(TMP,{recursive:true});
process.on("exit",()=>rmSync(TMP,{recursive:true,force:true}));
const br=await chromium.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",env:{...process.env,TMPDIR:process.cwd()+"/"+TMP+"/",MAC_CHROMIUM_TMPDIR:TMP}});
const pg=await br.newPage({viewport:{width:1720,height:860}});
pg.on("response",r=>{if(r.status()>=400)console.log("HTTP",r.status(),r.url())});
await pg.goto("http://127.0.0.1:8765/index.html#ch00_0",{waitUntil:"load"});
await pg.waitForTimeout(800);
const f=pg.locator("iframe[src*=archo]").first();
await f.scrollIntoViewIfNeeded(); await pg.waitForTimeout(1500);
console.log(JSON.stringify(await pg.evaluate(()=>{const i=document.querySelector("iframe[src*=archo]");const b=i.getBoundingClientRect();const d=i.contentDocument.documentElement;return {box:[b.width,b.height],inner:[d.scrollWidth,d.scrollHeight,d.clientWidth,d.clientHeight],fonts:[...document.fonts].filter(x=>x.status=="loaded").map(x=>x.family)}})));
await pg.screenshot({path:"layout_shots/r21_publish/w1720_fig_dy1-1.png"});
await br.close();
