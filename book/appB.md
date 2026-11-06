# 附录 B：Hopper（`sm_90a`）`CUDA C++ → PTX → SASS` 速查表

**本书地图：** 前言 → 第 0.0 章 → 第 0 章 → 第 0.5 章 → 第 1 章 [第 0 级] → 第 2 章 [第 1 级] → 第 3 章 [第 2 级] → 第 4 章 [第 3 级] → 第 5 章 [第 4 级] → 第 6 章 [第 5 级] → 第 7–9 章 → 第 10 章 [性能诊断法] → 附录 A → **【附录 B：`CUDA C++ → PTX → SASS` 速查表】**

附录 A 末尾问到：在反汇编或剖析器里看到不认识的 SASS 指令时，怎样查？这一页就是答案。

---

## 1. 怎样拆读一条 SASS 指令与三类反直觉编译结果

<!-- FIG appB-a: 图 B-1 上方画 CUDA C++ 源码经前端生成 PTX、再由 ptxas 编译成 128 位 SASS 指令字的降低流水线（移动块对应 LDG.E.EF.128 R8, desc[UR12][R8.64] 的各个操作码后缀与寄存器字段），下方点击十个反直觉案例可展开 1 条 PTX 映射为 0 条或多条 SASS 的指令流对比。 -->

我们平时写的是 CUDA C++ 或内联 PTX，但 GPU 硬件真正执行的是后端编译器 `ptxas` 生成的 128 位 SASS 机器指令（见第 6 章第 1 节）。如图 B-1 所示，从源码到机器码有三层：CUDA C++、PTX 和 SASS。

先看怎么拆读一条典型的 SASS 指令。拿第 3 章的 16 字节流式全局读取指令 `LDG.E.EF.128 R8, desc[UR12][R8.64]` 来说，PTX 里的修饰符会按固定位置变成 SASS 助记符的后缀和操作数：
- `LDG` 是全局内存读取操作码；
- `.E` 表示使用 64 位扩展地址；
- `.EF` 是本 SM 的 L1 优先淘汰提示（`evict_first`，只管 L1）；
- `.128` 表示每个线程一次读取 128 位（16 字节，装进 `R8..R11` 四个连续的 32 位向量寄存器）；
- 操作数里的 `desc[UR12]` 放在 **uniform register**（统一寄存器，见第 4 章，写作 `UR`）里，保存 64 位内存描述符（每条全局访存指令都带 `desc[URn]` 操作数；第 2 章用 `createpolicy` 生成的 L2 留存提示就编码在这个描述符里，不占指令后缀）；
- 末尾的 `[R8.64]` 则是由 `R8:R9` 寄存器对拼出来的 64 位字节地址。

反汇编里最容易让人困惑的是：**一条 PTX 指令不一定变成一条同名的 SASS 指令。** 它可能变成 0 条，可能被拆成好几条，也可能改了名字。按变化方式分三类看（各条指令的完整映射见第 2–5 节速查表对应项）：

第一类是**一条 PTX 在 SASS 里没有独立指令，或者被改成了位操作与无返回指令**。比如 `wgmma.commit_group` 没有独立指令，而是直接编码成这一批最后一条 `HGMMA` 或 `QGMMA` 指令末尾的 `gsb0` 组标志位（见第 64 项）。跨 CTA 映射地址的 `mapa` 在 `sm_90a` 上也没有独立操作码，而是由普通算术指令拼好地址，配合特殊寄存器读取指令 `S2R`（读取本 CTA 在集群内的编号 `%cluster_ctarank`）和通用地址读取 `LD.E` 来完成（见第 55、56 项）。把 BF16 升宽成 FP32 的 `cvt.f32.bf16`，因为 BF16 正好是 FP32 的高 16 位，`ptxas` 直接生成 1 条字节重排 `PRMT`（或移位指令）走 16 通道 ALU 管线，不走 4 通道 SFU 管线（见第 21 项）。此外，对于全局 `atomicAdd`，只要代码里不用返回值，编译器就会发出只发不等的全局归约 `REDG`；在共享内存里对常数 1 递增时，则会编译成单条投票递增指令 `ATOMS.POPC.INC.32`（见第 80–82 项）。

第二类是**一条 PTX 被 `ptxas` 拆成了一串指令**。比如单 warp 的 `HMMA` 没有原生 FP8 硬件指令，写单 warp 的 FP8 矩阵乘（`mma.sync ... e4m3`）时，`ptxas` 只能先用 `F2FP.F16.E4M3.UNPACK_B` 把 FP8 解包成 FP16，再发 **2** 条 `HMMA.16816.F32`（见第 60、62 项）。双元素半精度快速指数 `ex2.approx.f16x2` 和 `ex2.approx.ftz.bf16x2` 会被拆成 **2** 条标量 `MUFU.EX2` 加 1 条 `PRMT`，SFU 周期和两条标量指令一样多；而且单精度 `ex2.approx.f32` 如果漏写了 `.ftz`（flush to zero，把阶码全为 0、比最小正常浮点数还小的**非规格化数**直接当 0 处理），还会被外包上 `FSETP + FMUL` 修正指令（见第 6、89 项）。默认的单精度除法 `a / b`（`div.rn.f32`）会展开成 `MUFU.RCP`、牛顿迭代 `FFMA`、范围检查 `FCHK` 和慢速分支 `BRA`，而快速倒数 `rcp.approx.ftz.f32` 只要 1 条 `MUFU.RCP`（见第 4、5、7 项）。在内存同步上，PTX 规范只保证内存可见性顺序，不规定具体的 SASS 指令序列；在 `sm_90a` 反汇编观察中，1 条全卡内存栅栏 `__threadfence()` 展开成 **5** 条指令（`MEMBAR.ALL.CTA + MEMBAR.SC.GPU + ERRBAR + CGAERRBAR + CCTL.IVALL`），`ld.acquire.gpu`、`red.release.gpu` 和默认的 `cluster.sync()` 也会展开出全卡栅栏或 L1 失效指令——它们的真实性能代价是等待前序写操作被 L2 确认或让本 SM 的 L1 失效的延迟，而不只是多出来的几条指令字（见第 58、79、83 项）。

第三类是**助记符在 SASS 里改了名字，或者未出现在公开操作码简表里**。全局读取的缓存修饰符在 SASS 里都变成了后缀：绕过 L1 的 `__ldcg` 变成 `LDG.E.STRONG.GPU`，流式读取 `__ldcs` 变成 `LDG.E.EF`，只读缓存 `__ldg` 变成 `LDG.E.CONSTANT`，`createpolicy` 的 L2 策略则装进 `desc[URn]` 操作数（见第 30–33 项）。另外，走 ALU 管线的双值打包转换 **`F2FP`** 和 `cp.async` 向 `mbarrier` 报到的 **`ARRIVES`** 是反汇编里高频出现的真实指令，但公开操作码简表并未列出（见第 20、23、24、41 项）。

---

## 2. 算术、超越函数与类型转换速查表（第 1–28 项）

查这一组指令时，先看它走每个 SMSP 的哪条执行管线：FMA 有 32 条通道，ALU 有 16 条，SFU 只有 4 条。表的倒数第二列写的是这条指令所在的硬件单元和它会卡在第几级。

