import {chromium} from "/Users/yufanfei/tock-sniper/node_modules/playwright-core/index.mjs";
import {mkdirSync,rmSync} from "node:fs";
const T="/Users/yufanfei/GolandProjects/open-kernel-challenge-triad/audit_out/w25/orch/gpu_tutor/gh_book/layout_shots/r23_publish/_t";mkdirSync(T,{recursive:true});
const br=await chromium.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",env:{...process.env,TMPDIR:T+"/"}});
const pg=await br.newPage({viewport:{width:1720,height:860}});
await pg.goto("http://127.0.0.1:8765/index.html#ch00_0");await pg.waitForTimeout(800);
const r=await pg.evaluate(async()=>{const f=document.querySelector('iframe[src*="ch00_0-archo"],iframe[data-src*="ch00_0-archo"]');if(!f)return "noframe";f.scrollIntoView({block:"center"});await new Promise(r=>setTimeout(r,1500));const d=f.contentDocument.documentElement;const b=f.getBoundingClientRect();return {fh:b.height,fw:b.width,sh:d.scrollHeight,ch:d.clientHeight,sw:d.scrollWidth,cw:d.clientWidth,katexErr:document.querySelectorAll(".katex-error").length,red:[...document.querySelectorAll("#ch00_0-1 *")].filter(e=>getComputedStyle(e).color=="rgb(204, 0, 0)").length}});
console.log(JSON.stringify(r));await pg.screenshot({path:T+"/../w1720_archo.png"});await br.close();rmSync(T,{recursive:true,force:true});