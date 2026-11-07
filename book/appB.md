# 附录 B：在反汇编或剖析器里看到一条不认识的 SASS 指令，怎样查到它来自哪种源码写法、走哪条硬件管线、属于第几级？

**本书地图：** 前言 → 导引一 → 导引二 → 导引三 → 第 1 章 [第 1 级] → 第 2 章 [第 2 级] → 第 3 章 [第 3 级] → 第 4 章 [第 4 级] → 第 5 章 [第 5 级] → 第 6 章 [第 6 级] → 第 7–9 章 → 第 10 章 → **【附录 B：速查】**

附录 A 末尾问到：在反汇编或剖析器里看到一条不认识的 SASS 指令，怎样查到它来自哪种源码写法、走哪条硬件管线、属于第几级？本附录只收本书正文或图里出现过的指令，按功能分成四组速查表，并在末尾附上按 SASS 助记符字母顺序排列的索引。

表中每一项按它用到的硬件定级，“本书在哪里用到”一列另写教它或用到它的那一节：

- **第 1 级**：网格的启动与交接（第 1 章第 4 节：PDL），以及整网格同步（第 7 章第 12 节、第 8 章第 6 节）。
- **第 2 级**：全卡与 L2（第 2 章：HBM / L2 访问、L2 原子与归约、全卡范围的栅栏与释放 / 获取，见第 2 章第 6 节），以及 SM 之间的通信（集群与 DSMEM，机制见第 7 章第 12 节）。
- **第 3 级**：单个 SM（第 3 章：SMEM、LSU、TMA、`mbarrier`、寄存器借调）。
- **第 4 级**：SMSP 调度（第 4 章：块内与 warp 内屏障、洗牌、分支、记分牌等待；投票见第 7 章第 9 节、第 8 章第 6 节，`REDUX` 见第 1 章 图 I-1）。
- **第 5 级**：执行管线与 Tensor Core（第 5 章：FMA / ALU / SFU 指令、`HMMA` / `HGMMA` / `QGMMA`）。
- **第 6 级**：比特与机器码（第 6 章：打包与类型转换、SASS 编码、编在控制位里的组标志）。

---

## 1. 一条 SASS 指令怎样拆开读？

<!-- FIG appB-a: 图 B-1 上方画 CUDA C++ 源码经前端生成 PTX、再由 ptxas 编译成 128 位（16 B）SASS 指令字的降低流水线（模式 1 对应 LDG.E.EF.128 R8, desc[UR12][R8.64] 的 7 个操作码后缀与操作数字段）；下方模式 2–11 展示十个典型降低案例，每个案例标题前标明所属类别（第一类“0 条独立指令或位操作/无返回指令”：模式 2 wgmma.commit_group → 末尾 gsb0 组标志、模式 6 atomicAdd 返回值未用 → REDG / 共享内存 ATOMS.POPC.INC.32、模式 9 cvt.f32.bf16 → 1 条 PRMT、模式 10 mapa → 0 条独立指令配合 S2R + LD.E；第二类“1 条 PTX 拆成一串 SASS”：模式 3 mma.sync e4m3 → F2FP + 2 × HMMA、模式 4 ex2.approx.f16x2 → 2 × MUFU.EX2 + PRMT、模式 5 div.rn.f32 → MUFU.RCP + FFMA + FCHK + BRA、模式 8 全卡栅栏与释放/获取展开为 MEMBAR + ERRBAR + CGAERRBAR + CCTL.IVALL；第三类“换了名字或变成后缀/描述符”：模式 7 缓存修饰符 .cg/.cs/.nc 与 createpolicy → desc[URn]、模式 11 cvt…bf16x2 → F2FP 与 cp.async.mbarrier.arrive → ARRIVES，读数只写映射关系）。 -->

看到第 3 章第 8 节那条 16 B 流式读取指令 `LDG.E.EF.128 R8, desc[UR12][R8.64]` 时，它的每一段分别代表什么？**SASS 助记符由“操作码 + 修饰后缀”拼成，后缀按固定位置写出地址宽度、缓存提示和位宽；操作数则依次写出目的寄存器、存放在统一寄存器里的内存描述符和 64 位地址。**

从源码到机器码一共走三层：CUDA C++ → PTX → `ptxas` 生成的 **128 位**（**16 B**）SASS 指令字（PTX 与 `ptxas` 见第 4 章第 4 节；128 位指令字结构见第 6 章第 5 节）。按图 B-1 模式 1 把 `LDG.E.EF.128 R8, desc[UR12][R8.64]` 逐段拆开：

- **`LDG`**：**操作码**，表示全局显存读取；
- **`.E`**：**修饰后缀**，表示使用 64 位扩展地址；
- **`.EF`**：本 SM 的 L1 优先淘汰提示（`evict_first`，注意它只管本 SM 的 L1）；
- **`.128`**：每个线程一次读取 128 位（**16 B**），装进 `R8..R11` 四个连续的 32 位向量寄存器；
- **`desc[UR12]`**：放在统一寄存器 `UR`（见第 7 章第 7 节）里的 64 位**内存描述符**，第 2 章第 4 节用 `createpolicy` 生成的 L2 留存提示就编码在这个描述符里，不占指令后缀；
- **`[R8.64]`**：由 `R8:R9` 寄存器对拼出的 64 位字节地址。

会拆读单条指令之后，看反汇编时最让人困惑的是条数和名字对不上：一条 PTX 在 SASS 里可能变成 0 条、好几条，或者换了名字——这是下一节要理清的三类变化。

---

## 2. 一条 PTX 为什么不一定变成一条同名的 SASS？

为什么在反汇编里有时找不到自己写的那条 PTX，有时一条 PTX 又变成了一串 SASS？**`ptxas` 会把一条 PTX 编成 0 条独立指令（变成别的指令上的一个标志位）、拆成一串指令，或者换成另一个名字；按这三类去认，每类先记一个代表例子，其余直接查后面的四组速查表。**

对照图 B-1 下方的案例，三类变化各有明确的规律：

- **第一类：没有独立指令。** 比如 `wgmma.commit_group`（见第 5 章第 5 节、第 6 章第 6 节）在 SASS 里不占单独的指令字，而是直接编码成这一批最后一条 `HGMMA` 末尾的组标志（见速查三的 `wgmma.commit_group` 一项）。
- **第二类：拆成一串指令。** 比如单 warp 的 FP8 矩阵乘 `mma.sync … e4m3`（见第 7 章第 2 节：$L = 1$ 的 8 行）在 `sm_90a` 上先用 `F2FP` 把 FP8 解包成 FP16，再连发 **2** 条 `HMMA`（见速查三）。再比如第 9 章第 3 节的集群屏障（集群本身见第 7 章第 12 节）：默认的 `cluster.sync()` 在 `sm_90a` 的反汇编里展开成全卡范围的栅栏加 `ERRBAR`、`CGAERRBAR` 和让 L1 失效的 `CCTL.IVALL`。它真正的代价是等待此前的写入被 L2 确认、并让本 SM 的 L1 失效，而不是多出来的那几条指令字（见速查三的 `cluster.sync` 一项；一致性只在 L2 这一点见第 2 章第 6 节）。
- **第三类：换了名字或变成操作数。** 全局读取的缓存修饰符在 SASS 里会变成后缀或描述符操作数；例如 L2 留存提示（`ld.global.L2::cache_hint`，策略描述符来自 `createpolicy`，见第 2 章第 4 节）在 SASS 里变成了 `LDG` 上的 `desc[URn]` 操作数（见速查二）。

