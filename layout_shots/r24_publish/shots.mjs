import { chromium } from "/Users/yufanfei/tock-sniper/node_modules/playwright-core/index.mjs";
import { mkdirSync, rmSync } from "node:fs";
const out=process.argv[2]; const TMP=out+"/_t"; mkdirSync(TMP,{recursive:true});
process.on("exit",()=>rmSync(TMP,{recursive:true,force:true}));
const br=await chromium.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",env:{...process.env,TMPDIR:TMP+"/"}});
const V=[["top1720",1720,860,"ch00_0",0,"fig"],["ch04",1440,900,"ch04"],["ch07",1920,1080,"ch07"],["w900_open",900,900,"ch00_0","open"],["w390_s5_open",390,844,"ch00_0-5","open"]];
for(const [n,w,h,hash,m,f] of V){const pg=await br.newPage({viewport:{width:w,height:h}});
await pg.goto("http://localhost:8765/index.html#"+hash,{waitUntil:"load"});await pg.waitForTimeout(800);
await pg.evaluate(id=>{const e=document.getElementById(id);e&&e.scrollIntoView()},hash);
if(f) await pg.evaluate(()=>{const e=document.querySelector("iframe");e&&e.scrollIntoView({block:"center"})});
await pg.waitForTimeout(1200);
if(m==="open"){await pg.click("#toc-btn");await pg.waitForTimeout(400);}
const g=await pg.evaluate(()=>({sw:document.documentElement.scrollWidth,iw:innerWidth,fonts:[...document.fonts].filter(x=>x.status=="loaded").map(x=>x.family),ifr:document.querySelectorAll("iframe").length,err:document.querySelectorAll(".katex-error").length}));
console.log(n,JSON.stringify(g));await pg.screenshot({path:out+"/"+n+".png"});await pg.close();}
await br.close();