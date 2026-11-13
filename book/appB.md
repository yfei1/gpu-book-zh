# 附录 B：一条不认识的 SASS 指令，从哪里来、走哪条硬件管线、属于第几级？

**本书地图：** 前言 → 导引一 → 导引二 → 导引三 → 第 1 章 [第 1 级] → 第 2 章 [第 2 级] → 第 3 章 [第 3 级] → 第 4 章 [第 4 级] → 第 5 章 [第 5 级] → 第 6 章 [第 6 级] → 第 7–9 章 → 第 10 章 → **【附录 B：速查】**

附录 A 末尾留了个问题：碰到一条不认识的 SASS 指令，它从哪里来、走哪条硬件管线、属于第几级？本附录只收正文或图里出现过 PTX 或源码写法的指令，SASS 一列给出本书反汇编里见到的助记符。下面按功能分成四组速查表，末尾附有按助记符字母排序的索引。

每一项按它用到的硬件定级；“本书在哪里用到”一列写讲到它或用到它的那一节：

- **第 1 级**：网格的启动与交接，以及整网格同步，见第 1 章。
- **第 2 级**：直接作用于中央 L2 或跨 SM 的操作，包括 L2 留存提示与预取、L2 原子与归约、全卡内存屏障与释放获取，以及集群与 DSMEM，见第 2 章。
- **第 3 级**：单个 SM 内部的数据通路与资源，包括经本 SM L1 的普通全局读写、SMEM、TMA、`cp.async`、`mbarrier`、`setmaxnreg` 与块内内存栅栏，见第 3 章。
- **第 4 级**：SMSP 调度，包括块内与 warp 内屏障、洗牌、投票、分支、记分牌等待，以及时钟与线程编号等特殊寄存器读取，见第 4 章。
- **第 5 级**：执行管线与 Tensor Core，包括 FMA、ALU、SFU 算术与超越函数指令，以及 `HMMA`、`HGMMA`、`QGMMA`，见第 5 章。
- **第 6 级**：比特与机器码，包括位重排与打包类型转换、SASS 编码，以及编在控制位里的组标志，见第 6 章。

---

## 1. 一条 SASS 指令怎样拆开读？

<!-- FIG appB-a: 图 B-1 上方画 CUDA C++ 源码经前端生成 PTX、再由 ptxas 编译成 128 位（16 B）SASS 指令字的降低流水线（模式 1 对应 LDG.E.EF.128 R8, desc[UR12][R8.64] 的 7 个操作码后缀与操作数字段）；下方模式 2–10 展示九个典型降低案例，每个案例标题前标明所属类别（第一类“0 条独立指令或无返回指令”：模式 2 wgmma.commit_group → 末尾 gsb0 组标志、模式 6 atomicAdd 返回值未用 → 只有 REDG、模式 9 cvt.f32.bf16 → 1 条 PRMT 或移位；第二类“1 条 PTX 拆成一串 SASS”：模式 3 mma.sync e4m3 → F2FP + 2 × HMMA、模式 4 ex2.approx.f16x2 → 2 × MUFU.EX2 + PRMT、模式 5 div.approx.f32 → MUFU.RCP + FMUL、模式 8 __threadfence() / fence.sc.gpu → 4 或 5 条 SASS（内联 fence.sc.gpu 为 MEMBAR.SC.GPU + ERRBAR + CGAERRBAR + CCTL.IVALL，nvrtc 的 __threadfence() 前面还多 MEMBAR.ALL.CTA）；第三类“换了名字或变成后缀/描述符”：模式 7 缓存修饰符 .cg/.cs/.nc 与 createpolicy → desc[URn]（推测）、模式 10 cvt.rn.bf16x2.f32 → F2FP，读数只写映射关系）。 -->

**SASS 助记符由操作码加修饰后缀拼成，操作数依次写出目的寄存器、内存描述符和 64 位地址。**

从源码到机器码一共走三层：CUDA C++ → PTX → `ptxas` 生成的 **128 位**（**16 B**）SASS 指令字，见第 6 章第 5 节。我们拿图 B-1 模式 1 的 `LDG.E.EF.128 R8, desc[UR12][R8.64]` 来拆开读。它是一条带留存提示的 16 B 宽流式全局读取，见第 2 章第 4 节与第 3 章第 8 节：

- **`LDG`**：**操作码**，表示全局显存读取；
- **`.E`**：**修饰后缀**，表示使用 64 位扩展地址；
- **`.EF`**：带 `evict_first` 优先淘汰提示的后缀；NVIDIA 没有公开它作用于 L1 还是 L2（本书样本的 PTX 同时写了 `L1::evict_first` 与 L2 留存策略，反汇编只出现一个 `.EF` 后缀和一个 `desc[URn]` 操作数）；
- **`.128`**：每个线程一次读取 128 位（**16 B**），装进 `R8..R11` 四个连续的 32 位向量寄存器；
- **`desc[UR12]`**：放在统一寄存器 `UR` 里的 64 位**内存描述符**；我们推测第 2 章第 4 节的 L2 留存提示（在 PTX 里用 `createpolicy` 生成）编码在这个描述符里（未查明）。`UR` 是整个 warp 共享的寄存器（见第 7 章第 7 节），助记符以 `U` 开头的指令读写它；
- **`[R8.64]`**：由 `R8:R9` 寄存器对拼出的 64 位字节地址。

---

## 2. 一条 PTX 为什么不一定变成一条同名的 SASS？

**`ptxas` 会把一条 PTX 编成 0 条独立指令、拆成一串指令，或者换成另一个名字与操作数。**

- **第一类：没有独立指令。** 比如 `wgmma.commit_group`，见第 5 章第 5 节与第 6 章第 6 节，在 SASS 里不占单独的指令字，而是直接编码成这一批最后一条 `HGMMA` 末尾的组标志，见速查三第 45 项。
- **第二类：拆成一串指令。** 单 warp 的 FP8 矩阵乘 `mma.sync … e4m3` 在 `sm_90a` 上先用 `F2FP` 把 FP8 解包成 FP16，再连发 **2** 条 `HMMA`，见速查三第 41 项。第 9 章第 3 节的集群屏障（`barrier.cluster.arrive/wait`）编译为 `UCGABAR_ARV` / `UCGABAR_WAIT`，默认形式还在报到前加全卡内存屏障（`MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR`），在等待后加 `CCTL.IVALL`，见速查三第 39 项。
- **第三类：换了名字或变成操作数。** 全局读取的缓存修饰符在 SASS 里会变成后缀，还有一些我们推测编进了描述符操作数。例如第 2 章第 4 节带 `createpolicy` 的读取在 SASS 里变成 `.EF / .EL` 后缀，它的 L2 策略我们推测编码在 `LDG` 的 `desc[URn]` 操作数里（未查明；不带提示的普通读取也有 `desc[URn]`），见速查二第 24 项。