在查表之前还要记住一条边界：PTX 规范只保证内存可见性的顺序，并不规定具体的 SASS 指令序列；本附录列出的展开都是在 `sm_90a` 反汇编里看到的结果，换了编译器版本之后要重新核对一遍。接下来按功能进入四组速查表。

---

## 3. 速查一：算术、超越函数与类型转换

查这一组指令时，先看它走 FMA、ALU 还是 SFU 管线（见第 5 章第 1 节）；这一组除类型转换与打包外都属第 5 级，打包与类型转换（`F2FP`、`PRMT` 升宽、`I2FP`）属第 6 级。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `fma.rn.f32`（`mad.f32` 同） | `FFMA` | FMA 管线 · 第 5 级 | 导引三第 1 节、第 5 章第 1 节 | 写法：`fmaf(a,b,c)`、`__fmaf_rn` 或默认收缩的 `a*b+c`；1 对 1 编译为 `FFMA` |
| 2 | `add.f32`；`mul.f32` | `FADD`、`FMUL` | FMA 管线 · 第 5 级 | 导引三第 4 节、第 5 章第 1 节 | 写法：`a+b`、`a*b`、`__fadd_rn`、`__fmul_rn`；用 `__fadd_rn` / `__fmul_rn` 可阻止编译器把 `a*b+c` 收缩为 `FFMA`，代价是多发 1 条指令 |
| 3 | `min.f32`；`max.f32`；`selp.f32`；`setp.lt.f32` | `FMNMX`、`FSEL`、`FSETP` | ALU 管线 · 第 5 级 | 第 7 章第 3 节、第 7 章第 8 节 | 写法：`fminf`、`fmaxf`、`cond?a:b`、`a<b`；`FMNMX` 靠谓词选择取最小值或最大值，`setp` 写入谓词寄存器 `P0..P6` |
| 4 | `div.full.f32`；`div.approx.f32` | `MUFU.RCP`、`FMUL` | SFU + FMA 管线 · 第 5 级 | 第 7 章第 3 节、图 B-1 | 写法：`__fdividef(a,b)` 或开启 `-use_fast_math` 时的 `a/b`；1 条 PTX 展开为倒数近似 `MUFU.RCP` 加乘法 `FMUL`，比标准除法省去牛顿迭代与分支，代价是精度低于 IEEE 标准除法 |
| 5 | `div.rn.f32`；`sqrt.rn.f32` | `MUFU.RCP`、`FCHK`、`FFMA`、`BRA` | SFU + FMA + 分支单元 · 第 5 级 | 图 B-1（正文未用到） | 写法：默认 `a/b`、`sqrtf(x)`；含牛顿迭代 `FFMA` 与浮点范围检查 `FCHK`，越界时跳转到慢速修正路径 |
| 6 | `ex2.approx.f32`；`ex2.approx.ftz.f32` | `MUFU.EX2`、`FMUL`、`FSETP` | SFU 管线 · 第 5 级 | 第 7 章第 9 节、第 8 章第 13 节 | 写法：`exp2f(x)`、`__expf(x)` 或内联 PTX；`.ftz` 把非规格化数当 0 处理（非规格化数见第 6 章第 3 节），编译为裸的 1 条 `MUFU.EX2`；漏写 `.ftz` 会外包 `FSETP + FMUL` 修正指令 |
| 7 | `ex2.approx.f16x2`；`ex2.approx.ftz.bf16x2` | `MUFU.EX2.F16`、`PRMT` | SFU + ALU 管线 · 第 5 级 | 第 7 章第 8 节、图 B-1 | 写法：`h2exp2` 或内联 PTX；1 条 PTX 拆成 2 条标量 `MUFU.EX2.F16` 加 1 条 `PRMT` 重排，不能减半 SFU 周期（见第 7 章第 8 节） |
| 8 | `rcp.approx.ftz.f32`；`rsqrt.approx.ftz.f32`；`lg2.approx.ftz.f32` | `MUFU.RCP`、`MUFU.RSQ`、`MUFU.LG2` | SFU 管线 · 第 5 级 | 导引一第 1 节、图 B-1 | 写法：`rsqrtf(x)`、`__log2f(x)` 或内联 PTX；仅 `.approx.ftz` 形态为单条 `MUFU`，代价是近似误差高于标准库函数 |
| 9 | `tanh.approx.f32` | `MUFU.TANH` | SFU 管线 · 第 5 级 | 第 10 章第 8 节 | 写法：内联 PTX（标准库 `tanhf` 为软件展开）；1 对 1 编译为 `MUFU.TANH` |
| 10 | `add.rn.f16x2`；`mul.rn.bf16x2`；`fma.rn.bf16x2` | `HADD2`、`HMUL2`、`HFMA2` | FMA 管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 3 节 | 写法：`__hadd2`、`__hmul2`、`__hfma2`；BF16 打包指令带 `.BF16_V2` 后缀 |
| 11 | `max.f16x2`；`min.bf16x2`；`max.bf16x2` | `HMNMX2`、`VHMNMX` | ALU / FMA 管线 · 第 5 级 | 第 7 章第 8 节、第 7 章第 9 节 | 写法：`__hmax2`、`__hmin2`；单条指令同时求一对半精度数的极值，三输入归约时可融合为 `VHMNMX` |
| 12 | `mad.lo.s32`；`mad.wide.u32`；`mul.hi.u32` | `IMAD`、`IADD3`、`LEA` | `IMAD` 走 FMA；`IADD3 / LEA` 走 ALU · 第 5 级 | 第 5 章第 1 节、第 6 章第 3 节 | 写法：整数 `a*b+c`、`__mul24`、指针偏移 `ptr + i*size`；`IMAD` 兼具寄存器搬运（`IMAD.MOV`）、左移（`IMAD.SHL`）与 64 位宽乘加（`IMAD.WIDE`） |
| 13 | `add.s32`；`sub.s32`；`add.s64` | `IADD3`、`VIADD` | ALU 管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 2 节 | 写法：整数 `a+b+c`、`a+b`；三输入加法用 `IADD3`，双输入用 `VIADD`，64 位加法拆成 `IADD3 + IADD3.X` |
| 14 | `and.b32`；`or.b32`；`xor.b32`；`lop3.b32` | `LOP3` | ALU 管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 2 节 | 写法：`a&b`、`a\|b`、`a^b`、`~a` 或内联 `lop3.b32`；`ptxas` 把任意 1–3 输入按位逻辑折叠成 1 条 `LOP3.LUT`（8 位真值表立即数） |
| 15 | `shl.b32`；`shr.b32`；`shf.l.wrap.b32`；`shf.r.clamp.b32` | `SHF`、`IMAD.SHL.U32`、`USHF` | ALU（或 FMA）管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 3 节、第 8 章第 3 节 | 写法：`a<<n`、`a>>n`、`__funnelshift_l`、`__funnelshift_r`；常数左移可编成 `SHF`（走 ALU）或 `IMAD.SHL.U32`（走 FMA 分担 ALU，代价是跨管线多约 2 个周期，见第 6 章第 3 节） |
| 16 | `prmt.b32` | `PRMT` | ALU 管线 · 第 6 级 | 第 6 章第 2 节、第 6 章第 3 节、第 7 章第 10 节 | 写法：`__byte_perm(x,y,sel)` 或内联 PTX；从两个源寄存器的 8 个字节里按 4 位选择器挑出 4 个字节拼进目标寄存器 |
| 17 | `popc.b32`；`brev.b32`；`bfind.u32`；`bfe.u32`；`bfi.b32` | `POPC`、`BREV`、`FLO`、`SGXT`、`LOP3` | ALU / SFU 管线 · 第 5 级 | 第 8 章第 6 节 | 写法：`__popc`、`__brev`、`__clz`、`__ffs` 或内联 `bfe / bfi`；`bfe.u32` 编译为 `SGXT.U32` 或 `SHF + LOP3` |
| 18 | `min.s32`；`max.s32`；`abs.s32`；`setp.lt.s32`；`selp.b32` | `VIMNMX`、`IABS`、`ISETP`、`SEL` | ALU 管线 · 第 5 级 | 第 4 章第 4 节（图 4-3） | 写法：整数 `min / max`、`abs`、`a<b`、`?:`；1 对 1 走整数 ALU 管线 |
| 19 | `cvt.rn.bf16.f32` | `F2F.BF16.F32` | SFU 管线 · 第 6 级 | 第 5 章第 1 节、第 8 章第 16 节 | 写法：`__float2bfloat16(x)`；单值标量转换走 4 通道 SFU 管线，会与 `MUFU.EX2` 争抢 SFU；成对转换可改用下一项的 `F2FP` |
| 20 | `cvt.rn.bf16x2.f32`；`cvt.rn.f16x2.f32` | `F2FP.BF16.F32.PACK_AB`、`F2FP.F16.F32.PACK_AB` | ALU 管线 · 第 6 级 | 第 7 章第 9 节、第 8 章第 16 节 | 写法：`__floats2bfloat162_rn(a,b)`、`__floats2half2_rn(a,b)`；1 条指令把两个 FP32 舍入打包进 1 个 32 位寄存器，走 16 通道 ALU 管线（见第 8 章第 16 节），代价是要求两个待转换值已经在同一线程配成一对 |
| 21 | `cvt.f32.bf16` | `PRMT`、`IMAD.U32`、`SHF.L.U32` | ALU 管线 · 第 6 级 | 导引三第 1 节、第 6 章第 1 节、图 B-1 | 写法：`__bfloat162float(h)`、`__bfloat1622float2`；BF16 正好是 FP32 的高 16 位，编译为字节重排 `PRMT R0,RZ,0x7610,R0` 或移位，走 ALU 而不走 SFU |
| 22 | `cvt.rn.satfinite.e4m3x2.f32` | `F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C` | ALU 管线 · 第 6 级 | 第 7 章第 1 节、图 B-1 | 写法：`__nv_cvt_float2_to_fp8x2` 或内联 PTX；把两个 FP32 饱和打包成 16 位 FP8（E4M3）对，并保留目标寄存器的另一半 |
| 23 | `cvt.rn.f16x2.e4m3x2` | `F2FP.F16.E4M3.UNPACK_B` | ALU 管线 · 第 6 级 | 第 7 章第 2 节、图 B-1 | 写法：`__nv_cvt_fp8x2_to_halfraw2` 或内联 PTX；把 2 个 FP8（E4M3）字节解包成 `FP16x2` |
| 24 | `cvt.rn.f32.s32`；`cvt.rzi.s32.f32`；`cvt.rmi.f32.f32`；`cvt.rzi.f32.f32` | `I2FP.F32.S32`、`I2FP.F32.U32`、`F2I.TRUNC.NTZ`、`FRND.FLOOR`、`FRND.TRUNC` | `I2FP` 走 ALU；`F2I / FRND` 走 SFU · 第 6 级 | 第 5 章第 1 节 | 写法：`(float)i`、`(int)f`、`floorf`、`truncf`、`rintf`；32 位整数转 FP32 用 `I2FP`（走 ALU），浮点转整数与取整用 `F2I / FRND`（走 SFU） |