| 序号 | 操作类别 | CUDA C++ 写法 | PTX 指令 | SASS 助记符（`sm_90a`） | 硬件单元与代价层级 | 编译说明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | FP32 融合乘加 | `fmaf(a,b,c)`；`__fmaf_rn`；`a*b+c`（默认收缩） | `fma.rn.f32`（`mad.f32` 同） | `FFMA` | FMA 管线（32 通道，发射间隔 1 周期）· 第 4 级 | 1 对 1 |
| 2 | FP32 加法与乘法 | `a+b`；`a*b`；`__fadd_rn`；`__fmul_rn` | `add.f32`；`mul.f32` | `FADD`、`FMUL` | FMA 管线 · 第 4 级 | `__fadd_rn` / `__fmul_rn` 可阻止编译器将 `a*b+c` 收缩为 `FFMA` |
| 3 | FP32 极值、选择与比较 | `fminf`；`fmaxf`；`cond?a:b`；`a<b` | `min.f32`；`max.f32`；`selp.f32`；`setp.lt.f32` | `FMNMX`、`FSEL`、`FSETP` | ALU 管线 · 第 4 级 | `FMNMX` 靠谓词选择取最小值或最大值；`setp` 写入谓词寄存器 `P0..P6` |
| 4 | FP32 快速除法 | `__fdividef(a,b)`；开启快速数学编译选项 `-use_fast_math` 时的 `a/b` | `div.full.f32`；`div.approx.f32` | `MUFU.RCP`、`FMUL` | SFU 管线 + FMA 管线 · 第 4 级 | 1 条 PTX 展开为倒数近似 `MUFU.RCP` 加乘法 `FMUL` |
| 5 | FP32 标准 IEEE 除法与开方 | 默认 `a/b`；`sqrtf(x)` | `div.rn.f32`；`sqrt.rn.f32` | `MUFU.RCP`、`FCHK`、`FFMA`、`BRA` | SFU + FMA + 分支单元 · 第 4 级 | 含牛顿迭代 `FFMA` 与浮点范围检查 `FCHK`，越界时分支跳转到慢速修正路径 |
| 6 | FP32 指数运算 | `exp2f(x)`；`__expf(x)`；内联 `ex2.approx.ftz.f32` | `ex2.approx.f32`；`ex2.approx.ftz.f32` | `MUFU.EX2`、`FMUL`、`FSETP` | SFU 管线（4 通道，发射间隔 8 周期）· 第 4 级 | 带 `.ftz` 编译为裸的 1 条 `MUFU.EX2`；不带 `.ftz` 会外包 `FSETP + FMUL` 修正 |
| 7 | FP32 倒数、平方根倒数、对数与三角函数 | `rcp.approx`；`rsqrtf(x)`；`__log2f(x)`；`__sinf`；`__cosf` | `rcp/rsqrt/lg2/sin/cos.approx.ftz.f32` | `MUFU.RCP`、`MUFU.RSQ`、`MUFU.LG2`、`MUFU.SIN`、`MUFU.COS` | SFU 管线 · 第 4 级 | `SIN/COS` 前置 1 条范围归约 `FMUL`；仅 `.approx` 形态为单条 `MUFU` |
| 8 | FP32 硬件双曲正切 | 内联 `tanh.approx.f32`（标准库 `tanhf` 为软件展开） | `tanh.approx.f32` | `MUFU.TANH` | SFU 管线 · 第 4 级 | 1 对 1，最大相对误差 `2^-11` |
| 9 | 双半精度打包算术（FP16x2 / BF16x2） | `__hadd2`；`__hmul2`；`__hfma2`（`__half2` 或 `__nv_bfloat162`） | `add/mul/fma.rn.f16x2`；`add/mul/fma.rn.bf16x2` | `HADD2`、`HMUL2`、`HFMA2` | FMA 管线 · 第 4 级 | BF16 打包指令带 `.BF16_V2` 后缀，`HMUL2.BF16_V2` 发射间隔约 2 周期 |
| 10 | 双半精度打包极值 | `__hmax2`；`__hmin2` | `max/min.f16x2`；`max/min.bf16x2` | `HMNMX2` | ALU / FMA 管线· 第 4 级 | 单条指令同时求一对半精度数的极值 |
| 11 | 整数乘加与地址计算 | `a*b+c`（整数）；`__mul24`；指针偏移 `ptr + i*size` | `mad.lo.s32/u32`；`mad.wide.u32`；`mul.hi.u32` | `IMAD`、`IADD3`、`LEA` | `IMAD` 走 FMA 管线；`IADD3/LEA` 走 ALU 管线 · 第 4 级 | `IMAD` 兼具寄存器搬运（`IMAD.MOV`）、左移（`IMAD.SHL`）与 64 位宽乘加（`IMAD.WIDE`） |
| 12 | 整数加减与三输入加法 | `a+b+c`；`a+b`（整数） | `add.s32/u32`；`sub.s32`；`add.s64` | `IADD3`、`VIADD` | ALU 管线（16 通道，发射间隔 2 周期）· 第 4 级 | `sm_90a` 用三输入 `IADD3` 与双输入 `VIADD`；64 位加法拆为 `IADD3 + IADD3.X` |
| 13 | 三输入按位逻辑 | `a&b`；`a\|b`；`a^b`；`~a`；内联 `lop3.b32` | `and/or/xor/not.b32`；`lop3.b32 d,a,b,c,immLut` | `LOP3` | ALU 管线 · 第 4 级 | `ptxas` 将任意 1–3 输入按位逻辑表达式折叠为 1 条 `LOP3.LUT`（真值表编码在 8 位立即数中） |
| 14 | 移位、漏斗移位与循环移位 | `a<<n`；`a>>n`；`__funnelshift_l/r` | `shl/shr.b32`；`shf.l.wrap.b32`；`shf.r.clamp.b32` | `SHF`、`IMAD.SHL.U32`、`USHF` | ALU 管线（或 FMA 管线）· 第 4 级 | 常数左移可由编译器分配为 `SHF`（走 ALU）或 `IMAD.SHL.U32`（走 FMA 管线） |
| 15 | 字节重排 | `__byte_perm(x,y,sel)` | `prmt.b32 d,a,b,sel` | `PRMT` | ALU 管线 · 第 4 级 | 从两个源寄存器的 8 个字节中按 4 位选择器挑出 4 个字节拼入目标寄存器 |
| 16 | 位计数、位反转、前导一与位域提取 | `__popc`；`__brev`；`__clz`；`__ffs`；内联 `bfe/bfi` | `popc.b32`；`brev.b32`；`bfind`；`bfe.u32`；`bfi.b32` | `POPC`、`BREV`、`FLO`、`SGXT`、`LOP3` | ALU / SFU 管线· 第 4 级 | `bfe.u32` 可编译为 `SGXT.U32` 或 `SHF + LOP3` |
| 17 | 整数极值、绝对值、比较与选择 | `min/max`；`abs`；`a<b`；`?:` | `min/max.s32`；`abs.s32`；`setp.lt.s32`；`selp.b32` | `VIMNMX`、`IABS`、`ISETP`、`SEL` | ALU 管线 · 第 4 级 | 1 对 1 走整数 ALU 管线 |
| 18 | 4 路 8 位整数点积 | `__dp4a(a,b,c)`；`__dp2a_lo` | `dp4a.s32.s32`；`dp2a` | `IDP` | FMA 管线· 第 4 级 | 对应 `IDP`（推断） |
| 19 | 单值 FP32 转 BF16 | `__float2bfloat16(x)`；`static_cast<__nv_bfloat16>(f)` | `cvt.rn.bf16.f32` | `F2F.BF16.F32` | SFU 管线（标量转换）· 第 4 级 | 单值转换在反汇编中观察为标量 `F2F.BF16.F32`（走 4 通道 SFU）；若两个值打包进同一 32 位寄存器，可改用下一项的 `F2FP` |
| 20 | 双值 FP32 打包转 BF16x2 / FP16x2 | `__floats2bfloat162_rn(a,b)`；`__floats2half2_rn(a,b)` | `cvt.rn.bf16x2.f32 d,a,b`；`cvt.rn.f16x2.f32 d,a,b` | `F2FP.BF16.F32.PACK_AB`、`F2FP.F16.F32.PACK_AB` | ALU 管线 · 第 4 级 | 1 条指令把两个 FP32 舍入打包进 1 个 32 位寄存器，走 16 通道 ALU 管线（公开操作码简表未列出） |
| 21 | BF16 升宽为 FP32 | `__bfloat162float(h)`；`__bfloat1622float2` | `cvt.f32.bf16` | `PRMT`、`IMAD.U32`、`SHF.L.U32` | ALU 管线 · 第 4 级 | BF16 即 FP32 的高 16 位，编译为字节重排 `PRMT R0,RZ,0x7610,R0` 或移位 |
| 22 | FP16 与 FP32 / BF16 互转 | `__half2float(h)`；`__float2half(f)` | `cvt.f32.f16`；`cvt.rn.f16.f32`；`cvt.bf16.f16` | `HADD2.F32`、`F2FP.F16.F32.PACK_AB`、`F2F.BF16.F16` | FMA / ALU / SFU 管线 · 第 4 级 | `f16 -> f32` 编译为与 0 相加的 `HADD2.F32`（走 FMA 管线） |
| 23 | 双值 FP32 饱和打包转 FP8（E4M3 / E5M2） | `__nv_cvt_float2_to_fp8x2(f2, __NV_SATFINITE, __NV_E4M3)` | `cvt.rn.satfinite.e4m3x2.f32 d16,a,b` | `F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C` | ALU 管线· 第 4 级 | 两个 FP32 打包为 16 位 FP8 对并保留目标寄存器另一半 |
| 24 | 双值 FP8（E4M3）解包转 FP16x2 | `__nv_cvt_fp8x2_to_halfraw2(x, __NV_E4M3)`；内联 `cvt.rn.f16x2.e4m3x2` | `cvt.rn.f16x2.e4m3x2 d32,a16` | `F2FP.F16.E4M3.UNPACK_B` | ALU 管线· 第 4 级 | 把 2 个 FP8 字节解包成 `FP16x2` |
| 25 | FP16x2 饱和打包转 FP8 | 内联 `cvt.rn.satfinite.e4m3x2.f16x2` | `cvt.rn.satfinite.e4m3x2.f16x2` | `F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C`、`F2F` | ALU / SFU 管线· 第 4 级 | 按同族规则对应 `F2FP` / `F2F`（推断） |
| 26 | 32 位整数与 FP32 互转及取整 | `(float)i`；`(int)f`；`floorf`；`truncf`；`rintf` | `cvt.rn.f32.s32`；`cvt.rzi.s32.f32`；`cvt.rmi/rzi/rni.f32.f32` | `I2FP.F32.S32`、`I2FP.F32.U32`、`F2I.TRUNC.NTZ`、`FRND.FLOOR`、`FRND.TRUNC` | `I2FP` 走 ALU；`F2I/FRND` 走 SFU · 第 4 级 | 32 位整数转 FP32 用 `I2FP`；浮点取整用 `FRND` |
| 27 | FP64 与 FP32 互转、64 位整数转浮点 | `(double)f`；`(float)d`；`(float)ll` | `cvt.f64.f32`；`cvt.rn.f32.f64`；`cvt.rn.f32.s64` | `F2F.F64.F32`、`F2F.F32.F64`、`I2F.S64` | SFU 管线· 第 4 级 | 1 对 1 |
| 28 | 整数位宽扩展与截断 | `(long)i`；`(unsigned)u64`；`(short)i` | `cvt.u64.u32`；`cvt.s64.s32`；`cvt.u32.u16`；`cvt.s16.s8` | `MOV`、`SGXT`、`LOP3`、`PRMT`、`IMAD.MOV.U32` | ALU 管线 · 第 4 级 | 无符号升 64 位常直接将高 32 位记为 `RZ`（零指令）；有符号扩展用 `SGXT` |