为什么对不上号？因为 PTX 规范只规定语义，不规定具体的 SASS 指令序列。全卡内存屏障里的 `ERRBAR`、`CGAERRBAR`，NVIDIA 并没有公开硬件细节；本书只记录 `sm_90a` 反汇编里看到的序列，换了编译器版本之后记得重新核对。

---

## 3. 速查一：算术、超越函数与类型转换

查这一组指令时，先看它走 FMA、ALU 还是 SFU 管线，见第 5 章第 1 节。算术与超越函数属第 5 级，位重排与打包类型转换属第 6 级。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 写法与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `fma.rn.f32`（`mad.rn.f32` 同） | `FFMA` | FMA 管线 · 第 5 级 | 导引三第 1 节、第 5 章第 1 节 | `fmaf(a,b,c)`、`__fmaf_rn` 或默认收缩的 `a*b+c`；1 对 1 编译为 `FFMA` |
| 2 | `add.f32`；`mul.f32` | `FADD`、`FMUL` | FMA 管线 · 第 5 级 | 导引三第 4 节、第 5 章第 1 节 | `a+b`、`a*b`、`__fadd_rn`、`__fmul_rn`；用 `__fadd_rn` / `__fmul_rn` 可阻止编译器把 `a*b+c` 收缩为 `FFMA`，代价是多发 1 条指令 |
| 3 | `div.full.f32`；`div.approx.f32` | `MUFU.RCP`、`FMUL` | SFU + FMA 管线 · 第 5 级 | 第 7 章第 3 节 | `div.approx.f32`（`__fdividef(a,b)` 或开启 `-use_fast_math` 时的 `a/b`）展开为倒数近似 `MUFU.RCP` 加乘法 `FMUL`；`div.full.f32`（`-prec-div=false` 时的 `a/b`）在此之外还要缩放操作数以覆盖全范围，指令更多（本书无反汇编样本）。两者都比 IEEE 除法 `div.rn.f32` 省去牛顿迭代与分支，代价是精度低于 IEEE 标准除法 |
| 4 | `ex2.approx.f32`；`ex2.approx.ftz.f32` | `MUFU.EX2`、`FMUL`、`FSETP` | SFU 管线 · 第 5 级 | 第 7 章第 9 节 | `exp2f(x)`、`__expf(x)` 或内联 PTX；`.ftz` 把非规格化数当 0 处理（非规格化数见第 6 章第 3 节），编译为裸的 1 条 `MUFU.EX2`；漏写 `.ftz` 会多出 3 条修正指令：1 条 `FSETP` 加 2 条带谓词的 `FMUL`（`MUFU.EX2` 前后各一条） |
| 5 | `ex2.approx.f16x2` | `MUFU.EX2.F16`、`PRMT` | SFU + ALU 管线 · 第 5 级 | 第 7 章第 8 节 | `h2exp2` 或内联 PTX；1 条 PTX 拆成 2 条标量 `MUFU.EX2.F16` 加 1 条 `PRMT` 重排，不能减半 SFU 周期（据当时的反汇编，原始记录未留存；见第 7 章第 8 节；`bf16x2` 形式的 SASS 后缀未知） |
| 6 | `rcp.approx.ftz.f32`；`rsqrt.approx.ftz.f32`；`lg2.approx.ftz.f32` | `MUFU.RCP`、`MUFU.RSQ`、`MUFU.LG2` | SFU 管线 · 第 5 级 | 第 5 章第 1 节、第 7 章第 3 节 | `rsqrtf(x)`、`__log2f(x)` 或内联 PTX；仅 `.approx.ftz` 形态为单条 `MUFU`，代价是近似误差高于标准库函数 |
| 7 | `tanh.approx.f32` | `MUFU.TANH` | SFU 管线 · 第 5 级 | 第 10 章第 8 节 | 内联 PTX 或 `__tanhf(x)`（默认选项下标准库 `tanhf` 为软件展开；开 `-use_fast_math` 时 `tanhf` 换成 `__tanhf`）；1 对 1 编译为 `MUFU.TANH` |
| 8 | `mul.rn.bf16x2`；`fma.rn.bf16x2` | `HMUL2`、`HFMA2` | FMA 管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 3 节 | `__hmul2`、`__hfma2`；BF16 打包指令带 `.BF16_V2` 后缀 |
| 9 | `mad.lo.s32`；`mad.wide.u32`；`mul.hi.u32` | `IMAD`、`IADD3` | `IMAD` 走 FMA；`IADD3` 走 ALU · 第 5 级 | 第 5 章第 1 节、第 6 章第 3 节 | 整数 `a*b+c`、指针偏移 `ptr + i*size`；`IMAD` 兼具寄存器搬运（`IMAD.MOV`）、左移（`IMAD.SHL`）与 64 位宽乘加（`IMAD.WIDE`） |
| 10 | `add.s32`；`sub.s32`；`add.s64` | `IADD3`、`VIADD` | ALU 管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 2 节 | 整数 `a+b+c`、`a+b`；三输入加法用 `IADD3`，双输入用 `VIADD` 或 `IADD3`（第 3 操作数填 `RZ`），64 位加法拆成 `IADD3 + IADD3.X` |
| 11 | `and.b32`；`or.b32`；`xor.b32`；`lop3.b32` | `LOP3` | ALU 管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 2 节 | `a&b`、`a\|b`、`a^b`、`~a` 或内联 `lop3.b32`；`ptxas` 把任意 1–3 输入按位逻辑折叠成 1 条 `LOP3.LUT`（8 位真值表立即数） |
| 12 | `shl.b32`；`shr.b32`；`shf.l.wrap.b32`；`shf.r.clamp.b32` | `SHF`、`IMAD.SHL.U32` | ALU（或 FMA）管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 3 节、第 8 章第 3 节 | `a<<n`、`a>>n`、`__funnelshift_l`、`__funnelshift_r`；常数左移可编成 `SHF`（走 ALU）或 `IMAD.SHL.U32`（走 FMA 分担 ALU，见第 6 章第 3 节） |
| 13 | `prmt.b32` | `PRMT` | ALU 管线 · 第 6 级 | 第 6 章第 2 节、第 7 章第 10 节 | `__byte_perm(x,y,sel)` 或内联 PTX；从两个源寄存器的 8 个字节里按 4 位选择器挑出 4 个字节拼进目标寄存器 |
| 14 | `popc.b32` | `POPC` | 具体管线未测 · 第 5 级 | 第 8 章第 6 节 | `__popc` 或内联 `popc.b32`；统计 32 位掩码中 1 的个数（见第 8 章第 6 节） |
| 15 | `setp.ne.s32` | `ISETP` | ALU 管线 · 第 5 级 | 第 4 章第 4 节（图 4-3） | 整数比较 `a != b`；`ISETP` 把比较结果写进谓词寄存器 `P0..P6`（见图 4-3） |
| 16 | `cvt.rn.bf16.f32` | `F2F.BF16.F32`（有时也编为 `F2FP.BF16.F32.PACK_AB Rd, RZ, Rs`） | SFU 管线 · 第 6 级 | 第 5 章第 1 节、第 8 章第 16 节 | `__float2bfloat16(x)`；当落成 `F2F` 时走 SFU 管线，每条 warp 指令花 8 个周期（折合每周期 4 个通道），会和 `MUFU.EX2` 抢 SFU；若将两个值配成一对转换，可改用下一项的 `F2FP` |
| 17 | `cvt.rn.bf16x2.f32`；`cvt.rn.f16x2.f32` | `F2FP.BF16.F32.PACK_AB`、`F2FP.F16.F32.PACK_AB` | 非 SFU 管线（具体管线未测）· 第 6 级 | 第 7 章第 9 节、第 8 章第 16 节 | `__floats2bfloat162_rn(a,b)`、`__floats2half2_rn(a,b)`；1 条指令把两个 FP32 舍入打包进 1 个 32 位寄存器，不走 SFU 管线（见第 8 章第 16 节）；代价是要求两个待转换值已经在同一线程配成一对 |
| 18 | `cvt.f32.bf16` | `PRMT`、`IMAD.U32`、`SHF.L.U32` | ALU（或 FMA）管线 · 第 6 级 | 导引三第 1 节、第 6 章第 1 节 | `__bfloat162float(h)`、`__bfloat1622float2`；BF16 正好是 FP32 的高 16 位，编译为字节重排 `PRMT R0,RZ,0x7610,R0` 或移位（走 ALU，`IMAD.U32` 走 FMA），不走 SFU |
| 19 | `cvt.rn.satfinite.e4m3x2.f32` | `F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C` | 非 SFU 管线（具体管线未测）· 第 6 级 | 第 7 章第 9 节 | `__nv_cvt_float2_to_fp8x2` 或内联 PTX；把两个 FP32 饱和打包成 16 位 FP8（E4M3）对，并保留目标寄存器的另一半 |