---

## 4. 速查二：全局与片上访存、异步拷贝

先分清数据走哪条路：经寄存器的 `LDG / STG`、绕过寄存器直写 SMEM 的 `LDGSTS`（`cp.async`）、单线程发起的 TMA（`UTMALDG / UTMASTG`）（见第 3 章第 3 节）。HBM / L2 层面的访问属第 2 级，SMEM、TMA、`cp.async` 属第 3 级。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 25 | `ld.global.b32`；`ld.global.v4.b32`；`st.global.v4.b32` | `LDG.E`、`LDG.E.64`、`LDG.E.128`、`LDG.E.U16`、`STG.E`、`STG.E.64`、`STG.E.128` | LSU → L1 → L2 · 第 3 级 | 第 3 章第 2 节、第 3 章第 8 节 | 写法：`*p`、`p[i]`、`reinterpret_cast<uint4*>(p)[i]`（16 B）；位宽直接体现为后缀（`.64 / .128 / .U16`），均带 `desc[URn]` 操作数；若 16 B 向量只用其中几个分量，`ptxas` 会拆成标量 `LDG.E` |
| 26 | `ld.global.nc.u32`；`ld.global.nc.v4.f32` | `LDG.E.CONSTANT`、`LDG.E.128.CONSTANT`、`LDG.E.64.CONSTANT` | LSU → L1 只读路径 → L2 · 第 3 级 | 第 8 章第 8 节 | 写法：`__ldg(p)`、`const __restrict__ T* p` 或内联 `ld.global.nc`；`.nc` 编译为 `.CONSTANT` 后缀；只用于本 kernel 运行期间没人改写的地址，否则属未定义行为 |
| 27 | `ld.global.cg.v4.b32`；`st.global.cg.f32` | `LDG.E.STRONG.GPU`、`STG.E.STRONG.GPU` | LSU → L2（绕过 L1）· 第 2 级 | 第 2 章第 6 节、图 B-1 | 写法：`__ldcg(p)`、`__stcg(p,v)` 或内联 `ld / st.global.cg`；`.cg` 编译为 `.STRONG.GPU`；只适合轮询标志本身，读到标志后再读数据要用获取语义（如 `ld.acquire.gpu` 或加获取栅栏，见第 2 章第 6 节），否则可能从本 SM 的 L1 读到旧数据 |
| 28 | `ld.global.cs.v4.b32` | `LDG.E.EF`、`LDG.E.EF.128`、`LDG.E.EF.64` | LSU → L1 · 第 3 级 | 第 3 章第 8 节、附录 B 第 1 节 | 写法：`__ldcs(p)` 或内联 `ld.global.cs`；`.cs` 编译为 `.EF`（`evict_first`）后缀，只管本 SM 的 L1 优先淘汰；L2 的策略另在 `desc[URn]` 里 |
| 29 | `createpolicy.fractional .L2::evict_first.b64`；`ld.global .L1::evict_first .L2::cache_hint` | `UMOV`、`LDG.E.EF`、`LDG.E` | LSU + L2 · 第 2 级 | 第 2 章第 4 节、第 10 章第 2 节 | 写法：内联 PTX；L1 提示变成 `.EF / .EL` 后缀，L2 留存提示编码在 `desc[URn]` 操作数里传给硬件；若被保留的数据本来就不会被挤出 L2，加提示不省时间（见第 10 章第 2 节） |
| 30 | `prefetch.global.L2 [a]`；`prefetch.global.L1` | `CCTL.E.PF2` | LSU → L2 · 第 2 级 | 第 7 章第 6 节、第 9 章第 4 节 | 写法：`__builtin_prefetch` 或内联 `prefetch.global.L2`；1 对 1 生成 `CCTL.E.PF2`；若预取过早、在用到前被流式数据冲出 L2，反而多读一次 HBM（见第 7 章第 6 节） |
| 31 | `ld.local`；`st.local` | `LDL`、`LDL.LU`、`STL` | LSU → L1 → L2（位于全局显存）· 第 3 级 | 第 3 章第 1 节、第 3 章第 6 节、第 10 章第 6 节 | 写法：寄存器溢出（`ptxas -v` 报告 `spill`）、动态下标局部数组或未内联函数栈帧；`.LU` 在读出后释放缓存行；出现 `LDL / STL` 说明寄存器读写退化成了局部内存往返 |
| 32 | `ld.param.*`；`ld.const` | `LDC`、`ULDC` | SM 常量缓存 · 第 3 级 | 第 4 章第 4 节（图 4-3） | 写法：kernel 形参或 `__constant__` 变量；形参存于常量体 `c[0x0][0x210..]`，`ULDC` 直接把整束相同的常量读进统一寄存器 `UR`（见第 7 章第 7 节） |
| 33 | `ld.b32`；`st.b32`；`cvta.shared.u64`；`ld.shared::cluster` | `LD`、`ST`、`LD.E` | LSU · 第 3 级 | 第 7 章第 12 节、图 B-1 | 写法：编译器无法静态区分地址空间的指针，或跨 CTA 远端共享内存指针；通用 `LD.E / ST.E` 需在运行期由硬件解码地址窗口 |
| 34 | `ld.shared.b32`；`ld.shared.v4.b32`；`st.shared::cta.v4.b32` | `LDS`、`LDS.64`、`LDS.128`、`LDS.U8`、`LDS.U16`、`STS`、`STS.64`、`STS.128` | LSU → SMEM · 第 3 级 | 导引三第 4 节、第 3 章第 7 节 | 写法：`__shared__` 数组读写；1 对 1 带位宽后缀；同一波次不同通道撞上同一个 4 B bank 时会串行排队（见第 3 章第 7 节） |
| 35 | `cp.async.cg.shared.global [dst],[src],16`；`cp.async.ca.shared.global` | `LDGSTS.E.BYPASS.128`、`LDGSTS.E.BYPASS.128.ZFILL`、`LDGSTS.E`、`LDGSTS.E.64` | LSU（L2 直写 SMEM）· 第 3 级 | 第 3 章第 3 节、第 7 章第 6 节 | 写法：`__pipeline_memcpy_async` 或内联 `cp.async`；不经私有寄存器直写 SMEM；`.cg`（仅 16 B）编译为绕过 L1 的 `.BYPASS.128`，越界填零时生成 `.ZFILL`；代价是每个线程仍要自己算地址、发指令 |
| 36 | `cp.async.commit_group`；`cp.async.wait_group N`；`cp.async.wait_all` | `LDGDEPBAR`、`DEPBAR.LE` | LSU 记分牌 · 第 4 级 | 第 3 章第 4 节、第 5 章第 6 节 | 写法：`__pipeline_commit()`、`__pipeline_wait_prior(N)` 或内联 PTX；`commit_group` 编译为 `LDGDEPBAR`，`wait_group N` 编译为 `DEPBAR.LE SB0, N`；仅保证本线程发出的拷贝落定，跨线程读取前仍需块内屏障 |
| 37 | `cp.async.mbarrier.arrive .noinc.shared.b64 [bar]` | `ARRIVES.LDGSTSBAR.64.ARVCNT` | LSU + `mbarrier` 单元 · 第 3 级 | 第 3 章第 5 节、图 B-1 | 写法：内联 PTX；本线程此前发出的 `cp.async` 全部落定后自动触发 `mbarrier` 报到 |
| 38 | `cp.async.bulk.tensor .2d.shared::cluster.global .mbarrier::complete_tx::bytes` | `UTMALDG.2D`、`UTMALDG.3D`、`UTMALDG.5D` | SM 内专用 TMA 单元 · 第 3 级 | 第 3 章第 3 节、第 5 章第 6 节 | 写法：内联 PTX；1 对 1，由 1 个线程发出，占 0 个数据寄存器；代价是主机端要先建描述符、块形状受限，且不能按离散行号收集（见第 3 章第 3 节、第 10 章第 10 节） |
| 39 | `cp.async.bulk.tensor .2d.global.shared::cta .bulk_group`；`cp.async.bulk.commit_group`；`cp.async.bulk.wait_group` | `UTMASTG.2D`、`UTMASTG.3D`、`UTMACMDFLUSH`、`DEPBAR.LE` | TMA 单元 · 第 3 级 | 第 3 章第 3 节 | 写法：内联 PTX；把 SMEM 分块异步写回全局显存；发起写回前需先执行 `fence.proxy.async.shared::cta` 并完成块内同步（见第 3 章第 3 节），`commit_group` 编译为 `UTMACMDFLUSH` |
| 40 | `cp.reduce.async.bulk .tensor.2d.global.shared::cta .add.bulk_group` | `UTMAREDG.2D.ADD`、`UTMAREDG.3D.ADD` | TMA 单元 + L2 原子归约 · 第 2 级 | 第 5 章第 7 节、第 6 章第 9 节、第 10 章第 8 节 | 写法：内联 PTX；把 SMEM 分块直接发往 L2 做硬件原子加法，无需在 SM 内读回旧值；代价是浮点原子累加顺序不固定（见第 5 章第 7 节） |
| 41 | `cp.async.bulk .shared::cluster.global .mbarrier::complete_tx::bytes` | `UBLKCP.S.G`、`UBLKCP.S.S`、`UBLKRED.G.S.ADD.BF16.RN` | TMA 单元 · 第 3 级 | 第 3 章第 3 节 | 写法：内联 PTX；免张量描述符的一维连续字节流搬运与归约；要求地址与字节数按 16 B 对齐，搬非连续的多行时每行都要单独发 1 条（见第 3 章第 3 节） |

