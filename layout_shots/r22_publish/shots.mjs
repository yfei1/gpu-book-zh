import { chromium } from "/Users/yufanfei/tock-sniper/node_modules/playwright-core/index.mjs";
import { mkdirSync, rmSync } from "node:fs";
const out=process.argv[2]; const TMP=out+"/_t"; mkdirSync(TMP,{recursive:true});
process.on("exit",()=>rmSync(TMP,{recursive:true,force:true}));
const br=await chromium.launch({executablePath:"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",env:{...process.env,TMPDIR:TMP+"/",MAC_CHROMIUM_TMPDIR:TMP}});
const V=[["w1720_dy1_top",1720,860,"",0],["w1440_ch04",1440,900,"ch04",0],["w1920_ch07",1920,1080,"ch07",0],["w900_top_open",900,900,"",1],["w390_dy1_s5_open",390,844,"ch00_0-5",1]];
for(const [n,w,h,hs,op] of V){const pg=await br.newPage({viewport:{width:w,height:h}});
 const e=[];pg.on("pageerror",x=>e.push(x.message));
 await pg.goto("http://localhost:8765/index.html"+(hs?"#"+hs:""),{waitUntil:"load"});await pg.waitForTimeout(1500);
 if(hs)await pg.evaluate(i=>document.getElementById(i).scrollIntoView(),hs);
 if(n=="w1720_dy1_top")await pg.evaluate(()=>{const f=document.querySelector("iframe[title^='图 导一-1']");f.scrollIntoView({block:"center"})});
 if(op){await pg.click("#toc-btn");await pg.waitForTimeout(400)}
 await pg.waitForTimeout(800);
 const g=await pg.evaluate(()=>{const f=document.querySelector("iframe[title^='图 导一-1']");const r=f&&f.getBoundingClientRect();let sc=null;try{const d=f.contentDocument.documentElement;sc=[d.scrollHeight,d.clientHeight,d.scrollWidth,d.clientWidth]}catch(_){}
 return {sw:document.documentElement.scrollWidth,iw:innerWidth,font:[document.fonts.check("16px 'Google Sans'"),document.fonts.check("16px 'Noto Sans SC'")],body:getComputedStyle(document.body).fontFamily.slice(0,60),fr:r&&[r.width,r.height],ifr:sc}});
 console.log(n,JSON.stringify(g),e.join("|"));
 await pg.screenshot({path:out+"/"+n+".png"});await pg.close()}
await br.close();