---

## 4. 速查二：全局与片上访存、异步拷贝

先分清数据走哪条路：经加载存储单元 **LSU** 进出寄存器的 `LDG / STG`、绕过寄存器直写 SMEM 的 `LDGSTS`，以及单线程发起的 TMA，三条路的区别见第 3 章第 3 节。

直接作用于 L2 的访问属第 2 级：绕过 L1 的读写、L2 留存策略、L2 原子归约。经本 SM L1 的普通全局读写、SMEM、TMA 和 `cp.async` 属第 3 级。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 写法与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 20 | `ld.global.b32`；`ld.global.v4.b32`；`st.global.v4.b32` | `LDG.E`、`LDG.E.64`、`LDG.E.128`、`LDG.E.U16`、`STG.E`、`STG.E.64`、`STG.E.128` | LSU → L1 → L2 · 第 3 级 | 第 3 章第 2 节、第 3 章第 8 节 | `*p`、`p[i]`、`reinterpret_cast<uint4*>(p)[i]`（16 B）；位宽直接体现为后缀（`.64 / .128 / .U16`），均带 `desc[URn]` 操作数；若 16 B 向量只用其中几个分量，`ptxas` 会拆成标量 `LDG.E` |
| 21 | `ld.global.nc.u32`；`ld.global.nc.v4.f32` | `LDG.E.CONSTANT`、`LDG.E.128.CONSTANT`、`LDG.E.64.CONSTANT` | LSU → L1 只读路径 → L2 · 第 3 级 | 第 8 章第 8 节 | `__ldg(p)`、`const __restrict__ T* p` 或内联 `ld.global.nc`；`.nc` 编译为 `.CONSTANT` 后缀；只用于本 kernel 运行期间没人改写的数据（文档条件是“在 kernel 整个生命周期内只读”；`.nc` 走非一致的只读缓存，有人改写时可能读到旧值。开了 PDL 时，本书把与本 kernel 重叠运行的前序和后继 kernel 也算在内，属推论，见第 9 章第 5 节） |
| 22 | `ld.global.cg.v4.b32`；`st.global.cg.f32` | `LDG.E.STRONG.GPU`、`STG.E.STRONG.GPU` | LSU → L2（绕过 L1）· 第 2 级 | 第 2 章第 6 节 | `__ldcg(p)`、`__stcg(p,v)` 或内联 `ld / st.global.cg`，在 `sm_90a` 反汇编里编译成 `.STRONG.GPU`。注意 PTX 规范里 `.cg` 只是弱缓存提示，轮询同步标志要用 `ld.relaxed.gpu` 或 `ld.acquire.gpu`（见第 2 章第 6 节） |
| 23 | `ld.global.cs.v4.b32` | `LDG.E.EF`、`LDG.E.EF.128`、`LDG.E.EF.64` | LSU → L1 / L2 · 第 3 级 | 第 2 章第 4 节、附录 B 第 1 节 | `__ldcs(p)` 或内联 `ld.global.cs`；PTX 规范定义 `.cs` 在 L1 和 L2 都用 `evict_first`，在 `sm_90a` 反汇编里显示为 `.EF` 后缀与 `desc[URn]` 操作数（两者在硬件里怎样分管 L1 与 L2 未公开） |
| 24 | `createpolicy.fractional .L2::evict_first.b64`；`ld.global .L1::evict_first .L2::cache_hint` | `LDG.E.EF`、`LDG.E` | LSU + L2 · 第 2 级 | 第 2 章第 4 节、第 10 章第 2 节 | 内联 PTX；本书样本同时写了 L1 提示与 `createpolicy` 的 L2 留存提示，反汇编出现 `.EF / .EL` 后缀与 `desc[URn]` 操作数（L2 策略推测编码在 `desc[URn]` 里，未查明）；若被保留的数据本来就不会被挤出 L2，加提示不省时间（见第 2 章第 4 节） |
| 25 | `prefetch.global.L2 [a]`；`cp.async.bulk.prefetch.L2.global [a], size` | 本书反汇编未记录（操作码表有 `CCTL`、`UBLKPF`） | LSU → L2 · 第 2 级 | 第 7 章第 6 节、第 9 章第 4 节 | 内联 `prefetch.global.L2`（对照操作码表推断归属 `CCTL` 缓存控制指令，本书反汇编中未核实）；`cp.async.bulk.prefetch.L2` 由单个线程按给定字节数预取一段连续地址（对照操作码表推断为 `UBLKPF`，本书反汇编中同样未核实）。若预取过早、在用到前被流式数据冲出 L2，反而多读一次 HBM（见第 7 章第 6 节） |
| 26 | `ld.local`；`st.local` | 本书反汇编未记录 | LSU → L1 → L2（位于全局显存）· 第 3 级 | 第 3 章第 1 节、第 3 章第 6 节、第 10 章第 6 节 | 寄存器溢出（`ptxas -v` 报告 `spill`）、动态下标局部数组或未内联函数栈帧；出现局部内存读写说明寄存器读写退化成了显存往返 |
| 27 | `ld.param.*`；`ld.const` | `LDC` | SM 常量缓存 · 第 3 级 | 第 4 章第 4 节（图 4-3） | kernel 形参或 `__constant__` 变量；也可以把整个 warp 相同的常量直接读进统一寄存器 `UR`（见第 7 章第 7 节） |
| 28 | `ld.shared.b32`；`ld.shared.v4.b32`；`st.shared::cta.v4.b32` | `LDS`、`LDS.64`、`LDS.128`、`LDS.U8`、`LDS.U16`、`STS`、`STS.64`、`STS.128` | LSU → SMEM · 第 3 级 | 导引三第 4 节、第 3 章第 7 节 | `__shared__` 数组读写；1 对 1 带位宽后缀；同一波次不同通道撞上同一个 4 B bank 时会串行排队（见第 3 章第 7 节） |
| 29 | `cp.async.cg.shared.global [dst],[src],16`；`cp.async.ca.shared.global` | `LDGSTS.E.BYPASS.128`、`LDGSTS.E.BYPASS.128.ZFILL`、`LDGSTS.E`、`LDGSTS.E.64` | LSU（L2 直写 SMEM）· 第 3 级 | 第 3 章第 3 节、第 7 章第 5–6 节 | `__pipeline_memcpy_async` 或内联 `cp.async`；不经私有寄存器直写 SMEM；`.cg`（仅 16 B）编译为绕过 L1 的 `.BYPASS.128`，越界填零时生成 `.ZFILL`；代价是每个线程仍要自己算地址、发指令 |
| 30 | `cp.async.bulk.tensor .2d.shared::cluster.global .mbarrier::complete_tx::bytes` | 本书反汇编未记录 | SM 内专用 TMA 单元 · 第 3 级 | 第 3 章第 3 节、第 5 章第 6 节 | 内联 PTX；由 1 个线程发出，占 0 个数据寄存器；代价是主机端要先建描述符、块形状受限，且在 Hopper 上不能按离散行号收集（见第 3 章第 3 节、第 10 章第 10 节） |
| 31 | `cp.async.bulk.tensor .2d.global.shared::cta .bulk_group`；`cp.async.bulk.commit_group`；`cp.async.bulk.wait_group` | `UTMASTG.2D`、`UTMACMDFLUSH`、`DEPBAR.LE` | TMA 单元 · 第 3 级 | 第 3 章第 3 节、第 5 章第 7 节 | 内联 PTX；把 SMEM 分块异步写回全局显存：写回本身编译为 `UTMASTG`，`commit_group` 编译为 `UTMACMDFLUSH`，等待写回完成编译为 `DEPBAR.LE SB0, N`；发起写回前需先执行 `fence.proxy.async.shared::cta` 并完成块内同步（见第 5 章第 7 节） |
| 32 | `cp.reduce.async.bulk .tensor.2d.global.shared::cta .add.bulk_group` | `UTMAREDG.2D.ADD`、`UTMAREDG.3D.ADD` | TMA 单元 + 全局内存原子归约（推测在 L2） · 第 2 级 | 第 5 章第 7 节、第 6 章第 8 节、第 10 章第 8 节 | 内联 PTX；把 SMEM 分块直接发往全局内存做逐元素硬件原子加法（推测在 L2 完成，未查明），无需在 SM 内读回旧值；代价是浮点原子累加顺序不固定（见第 5 章第 7 节） |
| 33 | `cp.async.bulk .shared::cluster.global .mbarrier::complete_tx::bytes` | 本书反汇编未记录 | TMA 单元 · 第 3 级 | 第 3 章第 3 节 | 内联 PTX；免张量描述符的一维连续字节流搬运；要求地址与字节数按 16 B 对齐，搬非连续的多行时每行都要单独发 1 条（见第 3 章第 3 节） |