---

## 5. 速查三：屏障、集群共享内存与 Tensor Core

生产者靠 `mbarrier`（`SYNCS`）和 DSMEM 搬数据，消费者靠 `HGMMA / QGMMA` 用 Tensor Core（`mbarrier` 见第 3 章第 5 节，DSMEM 见第 7 章第 12 节，`wgmma` 见第 5 章第 5 节）。`mbarrier`、`setmaxnreg` 属第 3 级；DSMEM、集群屏障属第 2 级；`HMMA / HGMMA / QGMMA` 属第 5 级；`commit_group` 的组标志属第 6 级；PDL 的 `ACQBULK / PREEXIT` 属第 1 级。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 42 | `mbarrier.init.shared::cta.b64 [addr], count`；`mbarrier.inval.shared::cta.b64 [addr]` | `SYNCS.EXCH.64`、`SYNCS.CCTL.IV` | SM 同步单元（`SYNCS`）· 第 3 级 | 第 3 章第 5 节 | 写法：内联 PTX；`init` 编译为 `SYNCS.EXCH.64`（写入 64 位屏障字），`inval` 编译为 `SYNCS.CCTL.IV` |
| 43 | `mbarrier.arrive.shared::cta.b64`；`mbarrier.arrive.expect_tx .shared::cta.b64 state,[addr],txcount` | `SYNCS.ARRIVE.TRANS64`、`SYNCS.ARRIVE.TRANS64.A1T0` | `SYNCS` 单元 · 第 3 级 | 第 3 章第 5 节、第 5 章第 6 节 | 写法：内联 PTX；普通报到带 `.A1T0`（报到计数加 1、期望字节 0），登记 TMA 字节数用带寄存器操作数的 `.TRANS64`；若消费者在共享内存读（`LDS`）尚未返回前向 `empty[s]` 报到，会触发读后写竞态（见第 3 章第 5 节） |
| 44 | `mbarrier.try_wait.parity .shared::cta.b64 p,[addr],phase`；`mbarrier.test_wait` | `SYNCS.PHASECHK.TRANS64.TRYWAIT`、`SYNCS.PHASECHK.TRANS64` | `SYNCS` 单元 · 第 3 级 | 第 3 章第 5 节、第 5 章第 6 节 | 写法：内联 PTX；`try_wait` 编译为 `.TRYWAIT`，在硬件里等待直到相位位翻转或超时，未翻转时由 `@!P BRA` 重试 |
| 45 | `mapa.shared::cluster.u32 ra,addr,cta`；`mbarrier.arrive .shared::cluster.b64 _,[ra]` | `SYNCS.ARRIVE.TRANS64.RED.A1T0`、`R2UR` | `SYNCS` + 集群互连 · 第 2 级 | 第 7 章第 12 节 | 写法：内联 PTX；`.RED` 后缀表示无返回值的远端跨 CTA 报到 |
| 46 | `fence.mbarrier_init .release.cluster`；`fence.proxy.async .shared::cta`（或 `.global`） | `FENCE`、`FENCE.VIEW.ASYNC.S`、`FENCE.VIEW.ASYNC.G`、`MEMBAR.ALL.CTA` | LSU / 内存管线 · 第 3 级 | 第 3 章第 3 节、第 5 章第 7 节、第 8 章第 11 节 | 写法：内联 PTX；普通线程写完 SMEM 后，必须执行 `FENCE.VIEW.ASYNC.S` 才能让 TMA 或 `wgmma` 的异步代理看到新数据（见第 3 章第 3 节） |
| 47 | `mapa.shared::cluster.u32 d,a,cta`；`getctarank`；`mov.u32 %cluster_ctarank` | `R2UR`、`S2R`、`S2UR`、`LEA` | ALU / 统一数据通路 · 第 2 级 | 第 7 章第 12 节、图 B-1 | 写法：内联 PTX；`mapa` 在 `sm_90a` 上无独立操作码，由普通算术指令把目标 CTA 编号拼进地址高位，再用 `R2UR` 装入统一寄存器 |
| 48 | `ld.shared::cluster.v4.b32 [a]`；`st.shared::cluster`；`atom.shared::cluster.add` | `LD.E.128`、`ST.E`、`ATOM` | LSU → 集群互连 · 第 2 级 | 第 7 章第 12 节、图 B-1 | 写法：内联 PTX；远端读取编译为通用 `LD.E`（而非本块 `LDS`）；读取前须用集群同步保证远端 SMEM 已就绪 |
| 49 | `st.async.shared::cluster .mbarrier::complete_tx::bytes .v4.f32 [ra],{..},[mbar]` | `STAS`、`STAS.128`、`STAS.64` | 集群互连 + 远端 `mbarrier` · 第 2 级 | 第 7 章第 12 节、第 9 章第 3 节 | 写法：内联 PTX；1 对 1，数据写入同集群远端 CTA 的 SMEM 后自动扣减远端 `mbarrier` 的期望字节数 |
| 50 | `barrier.cluster.arrive {.relaxed/.release}.aligned`；`barrier.cluster.wait {.acquire}.aligned` | `UCGABAR_ARV`、`UCGABAR_WAIT`、`MEMBAR.ALL.GPU`、`ERRBAR`、`CGAERRBAR`、`CCTL.IVALL` | 集群屏障单元 · 第 2 级 | 第 7 章第 12 节、第 9 章第 3 节 | 写法：`cooperative_groups::this_cluster().sync()` 或内联 PTX；默认 `cluster.sync()` 附带 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR + CCTL.IVALL`（等待前序写被 L2 确认并使本 SM 的 L1 失效）；只有屏障前写的数据在屏障后不再被读，或者数据另有自己的完成通知（例如 `st.async` 加 `mbarrier`，见本组 `st.async` 一项）时，才能用 `.relaxed`；否则屏障不再保证数据的先后 |
| 51 | `mma.sync.aligned.m16n8k16 .row.col.f32.bf16.bf16.f32`（或 `.f16`） | `HMMA.16816.F32.BF16`、`HMMA.16816.F32` | 本 SMSP 的 Tensor Core · 第 5 级 | 第 5 章第 3 节、第 6 章第 3 节、第 7 章第 2 节 | 写法：内联 PTX；1 对 1，每条指令占 Tensor Core 管线 6.0 个周期，操作数 $A$、$B$ 与累加器 $D$ 均在向量寄存器中 |
| 52 | `mma.sync.aligned.m16n8k32 .row.col.f32.e4m3.e4m3.f32` | `F2FP.F16.E4M3.UNPACK_B`、`HMMA.16816.F32` | ALU + Tensor Core · 第 5 级 | 第 7 章第 2 节、附录 B 第 2 节 | 写法：内联 PTX；`sm_90a` 无单 warp 原生 FP8 `QMMA`，1 条 PTX 被 `ptxas` 拆为 `F2FP` 解包加 2 条 `HMMA.16816.F32` |
| 53 | `wgmma.mma_async.sync.aligned .m64n64k16.f32.bf16.bf16` | `HGMMA.64x64x16.F32.BF16` | 全 SM 4 个 Tensor Core · 第 5 级 | 第 5 章第 3 节、第 5 章第 5 节 | 写法：内联 PTX；1 对 1，$m = 64$ 固定，$n$ 取 $8..256$（步长 8），$A$ 与 $B$ 通过统一寄存器描述符 `gdesc[URn]` 从 SMEM 读取；代价是必须由 4 个 warp 齐步发射且累加器占向量寄存器（见第 10 章第 10 节） |
| 54 | `wgmma.mma_async.sync.aligned .m64n32k32.f32.e4m3.e4m3` | `QGMMA.64x32x32.F32.E4M3.E4M3` | 全 SM 4 个 Tensor Core · 第 5 级 | 第 5 章第 3 节、第 7 章第 10 节 | 写法：内联 PTX；FP8 `wgmma` 编译为原生 `QGMMA`（$k = 32$，吞吐见第 5 章第 3 节）；RS 模式下左矩阵 $A$ 直接从各 warp 的向量寄存器传入 |
| 55 | `wgmma.fence.sync.aligned` | `WARPGROUP.ARRIVE` | 线程束组汇合单元 · 第 4 级 | 第 5 章第 5 节、第 10 章第 10 节、附录 A 第 2 节 | 写法：内联 PTX；1 对 1，在首次 `wgmma` 前或普通指令改写累加器寄存器后执行，用来保证累加器寄存器与 SMEM 的读写顺序；4 个 warp 一起执行来自 `.sync.aligned` |
| 56 | `wgmma.commit_group .sync.aligned` | `HGMMA`、`QGMMA`（末尾带 `gsb0` 标志） | 最后一条 `HGMMA / QGMMA` 上的控制位 · 第 6 级 | 第 5 章第 5 节、第 6 章第 6 节、附录 B 第 2 节 | 写法：内联 PTX；无独立 SASS 指令，编码为该批次最后一条 `HGMMA / QGMMA` 指令末尾的 `gsb0` 组标志 |
| 57 | `wgmma.wait_group .sync.aligned N` | `WARPGROUP.DEPBAR.LE` | 线程束组记分牌 · 第 4 级 | 第 5 章第 5 节、第 6 章第 6 节 | 写法：内联 PTX；编译为 `WARPGROUP.DEPBAR.LE gsb0, N`，阻塞直到在途未完成的 `wgmma` 组数不超过 $N$；异步区间里混入改写累加器的普通指令或分支同步不一致时，编译器会在每条 `HGMMA` 后自动插 `DEPBAR.LE 0`（见第 6 章第 6 节） |
| 58 | `ldmatrix.sync.aligned .m8n8.x4{.trans}.shared.b16` | `LDSM.16.M88.4`、`LDSM.16.M88`、`LDSM.16.M88.2`、`LDSM.16.MT88.4` | LSU → SMEM · 第 3 级 | 第 7 章第 10 节 | 写法：内联 PTX；1 对 1，`.trans` 编译为带转置的 `.MT88`，一个 warp 按 $8 \times 8$ 小块把 SMEM 读进寄存器分片（见第 7 章第 10 节） |
| 59 | `stmatrix.sync.aligned .m8n8.x4{.trans}.shared.b16` | `STSM.16.M88.4`、`STSM.16.MT88.4`、`STSM.16.M88`、`STSM.16.MT88.2` | LSU → SMEM · 第 3 级 | 第 5 章第 7 节 | 写法：内联 PTX；`ldmatrix` 的逆操作，把累加器寄存器分片按交错布局直接写入 SMEM，供随后 TMA 写回或块归约 |
| 60 | `setmaxnreg.inc.sync.aligned .u32 N`；`setmaxnreg.dec.sync.aligned .u32 N` | `USETMAXREG.TRY_ALLOC.CTAPOOL`、`USETMAXREG.DEALLOC.CTAPOOL` | SM 块内寄存器池分配器 · 第 3 级 | 第 3 章第 6 节、第 7 章第 7 节、第 10 章第 10 节 | 写法：内联 PTX；$N$ 取 $24..256$（8 的倍数），`dec` 把生产者多余寄存器退回本 CTA 池，`inc` 为消费者申领寄存器；要求整个 warpgroup 对齐执行（见第 3 章第 6 节、第 4 章第 4 节） |
| 61 | `griddepcontrol.wait`；`griddepcontrol.launch_dependents` | `ACQBULK`、`PREEXIT` | 网格硬件派发器与 SM · 第 1 级 | 第 1 章第 4 节、第 6 章第 7 节、第 9 章第 5 节 | 写法：`cudaGridDependencySynchronize()`、`cudaTriggerProgrammaticLaunchCompletion()` 或内联 `griddepcontrol`（PTX 与 SASS 名的对应见第 6 章第 7 节）；`wait` 编译为 `ACQBULK`（阻塞直到前序网格完成且写入可见）；`launch_dependents` 编译为 `PREEXIT`（所有 CTA 发出它或退出后，后继网格可以被调度）；在 `launch_dependents` 之前执行 gpu 范围的释放栅栏，能让前序网格的写入对后继网格的开始可见（见第 9 章第 5 节）；触发过早会让后继占着 SM 空等（见第 1 章第 4 节、第 7 章第 11 节） |

---

## 6. 速查四：warp 操作、内存栅栏、原子操作与控制流

warp 内协作（`SHFL`、`REDUX`、`VOTE`）属第 4 级：`SHFL` 见第 4 章第 5 节，`VOTE` 见第 7 章第 9 节与第 8 章第 6 节，`REDUX` 见第 1 章 图 I-1；全卡范围的栅栏、L2 原子与释放 / 获取交接属第 2 级（第 2 章第 6 节）；整网格同步属第 1 级（第 7 章第 12 节、第 8 章第 6 节）。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 62 | `shfl.sync.idx.b32`；`shfl.sync.bfly.b32`；`shfl.sync.up.b32`；`shfl.sync.down.b32` | `SHFL.IDX`、`SHFL.BFLY`、`SHFL.UP` | LSU / MIO 洗牌交叉开关 · 第 4 级 | 第 4 章第 5 节 | 写法：`__shfl_sync(m,v,lane)`、`__shfl_xor_sync`、`__shfl_up_sync`、`__shfl_down_sync`；`__shfl_xor_sync` 编译为 `.BFLY`（蝶形洗牌，发射间隔约 6.0 周期，延迟 24.0 周期） |
| 63 | `redux.sync.add.s32`；`redux.sync.max.s32`；`redux.sync.min.s32`；`redux.sync.xor.b32` | `REDUX.SUM.S32`、`REDUX.MAX.S32`、`REDUX.MIN`、`REDUX.XOR` | 线程束归约单元 · 第 4 级 | 第 1 章 图 I-1（正文未用到） | 写法：`__reduce_add_sync(m,x)`、`__reduce_min_sync`、`__reduce_max_sync`、`__reduce_xor_sync`；1 条指令完成整束 32 个 32 位整数的归约（约 11.7 周期）；`sm_90a` 不支持 FP32 `REDUX` |
| 64 | `vote.sync.ballot.b32`；`vote.sync.any.pred`；`vote.sync.all.pred` | `VOTE.ANY`、`VOTEU.ANY`、`VOTEU.ALL` | 线程束投票单元 · 第 4 级 | 第 7 章第 9 节、第 8 章第 6 节 | 写法：`__ballot_sync(m,p)`（见第 8 章第 6 节）、`__any_sync`（见第 7 章第 9 节）、`__all_sync`；`ballot` 编译为 `VOTE.ANY Rd, PT, Ps`（返回 32 位掩码） |
| 65 | `bar.warp.sync mask` | `WARPSYNC.ALL`、`WARPSYNC`、`WARPSYNC.COLLECTIVE`、`BSSY`、`BSYNC` | 线程束调度器重汇合单元 · 第 4 级 | 第 4 章第 4 节、第 10 章第 9 节 | 写法：`__syncwarp(mask)` 或内联 `bar.warp.sync`；全掩码编译为 `WARPSYNC.ALL`；`BSSY / BSYNC` 是编译器在分化分支前后自动插入的汇合指令对（见第 4 章第 4 节、第 10 章第 9 节） |
| 66 | `bar.sync 0`（即 `barrier.sync.aligned 0`）；`barrier.red.popc`；`barrier.red.or` | `BAR.SYNC.DEFER_BLOCKING`、`BAR.RED.OR.DEFER_BLOCKING` | SM 块内屏障单元 · 第 4 级 | 导引三第 4 节、第 4 章第 4 节 | 写法：`__syncthreads()`、`__syncthreads_count`、`__syncthreads_or`；1 对 1；到达不齐时，等待的时间等于最晚与最早到达之差 |
| 67 | `bar.sync id, n`；`bar.arrive id, n` | `BAR.SYNC.DEFER_BLOCKING`、`BAR.ARV` | SM 块内屏障单元 · 第 4 级 | 第 4 章第 4 节、第 7 章第 7 节 | 写法：内联 `bar.sync id, n`、`bar.arrive id, n`（非对齐形式为 `barrier.sync`，见第 4 章第 4 节）；硬件屏障号 `id`（`0..15`）与线程数 `n` 编码为立即数（见第 7 章第 7 节），`BAR.ARV` 只报到不等待 |
| 68 | `fence.acq_rel.cta`；`fence.acq_rel.gpu`；`fence.sc.gpu` | `MEMBAR.ALL.CTA`、`MEMBAR.ALL.GPU`、`MEMBAR.SC.GPU`、`ERRBAR`、`CGAERRBAR`、`CCTL.IVALL` | LSU / 内存系统确认 · 第 2 级（`.cta` 属第 4 级） | 第 2 章第 6 节、第 8 章第 11 节 | 写法：`__threadfence_block()`、`__threadfence()` 或内联 PTX；全卡栅栏等待此前的写入被 L2 确认并使本 SM 的 L1 失效（实测周期见第 2 章第 6 节）；只有两个以上的标志必须被所有线程按同一个全序看到时才需要 `fence.sc`，生产者-消费者同步用 `acq_rel` 就够 |
| 69 | `fence.release.gpu` | 没有在反汇编里核对 | LSU / 内存系统确认 · 第 2 级 | 第 2 章第 6 节、第 9 章第 5 节 | 写法：内联 PTX；`fence.release.gpu`：它之前本线程的所有读写，要通过紧接在它后面的一次写入（例如写标志的 `st.relaxed`）才对其他线程变得可见；对方要用配对的获取（读到这次写入）才算同步（见第 2 章第 6 节）。需要 PTX ISA 8.6 以上、`sm_90` 以上 |
| 70 | `atom.global.add.u32`；`atom.global.add.f32`；`atom.global.exch`；`atom.global.inc` | `ATOMG.E.ADD.STRONG.GPU`、`ATOMG.E.ADD.S32.STRONG.GPU`、`ATOMG.E.EXCH.STRONG.GPU`、`ATOMG.E.INC.STRONG.GPU` | LSU → L2 原子单元 · 第 2 级 | 第 2 章第 6 节、第 2 章第 7 节、第 6 章第 9 节 | 写法：使用返回值的 `atomicAdd`、`atomicExch`、`atomicCAS`、`atomicInc`、`fetch_add`；在 L2 执行读改写并等旧值返回，往返延迟远高于不返回旧值的 `REDG`；直接对 BF16 做标量原子加会退化成比较交换重试循环（见第 2 章第 7 节、第 6 章第 9 节） |
| 71 | `red.global.add.f32`；`red.global.add.v4.f32`；`red.global.add.s32`；`red.global.min.u64` | `REDG.E.ADD.S32.STRONG.GPU`、`REDG.E.ADD.F32.FTZ.RN.STRONG.GPU`、`REDG.E.ADD.F32x4.FTZ.RN.STRONG.GPU` | LSU → L2 归约单元 · 第 2 级 | 第 2 章第 6 节、第 7 章第 12 节、第 9 章第 3 节 | 写法：忽略返回值的 `atomicAdd(p,v)`、向量 `atomicAdd(float2* / float4*)`；编译器自动转为只发不等的 `REDG`（代价是拿不到旧值） |
| 72 | `atom.shared.add.u32`；`red.shared.add.u32` | `ATOMS.POPC.INC.32`、`ATOMS.XOR`、`ATOMS.CAST.SPIN` | LSU → SMEM 原子单元 · 第 3 级 | 第 3 章第 7 节、第 8 章第 6 节、图 B-1 | 写法：`atomicAdd(&smem[i],v)`、`atomicAdd_block`、`atomicXor`；不用返回值的 `atomicAdd(&s, 1)` 编译为单条 `ATOMS.POPC.INC.32`，无原生支持的共享内存原子操作生成 `ATOMS.CAST.SPIN` 比较交换循环 |
| 73 | `ld.acquire.gpu.global.u32 [a]`；`red.release.gpu.global.add.s32 [a],v`；`atom.acq_rel.gpu` | `LDG.E.STRONG.GPU`、`CCTL.IVALL`、`MEMBAR.ALL.GPU`、`ERRBAR`、`CGAERRBAR`、`REDG`、`ATOMG` | LSU + L2 · 第 2 级 | 第 2 章第 6 节、第 7 章第 12 节、第 8 章第 11 节 | 写法：`cuda::atomic_ref<int, thread_scope_device>::store / load` 或内联 `ld.acquire.gpu`、`red.release.gpu`；PTX 只保证顺序；L1 失效、等 L2 确认是本 SM 的实现方式（一致性在 L2、L1 不一致见第 2 章第 6 节）：`ld.acquire.gpu` 展开为 `LDG.E.STRONG.GPU + CCTL.IVALL`，`red.release.gpu` 展开为 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR + REDG` |
| 74 | 全局原子计数 + 内存栅栏 + `ld.acquire` 自旋 + `bar.sync`（标准库展开） | 没有在反汇编里核对 | L2 原子单元 + 各 SM 轮询 · 第 1 级 | 第 8 章第 6 节 | 写法：`cooperative_groups::this_grid().sync()`（配合 `cudaLaunchCooperativeKernel`）；由标准库组合块内屏障、全卡栅栏与 L2 计数器轮询实现，要求全网格所有 CTA 同时驻留（见第 2 章第 6 节、第 7 章第 12 节、第 8 章第 6 节） |
| 75 | `mov.u64 d, %clock64`；`mov.u64 d, %globaltimer` | `CS2R`、`S2UR`、`S2R` | 特殊寄存器读取 · 第 4 级 | 第 3 章第 4 节、第 5 章第 3 节、第 10 章第 5–6 节 | 写法：`clock64()`、`clock()` 或内联读取 `%globaltimer`、`%clock64`；`%clock64` 编译为 `CS2R Rd, SR_CLOCKLO`，`%globaltimer` 编译为 `CS2R Rd, SR_GLOBALTIMERLO`（`%globaltimer` 最小步长实测 32 ns，见第 10 章第 5 节） |
| 76 | `bra`；`bra.uni`；`call.uni`；`ret`；`exit` | `BRA`、`BRX`、`CALL`、`RET`、`EXIT`、`BPT`、`BSSY`、`BSYNC`、`BREAK` | 分支与发射单元 · 第 4 级 | 第 4 章第 4 节、第 10 章第 9 节 | 写法：`if / for / switch`、函数调用、`return`；整束一致跳转标 `.U`，分化分支包在 `BSSY ... BSYNC` 内（分支分化代价见第 4 章第 4 节） |
| 77 | `mov.u32 %tid.x`；`mov.u32 %ctaid.x`；`mov.u32 %ntid.x`；`mov.u32 %nctaid.x` | `S2R`、`S2UR`、`R2UR`、`UMOV`、`ULDC` | 特殊寄存器与统一寄存器文件 · 第 4 级 | 导引三第 3 节、第 7 章第 7 节 | 写法：`threadIdx.x`、`blockIdx.x`、`blockDim.x`、`gridDim.x`；`S2R` 读入每线程向量寄存器 `R`，`S2UR` 直接读入整束共享的统一寄存器 `UR`（见第 7 章第 7 节），`R2UR` 把向量寄存器值拷入 `UR` |