---

## 3. 全局、片上访存与异步拷贝速查表（第 29–49 项）

查访存与异步拷贝指令时，重点是分清数据经过哪条硬件通路。常见的三条通路分别是：经过私有寄存器的普通 `LDG / STG`、由每个线程发指令但绕过寄存器直写 SMEM 的 `LDGSTS`（`cp.async`），以及由单个代表线程发起专用硬件搬运的 `UTMALDG / UTMASTG`（TMA）。

| 序号 | 操作类别 | CUDA C++ 写法 | PTX 指令 | SASS 助记符（`sm_90a`） | 硬件单元与代价层级 | 编译说明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 29 | 普通全局内存读写（标量与向量） | `*p`；`p[i]`；`reinterpret_cast<uint4*>(p)[i]`（16 字节） | `ld.global.b32/v4.b32/b64`；`st.global.v4.b32/b8/b16` | `LDG.E`、`LDG.E.64`、`LDG.E.128`、`LDG.E.U16`、`STG.E`、`STG.E.64`、`STG.E.128` | LSU → L1 → L2 · 第 2 级 | 位宽直接体现为后缀（`.64/.128/.U16`），均带 `desc[URn]` 内存描述符操作数；若 16 字节向量只用其中几个分量，`ptxas` 会拆成标量 `LDG.E` |
| 30 | 只读非一致全局读取（`__ldg`） | `__ldg(p)`；`const __restrict__ T* p`；内联 `ld.global.nc` | `ld.global.nc.u32`；`ld.global.nc.v4.f32` | `LDG.E.CONSTANT`、`LDG.E.128.CONSTANT`、`LDG.E.64.CONSTANT` | LSU → L1 只读路径 → L2 · 第 2 级 | `.nc` 编译为 `.CONSTANT` 修饰符；对本 kernel 运行期间会被其他 CTA 改写的地址使用属未定义行为 |
| 31 | 绕过 L1 的全局读写（`__ldcg / __stcg`） | `__ldcg(p)`；`__stcg(p,v)`；内联 `ld/st.global.cg` | `ld.global.cg.v4.b32`；`st.global.cg.f32` | `LDG.E.STRONG.GPU`、`STG.E.STRONG.GPU` | LSU → L2（绕过 L1）· 第 2 级 | `.cg` 编译为 `.STRONG.GPU`（与全卡作用域的宽松原子读写同指令）；只适合轮询标志本身，读到标志后再读数据必须用 `ld.acquire.gpu` 或加获取栅栏（第 83 项），否则可能从本 SM 的 L1 读到旧数据 |
| 32 | 流式优先淘汰全局读取（`__ldcs`） | `__ldcs(p)`；内联 `ld.global.cs` | `ld.global.cs.v4.b32` | `LDG.E.EF`、`LDG.E.EF.128`、`LDG.E.EF.64` | LSU → L1/L2（优先淘汰）· 第 2 级 | `.cs` 编译为 `.EF`（`evict_first`）修饰符 |
| 33 | 带 `createpolicy` 的 L1/L2 留存提示加载 | 内联 `createpolicy.fractional.L2::evict_first.b64` 加 `ld.global.L1::evict_first.L2::cache_hint` | `createpolicy.fractional.L2::evict_first\|evict_last.b64 pol,1.0`；`ld.global...L2::cache_hint` | `UMOV`、`LDG.E.EF`、`STG.E.EL`、`LDG.E` | LSU（策略存于统一寄存器）· 第 2 级 | L1 提示变成 `.EF/.EL` 后缀；L2 策略编码在 `desc[URn]` 操作数里传给硬件 |
| 34 | 预取到 L2 缓存 | `__builtin_prefetch`；内联 `prefetch.global.L2` | `prefetch.global.L2 [a]`；`prefetch.global.L1` | `CCTL.E.PF2` | L2 缓存控制 · 第 2 级 | 1 对 1 生成缓存控制预取指令 `CCTL.E.PF2` |
| 35 | 局部内存读写（寄存器溢出、动态下标数组或未内联调用栈帧） | 动态下标局部数组；寄存器溢出（`ptxas -v` 报告 `spill`）；未加 `__forceinline__` 的设备函数调用栈帧 | `ld.local`；`st.local` | `LDL`、`LDL.LU`、`STL` | LSU → L1 → L2（位于全局显存）· 第 2 级 | `.LU`（最后一次使用）在读出后释放缓存行；出现 `LDL/STL` 代表寄存器溢出或非内联函数调用栈帧（加 `__forceinline__` 可消去栈帧往返） |
| 36 | 内核参数与常量内存读取 | kernel 形参；`__constant__` 变量 | `ld.param.*`；`ld.const` | `LDC`、`ULDC` | SM 常量缓存 · 第 2 级 | 形参存于常量体 `c[0x0][0x210..]`；`ULDC` 直接把整束相同的常量读入统一寄存器 `UR` |
| 37 | 通用地址空间读写（`cvta`） | 编译器无法静态区分全局或共享空间的指针；`cluster.map_shared_rank` 返回的远端指针 | `ld.b32`；`st.b32`；`cvta.shared.u64`；`ld.shared::cluster` | `LD`、`ST` | LSU（运行时硬件解码地址窗口）· 第 2 级 | 通用 `LD.E / ST.E` 需在运行时判断地址空间；跨 CTA 读取远端共享内存也编译为 `LD.E` |
| 38 | SMEM 普通读写 | `extern __shared__ T s[]`；`s[i]`；`float4` 向量访问 | `ld.shared.b32/v4.b32`；`st.shared::cta.v4.b32` | `LDS`、`LDS.64`、`LDS.128`、`LDS.U8`、`LDS.U16`、`STS`、`STS.64`、`STS.128` | LSU → SMEM（32 个 4 字节 bank）· 第 2 级 | 1 对 1 带位宽后缀；整束 `LDS.128` 共读 512 字节（分 4 个波面请求 32 个 bank） |
| 39 | 逐线程异步全局到共享拷贝（`cp.async`） | `__pipeline_memcpy_async(dst,src,16)`；`cuda::memcpy_async`；内联 `cp.async.cg/ca` | `cp.async.cg.shared.global [dst],[src],16{,src-size}`；`cp.async.ca...4\|8\|16` | `LDGSTS.E.BYPASS.128`、`LDGSTS.E.BYPASS.128.ZFILL`、`LDGSTS.E`、`LDGSTS.E.64` | LSU（L2 直写 SMEM，不经私有寄存器）· 第 2 级 | `.cg`（仅 16 字节）编译为绕过 L1 的 `.BYPASS.128`；带 `src-size` 越界填零时生成 `.ZFILL` |
| 40 | `cp.async` 提交与按组等待 | `__pipeline_commit()`；`__pipeline_wait_prior(N)`；`cp_async_wait<N>()` | `cp.async.commit_group`；`cp.async.wait_group N`；`cp.async.wait_all` | `LDGDEPBAR`、`DEPBAR.LE` | LSU 记分牌（`SB0`）· 第 3 级 | `commit_group` 编译为 `LDGDEPBAR`；`wait_group N` 编译为 `DEPBAR.LE SB0, N`（跨线程读取前仍需块内屏障） |
| 41 | `cp.async` 向 `mbarrier` 报到 | `cuda::memcpy_async(..., bar)`；`cuda::ptx::cp_async_mbarrier_arrive_noinc` | `cp.async.mbarrier.arrive.noinc.shared.b64 [bar]` | `ARRIVES.LDGSTSBAR.64.ARVCNT` | LSU + `mbarrier` 单元 · 第 3 级 | 本线程此前发出的 `cp.async` 全部落定后自动触发屏障报到（公开操作码简表未列出） |
| 42 | TMA 多维张量分块加载（全局到共享） | `cuda::ptx::cp_async_bulk_tensor(space_cluster, space_global, ...)`（CUTLASS 中的对应写法：`SM90_TMA_LOAD`） | `cp.async.bulk.tensor.{1..5}d.shared::cluster.global.mbarrier::complete_tx::bytes [dst],[tmap,{c0..}],[mbar]` | `UTMALDG.2D`、`UTMALDG.3D`、`UTMALDG.5D` | SM 内专用 TMA 单元 · 第 2 级 | 1 对 1，通常由 `ELECT` 选出的 1 个线程发出，占 0 个数据寄存器 |
| 43 | TMA 集群多播分块加载 | `cuda::ptx::cp_async_bulk_tensor(..., ctaMask)`（CUTLASS 中的对应写法：`SM90_TMA_LOAD_MULTICAST`） | `cp.async.bulk.tensor.2d.shared::cluster.global.mbarrier::complete_tx::bytes.multicast::cluster ... ctaMask` | `UTMALDG.2D.MULTICAST` | TMA 单元 + 集群互连网络 · 第 1 级 | 读 1 次 L2，同时写入 `ctaMask` 掩码内各目标 CTA 的相同 SMEM 偏移并各自触发 `complete_tx` |
| 44 | TMA 多维张量分块写回（共享到全局） | 内联 PTX（CUTLASS 中的对应写法：`SM90_TMA_STORE`、`cute::tma_store_arrive`、`cute::tma_store_wait<Count>`） | `cp.async.bulk.tensor.2d.global.shared::cta.bulk_group`；`cp.async.bulk.commit_group`；`cp.async.bulk.wait_group{.read}` | `UTMASTG.2D`、`UTMASTG.3D`、`UTMACMDFLUSH`、`DEPBAR.LE` | TMA 单元 · 第 2 级 | 发起写回前需先执行 `fence.proxy.async.shared::cta`（第 54 项）；`commit_group` 编译为 `UTMACMDFLUSH`，`tma_store_wait` 发出带 `.read` 的 `wait_group.read` |
| 45 | TMA 多维张量分块原子累加写回 | `cuda::ptx::cp_reduce_async_bulk_tensor`（CUTLASS 中的对应写法：`SM90_TMA_REDUCE_ADD`） | `cp.reduce.async.bulk.tensor.2d.global.shared::cta.add.bulk_group [tmap,{..}],[src]` | `UTMAREDG.2D.ADD`、`UTMAREDG.3D.ADD` | TMA 单元 + L2 原子归约单元 · 第 1 级 | 把 SMEM 分块直接发往 L2 做硬件原子加法，无需在 SM 内读回旧值 |
| 46 | TMA 一维连续字节流拷贝与归约 | `cuda::ptx::cp_async_bulk`；`cp_reduce_async_bulk`（CUTLASS 中的对应写法：`SM90_BULK_COPY_G2S`） | `cp.async.bulk.shared::cluster.global.mbarrier::complete_tx::bytes [dst],[src],size,[mbar]` | `UBLKCP.S.G`、`UBLKCP.S.S`、`UBLKRED.G.S.ADD.BF16.RN` | TMA 单元（免描述符路径）· 第 2 级 | 要求地址与字节数按 16 字节对齐；`S.G` 表示全局到共享，`S.S` 表示跨 CTA 共享拷贝 |
| 47 | TMA 一维与张量分块预取至 L2 | `cuda::ptx::cp_async_bulk_prefetch`；`cp.async.bulk.prefetch.tensor` | `cp.async.bulk.prefetch.L2.global [a],size`；`cp.async.bulk.prefetch.tensor.2d.L2.global` | `UBLKPF.L2`、`UTMAPF.L2.2D` | TMA 单元 → L2 · 第 1 级 | 后台把分块拉入 L2 而不写 SMEM |
| 48 | TMA 张量描述符动态更新与栅栏 | `cuda::ptx::tensormap_replace`；`tensormap_cp_fenceproxy` | `tensormap.cp_fenceproxy.global.shared::cta.tensormap::generic.release.gpu.sync.aligned` | `UTMACCTL.PF`、`UTMACCTL.IV` | TMA 控制单元 · 第 2 级 | `UTMACCTL.IV` 使 TMA 缓存的旧描述符失效，`.PF` 预取新描述符 |
| 49 | 从线程束选出 1 个代表线程 | `cuda::ptx::elect_sync`（CUTLASS 中的对应写法：`cute::elect_one_sync()`） | `elect.sync d\|p, membermask` | `ELECT` | SMSP 统一数据通路 · 第 3 级 | 从活跃线程掩码中由硬件选出 1 个代表线程去发射 TMA 或 `mbarrier` 指令 |