---

## 5. 速查三：屏障、集群共享内存与 Tensor Core

生产者用 TMA 或 `st.async` 搬数据、用 SM 同步单元 `SYNCS` 的 `mbarrier` 通知到达，消费者用 `HGMMA / QGMMA` 在 Tensor Core 上算；`mbarrier`、DSMEM 与 `wgmma` 分别见第 3 章第 5 节、第 7 章第 12 节与第 5 章第 5 节。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 写法与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 34 | `mbarrier.init.shared::cta.b64 [addr], count`；`mbarrier.inval.shared::cta.b64 [addr]` | `SYNCS.EXCH.64`、`SYNCS.CCTL.IV` | SM 同步单元（`SYNCS`）· 第 3 级 | 第 3 章第 5 节 | 内联 PTX；`init` 编译为 `SYNCS.EXCH.64`（写入 64 位屏障字），`inval` 编译为 `SYNCS.CCTL.IV` |
| 35 | `mbarrier.arrive.shared::cta.b64`；`mbarrier.arrive.expect_tx .shared::cta.b64 state,[addr],txcount` | `SYNCS.ARRIVE.TRANS64`、`SYNCS.ARRIVE.TRANS64.A1T0` | `SYNCS` 单元 · 第 3 级 | 第 3 章第 5 节、第 5 章第 6 节 | 内联 PTX；普通报到带 `.A1T0`（报到计数加 1、期望字节 0），登记 TMA 字节数用带寄存器操作数的 `.TRANS64`；若消费者在共享内存读（`LDS`）尚未返回前向 `empty[s]` 报到，会触发读后写竞态（见第 3 章第 5 节） |
| 36 | `mbarrier.try_wait.parity .shared::cta.b64 p,[addr],phase`；`mbarrier.test_wait` | `SYNCS.PHASECHK.TRANS64.TRYWAIT`、`SYNCS.PHASECHK.TRANS64` | `SYNCS` 单元 · 第 3 级 | 第 3 章第 5 节、第 5 章第 6 节 | 内联 PTX；`try_wait` 编译为 `.TRYWAIT`，在硬件里等待直到相位位翻转或超时，未翻转时由 `@!P BRA` 重试 |
| 37a | `fence.proxy.async .shared::cta` | `FENCE.VIEW.ASYNC.S` | LSU / 内存管线 · 第 3 级 | 第 3 章第 3 节、第 5 章第 7 节 | 普通线程写完 SMEM 后，必须执行这道异步代理栅栏，TMA 或 `wgmma` 的异步代理才能看到新数据 |
| 37b | `fence.proxy.async .global` | `FENCE.VIEW.ASYNC.G` | LSU / 内存管线 · 第 3 级 | 第 5 章第 7 节、第 8 章第 11 节 | 普通存储写全局内存、随后由 TMA（异步代理）读取或归约时，在本线程内衔接通用代理与异步代理（代理见第 3 章第 3 节）。读侧：放在 `ld.acquire.gpu` 之后、发 TMA 之前；写侧用法见第 8 章第 11 节 |
| 38 | `st.async.shared::cluster .mbarrier::complete_tx::bytes .v4.f32 [ra],{..},[mbar]` | 本书反汇编未记录 | 集群互连 + 远端 `mbarrier` · 第 2 级 | 第 7 章第 12 节、第 9 章第 3 节 | 内联 PTX；数据写入同集群远端 CTA 的 SMEM 后自动扣减远端 `mbarrier` 的期望字节数 |
| 39 | `barrier.cluster.arrive {.relaxed/.release}.aligned`；`barrier.cluster.wait {.acquire}.aligned` | `MEMBAR.ALL.GPU`、`ERRBAR`、`CGAERRBAR`、`UCGABAR_ARV`、`UCGABAR_WAIT`、`CCTL.IVALL` | 集群屏障单元 · 第 2 级 | 第 9 章第 3 节 | `cooperative_groups::this_cluster().sync()` 或内联 PTX；默认 `cluster.sync()` 编译为 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR + UCGABAR_ARV`（带 release 语义的报到）和 `UCGABAR_WAIT + CCTL.IVALL`（带 acquire 语义的等待，等待前序写被 L2 确认并使本 SM 的 L1 失效）。只有屏障前写的数据在屏障后不再被读，或数据另有完成通知（如 `st.async` 加 `mbarrier`）时，才能用 `.relaxed`；否则屏障不再保证数据的先后 |
| 40 | `mma.sync.aligned.m16n8k16 .row.col.f32.bf16.bf16.f32`（或 `.f16`） | `HMMA.16816.F32.BF16`、`HMMA.16816.F32` | 本 SMSP 的 Tensor Core · 第 5 级 | 第 5 章第 3 节、第 6 章第 3 节、第 7 章第 2 节 | 内联 PTX；1 对 1，操作数 $A$、$B$ 与累加器 $D$ 均在向量寄存器中 |
| 41 | `mma.sync.aligned.m16n8k32 .row.col.f32.e4m3.e4m3.f32` | `F2FP.F16.E4M3.UNPACK_B`、`HMMA.16816.F32` | 非 SFU 管线（具体管线未测）+ Tensor Core · 第 5 级 | 第 5 章第 3 节、第 7 章第 2 节 | 内联 PTX；`sm_90a` 无单 warp 原生 FP8 矩阵乘指令，1 条 PTX（$k = 32$）被 `ptxas` 拆为 `F2FP` 解包加 2 条 `HMMA.16816.F32`（各算 $k = 16$） |
| 42 | `wgmma.mma_async.sync.aligned .m64n64k16.f32.bf16.bf16` | `HGMMA.64x64x16.F32.BF16` | 全 SM 4 个 Tensor Core · 第 5 级 | 第 5 章第 3 节、第 5 章第 5 节 | 内联 PTX；1 对 1，$m = 64$ 固定，$n$ 取 $8..256$（步长 8），$A$ 与 $B$ 通过统一寄存器描述符 `gdesc[URn]` 从 SMEM 读取；代价是必须由 4 个 warp 一起发射且累加器占向量寄存器（见第 10 章第 10 节） |
| 43 | `wgmma.mma_async.sync.aligned .m64n32k32.f32.e4m3.e4m3` | `QGMMA.64x32x32.F32.E4M3.E4M3` | 全 SM 4 个 Tensor Core · 第 5 级 | 第 5 章第 3 节、第 7 章第 10 节 | 内联 PTX；FP8 `wgmma` 编译为原生 `QGMMA`（$k = 32$，吞吐见第 5 章第 3 节）；左矩阵 $A$ 从各 warp 的向量寄存器传入（RS 模式，见第 5 章第 3 节） |
| 44 | `wgmma.fence.sync.aligned` | `WARPGROUP.ARRIVE` | 执行单元未公开 · 第 4 级 | 第 5 章第 5 节、第 10 章第 10 节、附录 A 第 2 节 | 内联 PTX；1 对 1，在首次 `wgmma` 前执行，也在普通指令读写累加器寄存器（或 RS 模式下 $A$ 的寄存器分片）之后、下一条访问这些寄存器的 `wgmma` 之前执行，只保证这些寄存器的访问顺序；SMEM 里矩阵的先写后读要另用 `fence.proxy.async`（第 37a 项）。因为带 `.aligned`，warpgroup 的 4 个 warp 都必须执行同一条它；`.sync` 只让同一 warp 的 32 个线程等齐，4 个 warp 之间是否互相等待，PTX 没有写明（见附录 A 第 2 节） |
| 45 | `wgmma.commit_group .sync.aligned` | `HGMMA`、`QGMMA`（末尾带 `gsb0` 标志） | 最后一条 `HGMMA / QGMMA` 上的控制位 · 第 6 级 | 第 5 章第 5 节、第 6 章第 6 节 | 内联 PTX；无独立 SASS 指令，编码为该批次最后一条 `HGMMA / QGMMA` 指令末尾的 `gsb0` 组标志 |
| 46 | `wgmma.wait_group .sync.aligned N` | `WARPGROUP.DEPBAR.LE` | warpgroup 记分牌 · 第 4 级 | 第 5 章第 5 节、第 6 章第 6 节 | 内联 PTX；编译为 `WARPGROUP.DEPBAR.LE gsb0, N`，阻塞直到在途未完成的 `wgmma` 组数不超过 $N$；异步区间里混入改写累加器的普通指令或分支同步不一致时，编译器会在每条 `HGMMA` 后自动插 `WARPGROUP.DEPBAR.LE gsb0, 0`（见第 6 章第 6 节） |
| 47 | `ldmatrix.sync.aligned .m8n8.x4{.trans}.shared.b16` | `LDSM.16.M88.4`、`LDSM.16.M88`、`LDSM.16.M88.2`、`LDSM.16.MT88.4` | LSU → SMEM · 第 3 级 | 第 7 章第 10 节 | 内联 PTX；1 对 1，`.trans` 编译为带转置的 `.MT88`，一个 warp 按 $8 \times 8$ 小块把 SMEM 读进寄存器分片（见第 7 章第 10 节） |
| 48 | `stmatrix.sync.aligned .m8n8.x4{.trans}.shared.b16` | `STSM.16.M88.4`、`STSM.16.MT88.4`、`STSM.16.M88`、`STSM.16.MT88.2` | LSU → SMEM · 第 3 级 | 第 5 章第 7 节 | 内联 PTX；`ldmatrix` 的逆操作，把累加器寄存器分片按交错布局直接写入 SMEM，供随后 TMA 写回或块归约 |
| 49 | `setmaxnreg.inc.sync.aligned .u32 N`；`setmaxnreg.dec.sync.aligned .u32 N` | `USETMAXREG.TRY_ALLOC.CTAPOOL`（`inc`）、`USETMAXREG.DEALLOC.CTAPOOL`（`dec`） | SM 块内寄存器池分配器 · 第 3 级 | 第 3 章第 6 节、第 7 章第 7 节、第 10 章第 10 节 | 内联 PTX；$N$ 取 $24..256$（8 的倍数），`dec` 把生产者多余寄存器退回本 CTA 池，`inc` 为消费者申领寄存器（池里寄存器不够时阻塞）；要求整个 warpgroup 执行同一条指令（`.sync.aligned`，见附录 A 第 2 节） |

---

## 6. 速查四：warp 操作、内存栅栏、原子操作、网格交接与控制流

warp 内协作 `SHFL` 和 `VOTE` 属第 4 级。`SHFL` 由 LSU 管线发往 L1TEX 单元，见第 4 章第 5 节；`VOTE` 见第 7 章第 9 节与第 8 章第 6 节。全卡内存屏障、L2 原子与释放获取交接属第 2 级，见第 2 章第 6 节。PDL 网格交接与整网格同步属第 1 级，见第 1 章第 4 节、第 7 章第 12 节与第 8 章第 6 节。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 写法与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 50 | `shfl.sync.idx.b32`；`shfl.sync.bfly.b32`；`shfl.sync.up.b32`；`shfl.sync.down.b32` | `SHFL.IDX`、`SHFL.BFLY`、`SHFL.UP` | LSU → L1TEX 洗牌单元 · 第 4 级 | 第 4 章第 5 节 | `__shfl_sync(m,v,lane)`、`__shfl_xor_sync`、`__shfl_up_sync`、`__shfl_down_sync`；`__shfl_xor_sync` 编译为 `.BFLY`（蝶形洗牌） |
| 51 | `vote.sync.ballot.b32`；`vote.sync.any.pred`；`vote.sync.all.pred` | `VOTE.ANY` | warp 投票单元 · 第 4 级 | 第 7 章第 9 节、第 8 章第 6 节 | `__ballot_sync(m,p)`（见第 8 章第 6 节）、`__any_sync`（见第 7 章第 9 节）、`__all_sync`；`ballot` 编译为 `VOTE.ANY Rd, PT, Ps`（返回 32 位掩码） |
| 52 | `bar.warp.sync mask` | `WARPSYNC.ALL`、`WARPSYNC`、`WARPSYNC.COLLECTIVE`、`BSSY`、`BSYNC` | warp 调度器的重汇合单元 · 第 4 级 | 第 4 章第 4 节、第 10 章第 9 节 | `__syncwarp(mask)` 或内联 `bar.warp.sync`；全掩码在需要独立指令时编译为 `WARPSYNC.ALL`（结构化 `if` 后若已由 `BSSY / BSYNC` 汇合，编译器可省掉 `WARPSYNC`）；`BSSY / BSYNC` 是编译器在分化分支前后自动插入的汇合指令对（见第 4 章第 4 节、第 10 章第 9 节） |
| 53 | `bar.sync 0`（即 `barrier.sync.aligned 0`） | `BAR.SYNC.DEFER_BLOCKING` | SM 块内屏障单元 · 第 4 级 | 导引三第 4 节、第 4 章第 4 节 | `__syncthreads()`；1 对 1；到达不齐时，等待的时间等于最晚与最早到达之差 |
| 54 | `bar.sync id, n`；`bar.arrive id, n` | `BAR.SYNC.DEFER_BLOCKING`、`BAR.ARV` | SM 块内屏障单元 · 第 4 级 | 第 5 章第 7 节、第 7 章第 7 节 | 内联 `bar.sync id, n`、`bar.arrive id, n`（缺省带 `.aligned`；当只让 CTA 内的一部分 warp 参与时，这种写法跟规范里 `.aligned` 的字面要求如何对应，本书没有查明，见附录 A 第 2 节）；硬件屏障号 `id`（`0..15`）与线程数 `n` 编码为立即数（见第 5 章第 7 节、第 7 章第 7 节），`BAR.ARV` 只报到不等待 |
| 55 | `fence.acq_rel.cta`；`fence.acq_rel.gpu`；`fence.sc.cta`；`fence.sc.gpu` | `MEMBAR.ALL.CTA`、`MEMBAR.ALL.GPU`、`MEMBAR.SC.GPU`、`ERRBAR`、`CGAERRBAR`、`CCTL.IVALL` | LSU / 内存系统确认 · 第 2 级（`.cta` 属第 3 级） | 第 8 章第 11 节 | `__threadfence_block()`（`fence.sc.cta`）、`__threadfence()`（语义同 `fence.sc.gpu`；本书反汇编里内联 `fence.sc.gpu` 展开为 `MEMBAR.SC.GPU + ERRBAR + CGAERRBAR + CCTL.IVALL` 4 条，另一份 nvrtc 编译的 `__threadfence()` 前面还多 1 条 `MEMBAR.ALL.CTA`，共 5 条，未保留 PTX）；只需要 `acq_rel` 语义时，写内联 `fence.acq_rel.cta` / `fence.acq_rel.gpu`。全卡内存屏障等待此前的写入被 L2 确认并使本 SM 的 L1 失效。单向的生产者-消费者交接用 `acq_rel` 就够；`acq_rel` 不禁止本线程的写与之后对另一地址的读交换顺序，双方先写自己的标志、再读对方的标志互等（Dekker 情形）时，需要 `fence.sc` 禁止这一种交换 |
| 56 | `fence.release.gpu` | 本书反汇编未记录 | LSU / 内存系统确认 · 第 2 级 | 第 2 章第 6 节、第 9 章第 5 节 | 内联 PTX；它只规定顺序：本线程之前的读写排在它之后的强写入或 `griddepcontrol.launch_dependents` 之前。强写入指带内存序修饰的写，如 `st.relaxed`；普通 `st` 是弱写入。要让别的线程看见，需要接上两种写法之一：之后的一次强写入（如写标志的 `st.relaxed`，与对方的获取读成对，见第 2 章第 6 节）；或按程序顺序排在它之后的 `griddepcontrol.launch_dependents`（同一内存同步域，即默认设置；见第 9 章第 5 节）。`sm_90` 起支持 |
| 57 | `atom.global.add.u32`；`atom.global.add.f32`；`atom.global.exch`；`atom.global.inc` | `ATOMG.E.ADD.STRONG.GPU`、`ATOMG.E.ADD.S32.STRONG.GPU`、`ATOMG.E.EXCH.STRONG.GPU`、`ATOMG.E.INC.STRONG.GPU` | LSU → L2 原子单元 · 第 2 级 | 第 2 章第 6 节、第 6 章第 8 节 | 使用返回值的 `atomicAdd`、`atomicExch`、`atomicCAS`、`atomicInc`、`fetch_add`；在 L2 执行读改写并要等旧值返回，比只发不等的 `REDG` 多一次 L2 往返；按第 6 章第 8 节那个 kernel 的写法，BF16 标量原子加会被编成比较交换重试循环（把两个值打包的 `.bf16x2` 成对形式见第 5 章第 7 节） |
| 58 | `red.global.add.f32`；`red.global.add.v4.f32`；`red.global.add.s32`；`red.global.min.u64` | `REDG.E.ADD.S32.STRONG.GPU`、`REDG.E.ADD.F32.FTZ.RN.STRONG.GPU`、`REDG.E.ADD.F32x4.FTZ.RN.STRONG.GPU` | LSU → L2 归约单元 · 第 2 级 | 第 2 章第 7 节、第 7 章第 12 节、第 9 章第 3 节 | 忽略返回值的 `atomicAdd(p,v)`、向量 `atomicAdd(float2* / float4*)`；编译器自动转为只发不等的 `REDG`（代价是拿不到旧值） |
| 59 | `ld.acquire.gpu.global.u32 [a]`；`red.release.gpu.global.add.s32 [a],v`；`atom.acq_rel.gpu` | `LDG.E.STRONG.GPU`、`CCTL.IVALL`、`MEMBAR.ALL.GPU`、`ERRBAR`、`CGAERRBAR`、`REDG`、`ATOMG`、`ATOM` | LSU + L2 · 第 2 级 | 第 2 章第 6 节、第 7 章第 12 节、第 8 章第 11 节 | `cuda::atomic_ref<int, thread_scope_device>`（`store / load / fetch_add`）或内联 `ld.acquire.gpu`、`red.release.gpu`；PTX 只保证顺序；L1 失效、等 L2 确认是本 SM 的实现方式（一致性在 L2、L1 不一致见第 2 章第 6 节）：`ld.acquire.gpu` 展开为 `LDG.E.STRONG.GPU + CCTL.IVALL`，`red.release.gpu` 展开为 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR + REDG`；编译器不能确定地址在全局空间时（如 `cuda::atomic_ref` 作用在普通指针上），`acq_rel` 的 `fetch_add` 生成通用地址的 `ATOM.E.ADD.S32.STRONG.GPU`，前后带 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR` 与 `CCTL.IVALL` |
| 60 | `griddepcontrol.wait`；`griddepcontrol.launch_dependents` | `ACQBULK`、`PREEXIT` | 网格硬件派发器与 SM · 第 1 级 | 第 1 章第 4 节、第 8 章第 8 节、第 9 章第 5 节 | `cudaGridDependencySynchronize()`、`cudaTriggerProgrammaticLaunchCompletion()` 或内联 `griddepcontrol`（见第 8 章第 8 节）。`wait → ACQBULK`：阻塞直到前序网格完成且写入可见。`launch_dependents → PREEXIT`：所有 CTA 发出它或退出后，后继网格可以被调度。按 PTX 规范，若前序线程在 `launch_dependents` 之前先执行 `fence.release.gpu`（两个网格在同一内存同步域，即默认设置），它此前的写入从后继网格启动起即可见；否则只保证在后继执行 `griddepcontrol.wait` 之后可见（见第 9 章第 5 节）。触发过早会让后继占着 SM 空等（见第 1 章第 4 节、第 7 章第 11 节） |
| 61 | 标准库实现（未公开，本书推断：全局原子计数 + 全卡内存屏障 + 轮询 + `bar.sync`） | 本书反汇编未记录 | L2 原子单元 + 各 SM 轮询 · 第 1 级 | 第 8 章第 6 节 | `cooperative_groups::this_grid().sync()`（配合 `cudaLaunchCooperativeKernel`）；本书推断由标准库组合块内屏障、全卡内存屏障与 L2 计数器轮询实现（轮询用哪种读取未核对），要求全网格所有 CTA 同时驻留（见第 2 章第 6 节、第 7 章第 12 节、第 8 章第 6 节） |
| 62 | `mov.u64 d, %clock64`；`mov.u64 d, %globaltimer` | `CS2R` | 特殊寄存器读取 · 第 4 级 | 第 2 章第 2 节、第 10 章第 5–6 节 | `clock64()`、`clock()` 或内联读取 `%globaltimer`、`%clock64`；本书反汇编里 `clock64()` 编译为 `CS2R R2, SR_CLOCKLO`，读 `%globaltimer` 编译为 `CS2R R4, SR_GLOBALTIMERLO`，各用 1 条指令读出 64 位；`clock()` 只读 32 位的 `%clock`，本书反汇编未记录（`%globaltimer` 最小步长实测 32 ns，见第 10 章第 5 节） |
| 63 | `bra`；`bra.uni`；`exit` | `BRA`、`EXIT`、`BSSY`、`BSYNC` | 分支与发射单元 · 第 4 级 | 第 4 章第 4 节、第 10 章第 9 节 | `if / for`、`return`；整个 warp 一致的跳转标 `.U`，分化分支包在 `BSSY ... BSYNC` 内（分支分化代价见第 4 章第 4 节、第 10 章第 9 节） |
| 64 | `mov.u32 %tid.x`；`mov.u32 %ctaid.x`；`mov.u32 %ntid.x`；`mov.u32 %nctaid.x` | `S2R`、`R2UR` | 特殊寄存器与统一寄存器文件 · 第 4 级 | 导引三第 3 节、第 7 章第 7 节 | `threadIdx.x`、`blockIdx.x`、`blockDim.x`、`gridDim.x`；`S2R` 读入每线程向量寄存器 `R`，`R2UR` 把向量寄存器值拷入整个 warp 共享的统一寄存器 `UR`（见第 7 章第 7 节） |

---

## 7. 按 SASS 助记符查（索引）

- `ACQBULK` → 速查四 第 60 项
- `ATOM` → 速查四 第 59 项
- `ATOMG` → 速查四 第 57 项；速查四 第 59 项
- `BAR` → 速查四 第 53 项；速查四 第 54 项
- `BRA` → 速查四 第 63 项
- `BSSY` → 速查四 第 52 项；速查四 第 63 项
- `BSYNC` → 速查四 第 52 项；速查四 第 63 项
- `CCTL` → 速查二 第 25 项；速查三 第 39 项；速查四 第 55 项；速查四 第 59 项
- `CGAERRBAR` → 速查三 第 39 项；速查四 第 55 项；速查四 第 59 项
- `CS2R` → 速查四 第 62 项
- `DEPBAR` → 速查二 第 31 项（TMA 写回的 `wait_group`）；wgmma 的等待是 `WARPGROUP.DEPBAR.LE`，见 `WARPGROUP` → 速查三 第 46 项
- `ERRBAR` → 速查三 第 39 项；速查四 第 55 项；速查四 第 59 项
- `EXIT` → 速查四 第 63 项
- `F2F` → 速查一 第 16 项
- `F2FP` → 速查一 第 16 项；速查一 第 17 项；速查一 第 19 项；速查三 第 41 项
- `FADD` → 速查一 第 2 项
- `FENCE` → 速查三 第 37a、37b 项
- `FFMA` → 速查一 第 1 项
- `FMUL` → 速查一 第 2 项；速查一 第 3 项；速查一 第 4 项
- `FSETP` → 速查一 第 4 项
- `HFMA2` → 速查一 第 8 项
- `HGMMA` → 速查三 第 42 项；速查三 第 45 项
- `HMMA` → 速查三 第 40 项；速查三 第 41 项
- `HMUL2` → 速查一 第 8 项
- `IADD3` → 速查一 第 9 项；速查一 第 10 项
- `IMAD` → 速查一 第 9 项；速查一 第 12 项；速查一 第 18 项
- `ISETP` → 速查一 第 15 项
- `LDC` → 速查二 第 27 项
- `LDG` → 速查二 第 20 项；速查二 第 21 项；速查二 第 22 项；速查二 第 23 项；速查二 第 24 项；速查四 第 59 项
- `LDGSTS` → 速查二 第 29 项
- `LDS` → 速查二 第 28 项
- `LDSM` → 速查三 第 47 项
- `LOP3` → 速查一 第 11 项
- `MEMBAR` → 速查三 第 39 项；速查四 第 55 项；速查四 第 59 项
- `MUFU` → 速查一 第 3 项；速查一 第 4 项；速查一 第 5 项；速查一 第 6 项；速查一 第 7 项
- `POPC` → 速查一 第 14 项
- `PREEXIT` → 速查四 第 60 项
- `PRMT` → 速查一 第 5 项；速查一 第 13 项；速查一 第 18 项
- `QGMMA` → 速查三 第 43 项；速查三 第 45 项
- `R2UR` → 速查四 第 64 项
- `REDG` → 速查四 第 58 项；速查四 第 59 项
- `S2R` → 速查四 第 64 项
- `SHF` → 速查一 第 12 项；速查一 第 18 项
- `SHFL` → 速查四 第 50 项
- `STG` → 速查二 第 20 项；速查二 第 22 项
- `STS` → 速查二 第 28 项
- `STSM` → 速查三 第 48 项
- `SYNCS` → 速查三 第 34 项；速查三 第 35 项；速查三 第 36 项
- `UBLKPF` → 速查二 第 25 项
- `UCGABAR` → 速查三 第 39 项
- `USETMAXREG` → 速查三 第 49 项
- `UTMACMDFLUSH` → 速查二 第 31 项
- `UTMAREDG` → 速查二 第 32 项
- `UTMASTG` → 速查二 第 31 项
- `VIADD` → 速查一 第 10 项
- `VOTE` → 速查四 第 51 项
- `WARPGROUP` → 速查三 第 44 项；速查三 第 46 项
- `WARPSYNC` → 速查四 第 52 项

---

**带走一句话：** 陌生的 SASS 指令按助记符在本附录里查：它来自哪种源码写法、走哪条管线、属于第几级、本书哪一节用过它。要定位到具体哪一行源码，用 `-lineinfo` 编译后在 NCU 的源码视图里看，见第 10 章第 7 节。

**接下来的问题：** 书里的一个术语在哪一节讲过？→ 附录 C。