---

## 7. 按 SASS 助记符查（索引）

- `ACQBULK` → 速查三 第 61 项
- `ARRIVES` → 速查二 第 37 项
- `ATOM` → 速查三 第 48 项
- `ATOMG` → 速查四 第 70 项；速查四 第 73 项
- `ATOMS` → 速查四 第 72 项
- `BAR` → 速查四 第 66 项；速查四 第 67 项
- `BPT` → 速查四 第 76 项
- `BRA` → 速查一 第 5 项；速查四 第 76 项
- `BREAK` → 速查四 第 76 项
- `BREV` → 速查一 第 17 项
- `BRX` → 速查四 第 76 项
- `BSSY` → 速查四 第 65 项；速查四 第 76 项
- `BSYNC` → 速查四 第 65 项；速查四 第 76 项
- `CALL` → 速查四 第 76 项
- `CCTL` → 速查二 第 30 项；速查三 第 50 项；速查四 第 68 项；速查四 第 73 项
- `CGAERRBAR` → 速查三 第 50 项；速查四 第 68 项；速查四 第 73 项
- `CS2R` → 速查四 第 75 项
- `DEPBAR` → 速查二 第 36 项；速查二 第 39 项
- `ERRBAR` → 速查三 第 50 项；速查四 第 68 项；速查四 第 73 项
- `EXIT` → 速查四 第 76 项
- `F2F` → 速查一 第 19 项
- `F2FP` → 速查一 第 20 项；速查一 第 22 项；速查一 第 23 项；速查三 第 52 项
- `F2I` → 速查一 第 24 项
- `FADD` → 速查一 第 2 项
- `FCHK` → 速查一 第 5 项
- `FENCE` → 速查三 第 46 项
- `FFMA` → 速查一 第 1 项；速查一 第 5 项
- `FLO` → 速查一 第 17 项
- `FMNMX` → 速查一 第 3 项
- `FMUL` → 速查一 第 2 项；速查一 第 4 项；速查一 第 6 项
- `FRND` → 速查一 第 24 项
- `FSEL` → 速查一 第 3 项
- `FSETP` → 速查一 第 3 项；速查一 第 6 项
- `HADD2` → 速查一 第 10 项
- `HFMA2` → 速查一 第 10 项
- `HGMMA` → 速查三 第 53 项；速查三 第 56 项
- `HMMA` → 速查三 第 51 项；速查三 第 52 项
- `HMNMX2` → 速查一 第 11 项
- `HMUL2` → 速查一 第 10 项
- `I2FP` → 速查一 第 24 项
- `IABS` → 速查一 第 18 项
- `IADD3` → 速查一 第 12 项；速查一 第 13 项
- `IMAD` → 速查一 第 12 项；速查一 第 15 项；速查一 第 21 项
- `ISETP` → 速查一 第 18 项
- `LD` → 速查二 第 33 项；速查三 第 48 项
- `LDC` → 速查二 第 32 项
- `LDG` → 速查二 第 25 项；速查二 第 26 项；速查二 第 27 项；速查二 第 28 项；速查二 第 29 项；速查四 第 73 项
- `LDGDEPBAR` → 速查二 第 36 项
- `LDGSTS` → 速查二 第 35 项
- `LDL` → 速查二 第 31 项
- `LDS` → 速查二 第 34 项
- `LDSM` → 速查三 第 58 项
- `LEA` → 速查一 第 12 项；速查三 第 47 项
- `LOP3` → 速查一 第 14 项；速查一 第 17 项
- `MEMBAR` → 速查三 第 46 项；速查三 第 50 项；速查四 第 68 项；速查四 第 73 项
- `MUFU` → 速查一 第 4 项；速查一 第 5 项；速查一 第 6 项；速查一 第 7 项；速查一 第 8 项；速查一 第 9 项
- `POPC` → 速查一 第 17 项
- `PREEXIT` → 速查三 第 61 项
- `PRMT` → 速查一 第 7 项；速查一 第 16 项；速查一 第 21 项
- `QGMMA` → 速查三 第 54 项；速查三 第 56 项
- `R2UR` → 速查三 第 45 项；速查三 第 47 项；速查四 第 77 项
- `REDG` → 速查四 第 71 项；速查四 第 73 项
- `REDUX` → 速查四 第 63 项
- `RET` → 速查四 第 76 项
- `S2R` → 速查三 第 47 项；速查四 第 75 项；速查四 第 77 项
- `S2UR` → 速查三 第 47 项；速查四 第 75 项；速查四 第 77 项
- `SEL` → 速查一 第 18 项
- `SGXT` → 速查一 第 17 项
- `SHF` → 速查一 第 15 项；速查一 第 21 项
- `SHFL` → 速查四 第 62 项
- `ST` → 速查二 第 33 项；速查三 第 48 项
- `STAS` → 速查三 第 49 项
- `STG` → 速查二 第 25 项；速查二 第 27 项
- `STL` → 速查二 第 31 项
- `STS` → 速查二 第 34 项
- `STSM` → 速查三 第 59 项
- `SYNCS` → 速查三 第 42 项；速查三 第 43 项；速查三 第 44 项；速查三 第 45 项
- `UBLKCP` → 速查二 第 41 项
- `UBLKRED` → 速查二 第 41 项
- `UCGABAR_ARV` → 速查三 第 50 项
- `UCGABAR_WAIT` → 速查三 第 50 项
- `ULDC` → 速查二 第 32 项；速查四 第 77 项
- `UMOV` → 速查二 第 29 项；速查四 第 77 项
- `USETMAXREG` → 速查三 第 60 项
- `USHF` → 速查一 第 15 项
- `UTMACMDFLUSH` → 速查二 第 39 项
- `UTMALDG` → 速查二 第 38 项
- `UTMAREDG` → 速查二 第 40 项
- `UTMASTG` → 速查二 第 39 项
- `VHMNMX` → 速查一 第 11 项
- `VIADD` → 速查一 第 13 项
- `VIMNMX` → 速查一 第 18 项
- `VOTE` → 速查四 第 64 项
- `VOTEU` → 速查四 第 64 项
- `WARPGROUP` → 速查三 第 55 项；速查三 第 57 项
- `WARPSYNC` → 速查四 第 65 项

---

**带走一句话：** 看到一条陌生的 SASS 指令，按助记符在本附录里找到它，就知道它来自哪种源码写法、走哪条管线、属于第几级、本书哪一章用过它；要定位到具体哪一行源码，还要用带行号信息编译的 kernel 在剖析器的源码视图里看。
