import { chromium } from "/Users/yufanfei/tock-sniper/node_modules/playwright-core/index.mjs";
import { mkdirSync, rmSync } from "node:fs";
const out=process.argv[2]; const TMP=out+"/_t"; mkdirSync(TMP,{recursive:true});
process.on("exit",()=>rmSync(TMP,{recursive:true,force:true}));
const br=await chromium.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",env:{...process.env,TMPDIR:TMP+"/"}});
const V=[["w1720_dy1_top",1720,860,1,"ch00_0","fig"],["w1440_ch04",1440,900,1,"ch04"],["w1920_ch07",1920,1080,1,"ch07"],["w900_top_open",900,900,1,"","open"],["w390_dy1_s5_open",390,844,2,"ch00_0-5","open"],["w1720_dy1_s1",1720,860,1,"ch00_0-1"]];
for(const [n,w,h,d,hash,m] of V){
 const pg=await br.newPage({viewport:{width:w,height:h},deviceScaleFactor:d});
 await pg.goto("http://localhost:8765/index.html"+(hash?"#"+hash:""),{waitUntil:"load"});
 await pg.waitForTimeout(800);
 if(hash) await pg.evaluate(id=>document.getElementById(id).scrollIntoView(),hash);
 if(m==="fig") await pg.evaluate(()=>document.querySelector("iframe").scrollIntoView({block:"center"}));
 await pg.waitForTimeout(1200);
 if(m==="open"){await pg.click("#toc-btn");await pg.waitForTimeout(400);}
 const g=await pg.evaluate(()=>{const f=document.querySelector("iframe");let fi=null;try{const d=f.contentDocument.documentElement;fi=[f.clientWidth,f.clientHeight,d.scrollWidth,d.scrollHeight]}catch(e){fi="x"}
  return {sw:document.documentElement.scrollWidth,vw:innerWidth,font:[document.fonts.check("16px 'Noto Sans SC'"),[...document.fonts].filter(x=>x.status==="loaded").map(x=>x.family)],katexErr:document.querySelectorAll(".katex-error").length,redtext:document.querySelectorAll("[style*='color:#cc0000']").length,fi,wrap:[...document.querySelectorAll("code")].filter(c=>c.textContent.includes("T = 1")).map(c=>c.getClientRects().length)}});
 console.log(n,JSON.stringify(g));
 await pg.screenshot({path:out+"/"+n+".png"});await pg.close();}
await br.close();