---

## 4. 片上屏障、集群共享内存与 Tensor Core 速查表（第 50–70 项）

这一组是 Hopper 异步流水的核心指令。生产者靠 `mbarrier`（`SYNCS`）和 **DSMEM**（分布式共享内存，见第 3 章与第 7 章）把数据搬进片上；消费者则靠 `HGMMA / QGMMA` 驱动全 SM 的 4 个 Tensor Core，再配合 `USETMAXREG` 动态借还寄存器、配合 `ACQBULK / PREEXIT` 衔接前后内核（PDL）。

| 序号 | 操作类别 | CUDA C++ 写法 | PTX 指令 | SASS 助记符（`sm_90a`） | 硬件单元与代价层级 | 编译说明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 50 | `mbarrier` 初始化与失效 | `cuda::barrier<thread_scope_block>`；`init(&bar, count)`；`cuda::ptx::mbarrier_init` | `mbarrier.init.shared::cta.b64 [addr], count`；`mbarrier.inval.shared::cta.b64 [addr]` | `SYNCS.EXCH.64`、`SYNCS.CCTL.IV` | SM 同步单元（`SYNCS`）· 第 2 级 | `init` 编译为 `SYNCS.EXCH.64`（写入 64 位屏障字）；`inval` 编译为 `SYNCS.CCTL.IV` |
| 51 | `mbarrier` 报到与登记期望字节数 | `bar.arrive()`；`cuda::ptx::mbarrier_arrive`；`mbarrier_arrive_expect_tx` | `mbarrier.arrive.shared::cta.b64`；`mbarrier.arrive.expect_tx.shared::cta.b64 state,[addr],txcount` | `SYNCS.ARRIVE.TRANS64`、`SYNCS.ARRIVE.TRANS64.A1T0` | `SYNCS` 单元 · 第 2 级 | 普通报到带 `.A1T0`（报到计数加 1，期望字节 0）；登记 TMA 字节数用带寄存器操作数的 `.TRANS64` |
| 52 | `mbarrier` 相位等待与轮询 | `bar.wait(...)`；`cuda::ptx::mbarrier_try_wait_parity` | `mbarrier.try_wait.parity.shared::cta.b64 p,[addr],phase`；`mbarrier.test_wait` | `SYNCS.PHASECHK.TRANS64.TRYWAIT`、`SYNCS.PHASECHK.TRANS64` | `SYNCS` 单元 · 第 3 级 | `try_wait` 编译为 `.TRYWAIT`，在硬件中休眠等待直到相位位翻转或超时，未翻转时由 `@!P BRA` 重试 |
| 53 | 向同集群远端 CTA 的 `mbarrier` 报到 | `cuda::ptx::mbarrier_arrive(sem_release, scope_cluster, space_cluster, addr)`（CUTLASS 中的对应写法：`cutlass::arch::ClusterBarrier::arrive`） | `mapa.shared::cluster.u32 ra,addr,cta`；`mbarrier.arrive{.release.cluster}.shared::cluster.b64 _,[ra]` | `SYNCS.ARRIVE.TRANS64.RED.A1T0`、`R2UR` | `SYNCS` 单元 + 集群互连网络 · 第 1 级 | `.RED` 后缀代表无返回值的远端跨块报到（`ClusterBarrier::arrive` 使用默认的 `mbarrier.arrive.shared::cluster.b64`，未显式拼写 `.release.cluster`） |
| 54 | `mbarrier` 初始化与异步代理可见性栅栏 | `cuda::ptx::fence_mbarrier_init`；`fence_proxy_async`（CUTLASS 中的对应写法：`fence_view_async_shared`） | `fence.mbarrier_init.release.cluster`；`fence.proxy.async.shared::cta`（或 `.global`） | `FENCE`、`FENCE.VIEW.ASYNC.S`、`FENCE.VIEW.ASYNC.G`、`MEMBAR.ALL.CTA` | LSU / 内存管线 · 第 3 级 | 普通线程写完 SMEM 后，必须执行 `FENCE.VIEW.ASYNC.S` 才能让 TMA 或 `wgmma` 看到新数据 |
| 55 | DSMEM 远端地址映射 | `cluster.map_shared_rank(ptr, rank)`；`cuda::ptx::mapa`；`cluster.block_rank()` | `mapa.shared::cluster.u32 d,a,cta`；`getctarank`；`mov.u32 %cluster_ctarank` | `R2UR`、`S2R`、`S2UR`、`LEA` | ALU / 统一数据通路 · 第 1 级 | `mapa` 在 `sm_90a` 上无独立操作码：由普通算术指令把目标块号拼进地址高位，再用 `R2UR` 装入统一寄存器 |
| 56 | DSMEM 跨 CTA 读写与原子操作 | `*cluster.map_shared_rank(p, r)`；内联 `ld/st/atom.shared::cluster` | `ld.shared::cluster.v4.b32 [a]`；`st.shared::cluster`；`atom.shared::cluster.add` | `LD.E.128`、`ST.E`、`ATOM` | LSU 通用地址路径 → 集群互连网络 · 第 1 级 | 远端读取编译为通用 `LD.E`（而非本块 `LDS`）；读取前须用集群屏障保证远端 SMEM 已就绪 |
| 57 | DSMEM 跨 CTA 异步写并扣减远端屏障（`st.async`） | `cuda::ptx::st_async`；`cluster.map_shared_rank + st.async` | `st.async.shared::cluster.mbarrier::complete_tx::bytes.v4.f32 [ra],{..},[mbar]` | `STAS`、`STAS.128`、`STAS.64` | 集群互连网络 + 远端 `mbarrier` · 第 1 级 | 1 对 1，数据写入远端 CTA 的 SMEM 后自动扣减远端 `mbarrier` 的期望字节数 |
| 58 | 集群同步屏障（`cluster.sync`） | `cooperative_groups::this_cluster().sync()`（CUTLASS 中的对应写法：`cute::cluster_sync()`） | `barrier.cluster.arrive{.relaxed\|.release}.aligned`；`barrier.cluster.wait{.acquire}.aligned` | `UCGABAR_ARV`、`UCGABAR_WAIT`、`MEMBAR.ALL.GPU`、`ERRBAR`、`CGAERRBAR`、`CCTL.IVALL` | 集群屏障单元 · 第 1 级 | 默认 `cluster.sync()` 附带 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR + CCTL.IVALL`（等待前序写被 L2 确认并使本 SM 的 L1 失效）；使用 `.relaxed` 可省掉全卡栅栏 |
| 59 | 单 warp 同步 Tensor Core 矩阵乘（FP16 / BF16） | `nvcuda::wmma::mma_sync`；内联 `mma.sync.aligned.m16n8k16`（CUTLASS 中的对应写法：`SM80_16x8x16_F32BF16BF16F32_TN`） | `mma.sync.aligned.m16n8k16.row.col.f32.bf16.bf16.f32`（或 `.f16`） | `HMMA.16816.F32.BF16`、`HMMA.16816.F32` | 本 SMSP 的 Tensor Core（单 warp 驱动）· 第 4 级 | 1 对 1，每条指令占 Tensor Core 管线 6.0 个周期，操作数 `A`、`B` 与累加器 `D` 均在向量寄存器中 |
| 60 | 单 warp FP8 矩阵乘（`sm_90a` 软件模拟） | 内联 `mma.sync.aligned.m16n8k32.row.col.f32.e4m3.e4m3.f32` | `mma.sync.aligned.m16n8k32.row.col.f32.e4m3.e4m3.f32` | `F2FP.F16.E4M3.UNPACK_B`、`HMMA.16816.F32` | ALU（解包）+ Tensor Core（`HMMA`）· 第 4 级 | `sm_90a` 无单 warp 原生 FP8 `QMMA`：1 条 PTX 被 `ptxas` 拆为 `F2FP` 解包加 **2** 条 `HMMA.16816.F32` |
| 61 | warpgroup 异步矩阵乘（SS 模式，操作数在 SMEM） | 内联 `wgmma.mma_async`（CUTLASS 中的对应写法：`SM90_64x64x16_F32BF16BF16_SS<tnspA, tnspB>`） | `wgmma.mma_async.sync.aligned.m64n64k16.f32.bf16.bf16 {d..},descA,descB,...` | `HGMMA.64x64x16.F32.BF16` | 全 SM 4 个 Tensor Core（128 线程协同）· 第 4 级 | 1 对 1，`M = 64` 固定，`N` 取 `8..256`（步长 8），`A` 与 `B` 通过统一寄存器描述符 `gdesc[URn]` 从 SMEM 读取 |
| 62 | warpgroup 异步矩阵乘（RS 模式与 FP8 `QGMMA`） | 左矩阵 `A` 在寄存器的内联 `wgmma`（CUTLASS 中的对应写法：`SM90_64x32x32_F32E4M3E4M3_RS_TN`） | `wgmma.mma_async.sync.aligned.m64n32k32.f32.e4m3.e4m3 {d..},{a0..a3},descB,...` | `QGMMA.64x32x32.F32.E4M3.E4M3` | 全 SM 4 个 Tensor Core · 第 4 级 | FP8 `wgmma` 编译为原生 `QGMMA`（`K = 32`）；RS 模式左矩阵 `A` 直接从各 warp 的向量寄存器传入 |
| 63 | `wgmma` 寄存器汇合栅栏 | 内联 `wgmma.fence.sync.aligned`（CUTLASS 中的对应写法：`cute::warpgroup_arrive()`） | `wgmma.fence.sync.aligned` | `WARPGROUP.ARRIVE` | SM 线程束组汇合单元 · 第 3 级 | 1 对 1，在首次 `wgmma` 前或普通指令改写累加器寄存器后执行 |
| 64 | `wgmma` 打包提交批次 | 内联 `wgmma.commit_group.sync.aligned`（CUTLASS 中的对应写法：`cute::warpgroup_commit_batch()`） | `wgmma.commit_group.sync.aligned` | `HGMMA`、`QGMMA`（末尾带 `gsb0` 标志） | 最后一条 `HGMMA/QGMMA` 上的控制位 · 第 3 级 | **无独立 SASS 指令**：被编码为该组最后一条 `HGMMA/QGMMA` 指令末尾的 `gsb0` 标志操作数 |
| 65 | `wgmma` 按在途组数等待 | 内联 `wgmma.wait_group.sync.aligned N`（CUTLASS 中的对应写法：`cute::warpgroup_wait<N>()`） | `wgmma.wait_group.sync.aligned N` | `WARPGROUP.DEPBAR.LE` | 线程束组记分牌 · 第 3 级 | 编译为 `WARPGROUP.DEPBAR.LE gsb0, N`，阻塞直到在途未完成的 `wgmma` 组数不超过 `N` |
| 66 | 从 SMEM 加载矩阵分片到寄存器（`ldmatrix`） | 内联 `ldmatrix`（CUTLASS 中的对应写法：`SM75_U32x4_LDSM_N`、`SM75_U16x8_LDSM_T`） | `ldmatrix.sync.aligned.m8n8.x1\|x2\|x4{.trans}.shared.b16` | `LDSM.16.M88.4`、`LDSM.16.M88`、`LDSM.16.M88.2`、`LDSM.16.MT88.4` | LSU → SMEM · 第 2 级 | 1 对 1，`.trans` 编译为带转置的 `.MT88`，为 `mma.sync` 或 `wgmma` RS 模式装填寄存器分片 |
| 67 | 从寄存器将矩阵分片存入 SMEM（`stmatrix`） | 内联 `stmatrix`（CUTLASS 中的对应写法：`SM90_U32x4_STSM_N`、`SM90_U16x8_STSM_T`） | `stmatrix.sync.aligned.m8n8.x1\|x2\|x4{.trans}.shared.b16` | `STSM.16.M88.4`、`STSM.16.MT88.4`、`STSM.16.M88`、`STSM.16.MT88.2` | LSU → SMEM · 第 2 级 | `ldmatrix` 的逆操作，常用于把累加器结果按 TMA 写回所需的交错布局直接写入 SMEM |
| 68 | 寄存器内 8×8 矩阵转置（`movmatrix`） | 内联 `movmatrix.sync.aligned.m8n8.trans.b16` | `movmatrix.sync.aligned.m8n8.trans.b16` | `MOVM.16.MT88` | 线程束寄存器交叉开关 · 第 4 级 | 1 对 1 在寄存器内转置 8×8 的 16 位矩阵分片 |
| 69 | 跨 warpgroup 动态重分配寄存器配额（`setmaxnreg`） | 内联 `setmaxnreg`（CUTLASS 中的对应写法：`cutlass::arch::warpgroup_reg_alloc<N>`、`cutlass::arch::warpgroup_reg_dealloc<N>`） | `setmaxnreg.inc.sync.aligned.u32 N`；`setmaxnreg.dec.sync.aligned.u32 N` | `USETMAXREG.TRY_ALLOC.CTAPOOL`、`USETMAXREG.DEALLOC.CTAPOOL` | SM 块内寄存器池分配器 · 第 2 级 | `N` 取 `24..256`（8 的倍数）；`dec` 将多余寄存器退回本 CTA 池，`inc` 从池中申领寄存器 |
| 70 | PDL 触发与等待 | `cudaGridDependencySynchronize()`；`cudaTriggerProgrammaticLaunchCompletion()`；内联 `griddepcontrol` | `griddepcontrol.wait`；`griddepcontrol.launch_dependents` | `ACQBULK`、`PREEXIT` | 网格硬件派发器与 SM · 第 0 级 | `wait` 编译为 `ACQBULK`（阻塞直到所有前序网格完成且显存写入对本网格可见）；`launch_dependents` 编译为 `PREEXIT`（前序所有 CTA 发出该指令或退出后，后继网格才可被调度；规范不保证在前序结束前一定已启动） |

---

## 5. 线程束操作、内存栅栏、原子操作与控制流速查表（第 71–91 项）

最后一组涵盖线程束内部的协同（洗牌 `SHFL`、单指令整数归约 `REDUX`、投票 `VOTE`）以及块内与全卡同步栅栏。此外还包含 L2 与 SMEM 原子操作、跨 SM 的释放/获取（`release / acquire`）交接、硬件计时器以及分支控制流。

| 序号 | 操作类别 | CUDA C++ 写法 | PTX 指令 | SASS 助记符（`sm_90a`） | 硬件单元与代价层级 | 编译说明 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 71 | 线程束内寄存器洗牌（`warp shuffle`） | `__shfl_sync(m,v,lane)`；`__shfl_xor_sync`；`__shfl_up_sync`；`__shfl_down_sync` | `shfl.sync.idx/bfly/up/down.b32` | `SHFL.IDX`、`SHFL.BFLY`、`SHFL.UP`、`SHFL.DOWN` | LSU/MIO 洗牌交叉开关 · 第 4 级 | `__shfl_xor_sync` 编译为 `.BFLY`（蝶形洗牌，实测发射间隔约 6.0 周期，延迟 24.0 周期）；`SHFL.DOWN` 对应 PTX `.down` 模式 |
| 72 | 线程束单指令整数归约（`redux.sync`） | `__reduce_add_sync(m,x)`；`__reduce_min/max/and/or/xor_sync` | `redux.sync.add/max/min.s32`；`redux.sync.and/or/xor.b32` | `REDUX.SUM.S32`、`REDUX.MAX.S32`、`REDUX.MIN`、`REDUX.XOR` | 线程束归约单元 · 第 4 级 | 1 条指令完成整束 32 个 32 位整数的归约（实测约 11.7 周期）；`sm_90a` 不支持 FP32 `REDUX` |
| 73 | 线程束投票与掩码汇总 | `__ballot_sync(m,p)`；`__any_sync`；`__all_sync`；`__uni_sync` | `vote.sync.ballot.b32`；`vote.sync.any/all/uni.pred` | `VOTE.ANY`、`VOTEU.ANY`、`VOTEU.ALL` | 线程束投票单元 · 第 3 级 | `ballot` 编译为 `VOTE.ANY Rd, PT, Ps`（返回 32 位掩码） |
| 74 | 线程束等值匹配 | `__match_any_sync(m,v)`；`__match_all_sync` | `match.any.sync.b32`；`match.all.sync.b32` | `MATCH.ANY` | 线程束匹配单元 · 第 4 级 | 找出同一 warp 内持有相同寄存器值的线程掩码 |
| 75 | 活跃掩码与特殊编号读取 | `__activemask()`；`__lanemask_lt()`；`threadIdx.x & 31` | `activemask.b32`；`mov.u32 %laneid / %lanemask_lt / %warpid` | `VOTE`、`S2R`、`S2UR`、`CS2R` | 特殊寄存器读取或投票单元 · 第 3 级 | `S2R / S2UR` 读取特殊寄存器 `SR_LANEID` 等；`activemask` 编译为 `VOTE.ANY` |
| 76 | 线程束内同步屏障 | `__syncwarp(mask)`；内联 `bar.warp.sync` | `bar.warp.sync mask` | `WARPSYNC.ALL`、`WARPSYNC`、`WARPSYNC.COLLECTIVE`、`BSSY`、`BSYNC` | 线程束调度器重汇合单元 · 第 3 级 | 全掩码编译为 `WARPSYNC.ALL`；`BSSY / BSYNC` 是编译器在分化分支前后自动插入的重汇合对 |
| 77 | 块内全员同步屏障（`__syncthreads`） | `__syncthreads()`；`__syncthreads_count/and/or` | `bar.sync 0`（即 `barrier.sync.aligned 0`）；`barrier.red.popc/and/or` | `BAR.SYNC.DEFER_BLOCKING`、`BAR.RED.OR.DEFER_BLOCKING` | SM 块内屏障单元（每 CTA 16 个命名屏障）· 第 3 级 | 1 对 1；H200 实测 128 线程无到达偏差的纯屏障耗时 20.4 周期；到达时间不齐时，等待时间等于最晚和最早到达之差，与屏障本身无关 |
| 78 | 命名部分屏障（生产者-消费者分组同步） | 内联 `bar.sync id, nthreads`；`bar.arrive id, nthreads`（CUTLASS 中的对应写法：`cutlass::arch::NamedBarrier::sync`） | `bar.sync id, n`；`bar.arrive id, n` | `BAR.SYNC.DEFER_BLOCKING`、`BAR.ARV` | SM 块内屏障单元 · 第 3 级 | 硬件屏障号 `id`（`0..15`）与线程数 `n` 编码为立即数（`NamedBarrier` 将前 8 个留作系统保留，用户传入的 `0..7` 会在内部加 8）；`BAR.ARV` 只报到不等待 |
| 79 | 块级、全卡级与系统级内存栅栏 | `__threadfence_block()`；`__threadfence()`；`__threadfence_system()`；内联 `fence.acq_rel.cta/gpu` | `fence.acq_rel.cta`；`fence.acq_rel.gpu`；`fence.sc.gpu` | `MEMBAR.ALL.CTA`、`MEMBAR.ALL.GPU`、`MEMBAR.SC.GPU`、`ERRBAR`、`CGAERRBAR`、`CCTL.IVALL` | LSU / 内存系统确认 · 第 3 级 | 等待本线程此前的写操作在对应作用域内落定（全卡栅栏等待 L2 确认并使本 SM 的 L1 失效，H200 实测空载 `fence.acq_rel.gpu` 约 269.0 周期、带 1 条在途写约 475 周期）；反汇编观察 `__threadfence_block()` 为 1 条 `MEMBAR.ALL.CTA`，`__threadfence()` 展开为 5 条指令 |
| 80 | 全局内存带返回值原子操作 | 使用返回值的 `atomicAdd`、`atomicExch`、`atomicCAS`、`atomicInc`、`fetch_add` | `atom.global.add.u32/f32`；`atom.global.exch/cas/inc` | `ATOMG.E.ADD.STRONG.GPU`、`ATOMG.E.ADD.S32.STRONG.GPU`、`ATOMG.E.EXCH.STRONG.GPU`、`ATOMG.E.INC.STRONG.GPU` | LSU → L2 原子单元 · 第 1 级 | 在 L2 执行读改写并等旧值返回 |
| 81 | 全局内存无返回值原子归约 | 忽略返回值的 `atomicAdd(p,v)`、`atomicMax`、`atomicMin`、向量 `atomicAdd(float2*/float4*)` | `red.global.add.f32/v4.f32/s32`；`red.global.min.u64` | `REDG.E.ADD.S32.STRONG.GPU`、`REDG.E.ADD.F32.FTZ.RN.STRONG.GPU`、`REDG.E.ADD.F32x4.FTZ.RN.STRONG.GPU` | LSU → L2 归约单元 · 第 1 级 | 不用返回值时编译器自动把 `atomicAdd` 转为只发不等的 `REDG`；`F32x2 / F32x4` 向量原子归约为 `sm_90` 新增 |
| 82 | SMEM 原子操作 | `atomicAdd(&smem[i],v)`；`atomicAdd_block`；`atomicXor` | `atom.shared.add.u32`；`red.shared` | `ATOMS.POPC.INC.32`、`ATOMS.XOR`、`ATOMS.CAST.SPIN` | LSU → SMEM 原子单元 · 第 2 级 | 不用返回值的 `atomicAdd(&s, 1)` 编译为单条 `ATOMS.POPC.INC.32`；无原生支持的共享内存原子操作生成 `ATOMS.CAST.SPIN` 比较交换循环 |
| 83 | 跨 SM 释放与获取（`release / acquire`）交接 | `cuda::atomic_ref<int, thread_scope_device>::store/load`；内联 `ld.acquire.gpu`、`red.release.gpu` | `ld.acquire.gpu.global.u32 [a]`；`red.release.gpu.global.add.s32 [a],v`；`atom.acq_rel.gpu` | `LDG.E.STRONG.GPU`、`CCTL.IVALL`、`MEMBAR.ALL.GPU`、`ERRBAR`、`CGAERRBAR`、`REDG`、`ATOMG` | LSU + L2 · 第 1 级 | PTX 规范保证获取-释放的内存可见性顺序；反汇编观察中，`ld.acquire.gpu` 展开为 `LDG.E.STRONG.GPU + CCTL.IVALL`（使本 SM 全部 L1 缓存行失效以从 L2 重取），`red.release.gpu` 展开为 `MEMBAR.ALL.GPU`（等待此前写排空至 L2）`+ ERRBAR + CGAERRBAR + REDG` |
| 84 | 协作启动全网格同步栅栏（`grid.sync`） | `cooperative_groups::this_grid().sync()`；`cudaLaunchCooperativeKernel` | 标准库展开：全局原子计数 + 内存栅栏 + `ld.acquire` 自旋 + `bar.sync` | `ATOMG.E.ADD.STRONG.GPU`、`MEMBAR.ALL.GPU`、`LDG.E.STRONG.GPU`、`CCTL.IVALL`、`BAR.SYNC.DEFER_BLOCKING` | L2 原子单元 + 各 SM 轮询· 第 0 级 | 由标准库组合块内屏障、全卡栅栏与 L2 计数器轮询实现（132 个 CTA 实测耗时约 1.42 µs） |
| 85 | 轮询休眠与让出调度（`nanosleep`） | `__nanosleep(ns)`；`__nv_nanosleep` | `nanosleep.u32 t` | `NANOSLEEP`、`YIELD` | SMSP 线程束调度器 · 第 3 级 | 在 `[0, 2t]` 纳秒区间内挂起当前 warp（上限 1 ms），自旋循环中常辅以 `YIELD`（让出调度指令） |
| 86 | 读取周期计数器与全局纳秒计时器 | `clock64()`；`clock()`；内联读取 `%globaltimer` 或 `%clock64` | `mov.u64 d, %clock64`；`mov.u64 d, %globaltimer` | `CS2R`、`S2UR`、`S2R` | 特殊寄存器读取 · 第 3 级 | `%clock64` 编译为 `CS2R Rd, SR_CLOCKLO`，`%globaltimer` 编译为 `CS2R Rd, SR_GLOBALTIMERLO` |
| 87 | 分支、调用、返回、退出与断点（含 64 位整数除法子程序调用） | `if / for / switch`；函数调用；64 位整数除法 `a / b`（`int64_t`）；`return` | `bra / bra.uni`；`call.uni`；`div.s64 / u64`；`ret`；`exit` | `BRA`、`BRX`、`CALL`、`RET`、`EXIT`、`BPT`、`BSSY`、`BSYNC`、`BREAK` | 分支与发射单元 · 第 3 级 | 整束一致跳转标 `.U`；分化分支包在 `BSSY ... BSYNC` 内；`sm_90a` 无硬件 64 位整数除法，`div.s64` 会编译为慢速子程序调用 `CALL.REL __cuda_sm20_div_s64`（改用 32 位无符号除法可消去调用） |
| 88 | 线程与块下标读取及统一寄存器搬运 | `threadIdx.x`；`blockIdx.x`；`blockDim.x`；`gridDim.x`；整束一致标量 | `mov.u32 %tid.x / %ctaid.x / %ntid.x / %nctaid.x` | `S2R`、`S2UR`、`R2UR`、`UMOV`、`ULDC` | 特殊寄存器与统一寄存器文件 · 第 3 级 | `S2R` 读入每线程向量寄存器 `R`；`S2UR` 直接读入整束共享的统一寄存器 `UR`；`R2UR` 把向量寄存器值拷入 `UR` |
| 89 | 双元素半精度快速指数（`ex2.approx.f16x2 / bf16x2`） | 内联 `ex2.approx.f16x2`；`ex2.approx.ftz.bf16x2`；`h2exp2(__half2)` | `ex2.approx.f16x2 d,a`；`ex2.approx.ftz.bf16x2 d,a` | `MUFU.EX2.F16`、`MUFU.EX2.BF16`、`PRMT` | SFU 管线（2 次 `MUFU`）+ ALU 管线 · 第 4 级 | 编译实测 1 条 `ex2.approx.f16x2` 被拆成 **2** 条标量 `MUFU.EX2.F16`（含 `.H1` 高半字）加 1 条 `PRMT` 重排，无法减半 SFU 发射周期 |
| 90 | `volatile` 与系统级作用域访存 | `volatile T*` 读写；`cuda::atomic_ref<T, thread_scope_system>`；内联 `ld.relaxed.sys` | `ld.volatile.global`；`ld/st.relaxed.sys.global` | `LDG.E.STRONG.SYS`、`LD.E.STRONG.SYS`、`STG.E.STRONG.SYS` | LSU → L2 → PCIe / NVLink · 第 1 级 | `.STRONG.SYS` 绕过 L1 并与主机及跨卡保持系统级一致；共享内存 `ld.volatile.shared` 生成普通 `LDS` |
| 91 | 其他全局缓存修饰符（`.ca / .lu / .cv / .wt`） | `__ldca(p)`；`__ldlu(p)`（最后一次使用）；`__ldcv(p)`；`__stwt / __stcs` | `ld.global.ca/lu/cv`；`st.global.wt/cs` | `LDG.E`、`LDG.E.LU`、`LDG.E.STRONG.SYS`、`STG.E.EF` | LSU · 第 2 级 | `.ca` 默认为 `LDG.E`，`.lu / .cv / .wt` 对应 `.LU`、`.STRONG.SYS`、`.EF` 后缀（推断） |

---

**带走一句话：** 看到一条陌生的 SASS 指令，查这 91 项就能知道它是哪行源码、走哪条管线、会卡在第几级。
