# 附录 B：一条不认识的 SASS 指令，从哪里来、走哪条硬件管线、属于第几级？

**本书地图：** 前言 → 导引一 → 导引二 → 导引三 → 第 1 章 [第 1 级] → 第 2 章 [第 2 级] → 第 3 章 [第 3 级] → 第 4 章 [第 4 级] → 第 5 章 [第 5 级] → 第 6 章 [第 6 级] → 第 7–9 章 → 第 10 章 → **【附录 B：速查】**

附录 A 末尾留了个问题：碰到一条不认识的 SASS 指令，它从哪里来、走哪条硬件管线、属于第几级？本附录收录正文、配图及附录 D 讲到的 PTX 或源码写法；SASS 一列给出本书反汇编里见到的助记符，只有第 3、23、29、31 项的助记符取自早期反汇编记录记录（并注明“原始样本未留存”或“映射来自早期反汇编记录”）；没有留存反汇编样本的标为“本书反汇编未记录”（表示未留存样本，不代表从未见过该操作码），部分行另注操作码表里的对应操作码。下面按功能分成四组速查表，末尾附有按助记符字母排序的索引。

每一项按它用到的硬件定级；“本书在哪里用到”一列写讲到它或用到它的那一节：

- **第 1 级**：网格的启动与交接（见第 1 章），以及整网格同步（见第 2 章第 6 节、第 7 章第 12 节与第 8 章第 6 节）。
- **第 2 级**：直接作用于中央 L2 或跨 SM 的操作，包括 L2 留存提示、L2 原子与归约、全卡内存屏障与释放获取（见第 2 章），以及 L2 与张量描述符预取（见第 7 章第 6 节与第 9 章第 5 节）、集群与 DSMEM（见第 7 章第 12 节与第 9 章第 3 节）。
- **第 3 级**：单个 SM 内部的数据通路与资源，包括经本 SM L1 的普通全局读写、SMEM、TMA、`cp.async`、`mbarrier`、`setmaxnreg` 与块内内存栅栏（见第 3 章；块内内存栅栏另见第 8 章第 11 节），以及常量缓存（见第 4 章第 4 节）。
- **第 4 级**：SMSP 调度，包括块内与 warp 内屏障、洗牌与整数归约、代表线程选举、分支、记分牌等待（见第 3–4 章与第 7 章）、睡眠让槽（见第 7 章第 12 节、第 8 章第 7 节与第 10 章第 7 节）和投票（见第 7 章第 9 节与第 8 章第 6 节），以及线程与集群序号（见导引三第 2 节与第 9 章第 3 节）和时钟（见第 10 章第 5 节）等特殊寄存器读取。
- **第 5 级**：执行管线与 Tensor Core，包括 FMA、ALU、SFU 算术与超越函数指令，以及矩阵乘指令（原理见第 5 章，SASS 助记符 `HMMA`、`HGMMA`、`QGMMA` 见第 6 章第 5 节与本附录）。
- **第 6 级**：比特与机器码，包括位重排与打包类型转换、SASS 编码，以及编在控制位里的组标志，见第 6 章。

---

## 1. 一条 SASS 指令怎样拆开读？

<!-- FIG appB-a: 图 B-1 从 CUDA C++ 到 PTX 再到 SASS：一条指令怎样拆读与降低——上方拆读与降低条带切换模式 1 或模式 2–10（无步骤编号、无红圈红框）：模式 1 将内联 PTX（ld.global.L1::evict_first.L2::cache_hint.v4.b32 …）经 ptxas 编译成运行期取入 SM 指令缓存的 1 条 128 位（16 B，PC 步长 0x10）SASS 指令字 LDG.E.EF.128 R8, desc[UR12][R8.64]，并用括号标出同一次发射一起译码的 7 个语法字段（字段位置仅为示意，不代表实际位序：操作码 LDG、64 位地址 .E、优先淘汰 .EF［作用于 L1 还是 L2 未公开］、每线程 16 B 的 .128［1 个 warp 合并请求 32 × 16 B = 512 B 即 16 个扇区，本条指令内修饰字段占 0 条额外指令］、由 long_scoreboard 锁定的连续 4 个目的寄存器 R8..R11、warp 共享统一寄存器里的 64 位描述符 desc[UR12]［占 0 个向量寄存器 R，L2 留存策略位推测编在其中、格式未查明］，以及发射时先读 R8:R9 旧值拼出的地址 [R8.64]；gemv v6 → v7 每线程挂起 8 条读取把 long_scoreboard 从 12.9 压到 8.1 clk/inst，耗时从 21.63 降到 15.15 µs）；模式 2–10 按第 2 节三类降低关系对照九个案例的 CUDA C++、PTX、sm_90a SASS 序列与条数汇总标签——第一类“没有独立 SASS 指令”：模式 2（wgmma.commit_group → ptxas 编码时写进末条 HGMMA / QGMMA 指令字的 gsb0 组标志，占 0 条独立 SASS 指令，每 4-warp warpgroup 少发 4 次、少 1 条 16 B 指令字，对比 cp.async.bulk.commit_group 单独编出 1 条 UTMACMDFLUSH）；第二类“拆成一串 SASS 指令”：模式 3（单 warp FP8 mma.sync … m16n8k32.e4m3 → 多条 F2FP.F16.E4M3.UNPACK_B 解包［示意排在前面，SMSP 0 内具体管线没有测，未排除 SFU］+ 2 × HMMA.16816.F32，无复用时 12 条 F2FP + 2 条 HMMA 共 14 条，改用 4-warp wgmma 才 1 对 1 编成原生 QGMMA.64x32x32）、模式 4（ex2.approx.f16x2 → 2 × MUFU.EX2.F16［占 4 通道 SFU 共 2 × 8 = 16 个发射周期，省 0 个 SFU 周期］+ 1 × PRMT 共 3 条 SASS，据当时的反汇编、原始记录未留存，对比 ex2.approx.ftz.f32 为 1 条裸 MUFU.EX2 而漏写 .ftz 变成 4 条）、模式 5（__fdividef / div.approx.f32 → 1 条走 SFU 的 MUFU.RCP + 1 条走 FMA 的 FMUL 共 2 条 SASS，映射来自早期反汇编记录、原始样本未留存，省去 IEEE div.rn.f32 的牛顿迭代与分支）、模式 8（__threadfence() / fence.sc.gpu → 4–5 条 SASS：NVRTC 等工具链 5 条样本前置可选 [MEMBAR.ALL.CTA]［nvcc 12.8 的 4 条序列无，多出原因未查明］+ MEMBAR.SC.GPU［有 1 笔在途写多约 200 clk 属推断］+ ERRBAR + CGAERRBAR［两者执行单元与硬件位置未公开］+ CCTL.IVALL［无热数据直接 3.0 clk，16 KiB 热 L1 重填 +276.8 clk］；nvcc 12.8 的 4 条序列实测 0 笔在途写 269.0 clk、1 笔在途写 476 clk，fence.acq_rel.gpu 为 475 clk，5 条序列周期没有测）；第三类“换了名字或变成后缀 / 操作数”：模式 6（忽略返回值的 atomicAdd → red.global.add → 经 LSU → L1TEX → L2 的 1 条 REDG，0 个目的寄存器、0 次记分牌等待，relaxed REDG 发射代价没有单测，省去返回等待属推断；对比读目的寄存器时 relaxed ATOMG 有 1 笔在途写往返 506 clk、0 笔在途写 501 clk、u32 依赖链 497.2 clk）、模式 7（.cg → 不在 L1 分配的 LDG.E.STRONG.GPU、.cs → LDG.E.EF［映射来自早期反汇编记录，原始样本未留存］、.nc → 经 L1TEX 只读通路的 LDG.E.CONSTANT，以及 createpolicy → 操作数 desc[URn]：每个加载本身仍是 1 条 LDG，普通读取也有 desc[URn]，策略构造提到循环外、循环内另有条数没有单列的传提示指令，L2 策略位推测编在 desc[URn] 内、格式未查明；流式数据超 60 MiB 时保住 98.8%–100% 的 L2 重读带宽，已在 L2 时 gemv v3 → v4 从 43.34 反慢约 1 µs 到 44.29 µs）、模式 9（__bfloat162float / cvt.f32.bf16 → 1 条走 16 通道 ALU 的 PRMT 或 SHF.L.U32，或走 FMA 整数重半边的 IMAD.U32，2 周期/warp，占 0 条 SFU 指令）、模式 10（__floats2bfloat162_rn / cvt.rn.bf16x2.f32 → 1 条非 SFU 管线的 F2FP.BF16.F32.PACK_AB，SFU 标“不走这里”，具体走 ALU / FMA / LSU / Tensor Core 哪条管线没有测，第 8 章第 16 节全核 SFU 利用率从 5.74% 降到 3.08%、整层捆绑提速 0.33%、单项耗时占比没有单测）。中段三维结构示意图（尺寸与间距不按容量或延迟比例）连接 6 组共享 HBM 堆栈（哪组存哪些字节未指定）→ 60 MiB 共享 L2 → 1 个 SM（1 / 132，含合一 L1 / SMEM 即 L1TEX、指令缓存、SMSP 1–3，以及展开的 SMSP 0 调度器［1 条/周期］、向量寄存器 R、统一寄存器 UR、4 通道 SFU［8 周期/warp］、32 通道 FMA［1 周期/warp］、16 通道 ALU［2 周期/warp］、每 SMSP 1 个共 4 个 Tensor Core 与 LSU，未公开、没有测或格式未查明处用虚线标出）；底部步骤顺序时间线只表示步骤先后、不是时间比例，右上双行读数同步汇总当前模式的映射关系与实测指标。 -->

**SASS 助记符由操作码加修饰后缀拼成，操作数依次写出目的寄存器、内存描述符和 64 位地址。**

从源码到机器码一共走三层：CUDA C++ → PTX → `ptxas` 生成的 **128 位**（**16 B**）SASS 指令字（运行期装入 SM 的**指令缓存**，程序计数器每条指令前进 `0x10` = 16 B），见第 6 章第 5 节。我们拿图 B-1 模式 1 的 `LDG.E.EF.128 R8, desc[UR12][R8.64]` 来拆开读。它是一条带留存提示的 16 B 宽流式全局读取，见第 2 章第 4 节与第 3 章第 3 节：

- **`LDG`**：**操作码**，表示全局显存读取；
- **`.E`**：**修饰后缀**，表示使用 64 位扩展地址；
- **`.EF`**：带 `evict_first` 优先淘汰提示的后缀；NVIDIA 没有公开它作用于 L1 还是 L2（本书样本的 PTX 同时写了 `L1::evict_first` 与 L2 留存策略，反汇编只出现一个 `.EF` 后缀和一个 `desc[URn]` 操作数）；
- **`.128`**：每个线程一次读取 128 位（**16 B**），装进 `R8..R11` 四个连续的 32 位向量寄存器；
- **`desc[UR12]`**：放在统一寄存器 `UR` 里的 64 位**内存描述符**；我们推测第 2 章第 4 节的 L2 留存提示（在 PTX 里用 `createpolicy` 生成）编码在这个描述符里（未查明）。`UR` 是整个 warp 共享的寄存器（见第 7 章第 7 节），助记符以 `U` 开头的指令读写它；
- **`[R8.64]`**：由 `R8:R9` 寄存器对拼出的 64 位字节地址；
- **`.reuse`**（常见于多源算术指令的源寄存器后，如 `R20.reuse`）：官方最佳实践指南说明寄存器文件分存储体，冲突由编译器和硬件调度器规避、程序员无法直接控制；公开逆向研究（Volta / Turing）表明 `.reuse` 编在 16 B 指令控制位里提示硬件复用刚读过的操作数，Hopper 的存储体个数与位编码 NVIDIA 未公开。

---

## 2. 一条 PTX 为什么不一定变成一条同名的 SASS？

**`ptxas` 会把一条 PTX 编成 0 条独立指令、拆成一串指令，或者换成另一个名字与操作数。**

- **第一类：没有独立指令。** 比如 `wgmma.commit_group`，见第 5 章第 6 节与第 6 章第 5 节，在 SASS 里不占单独的指令字，而是直接编码成这一批最后一条 `HGMMA` / `QGMMA` 末尾的组标志，见速查三第 45 项（相反，TMA 写回或归约用的 `cp.async.bulk.commit_group` 会单独编出一条 `UTMACMDFLUSH`“TMA 命令冲刷”指令，见速查二第 31 项）。
- **第二类：拆成一串指令。** 单 warp 的 FP8 矩阵乘 `mma.sync … e4m3` 在 `sm_90a` 上先用 `F2FP` 把 FP8 解包成 FP16，再连发 **2** 条 `HMMA`，见速查三第 41 项。第 9 章第 3 节的集群屏障（`barrier.cluster.arrive/wait`）编译为 `UCGABAR_ARV` / `UCGABAR_WAIT`，默认形式还在报到前加全卡内存屏障（`MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR`），在等待后加 `CCTL.IVALL`，见速查三第 39 项。
- **第三类：换了名字或变成操作数。** 全局读取的缓存修饰符在 SASS 里会变成后缀，还有一些我们推测编进了描述符操作数。例如第 2 章第 4 节带 `createpolicy` 的读取在 SASS 里变成 `.EF / .EL` 后缀，它的 L2 策略我们推测编码在 `LDG` 的 `desc[URn]` 操作数里（未查明；不带提示的普通读取也有 `desc[URn]`），见速查二第 24 项。

为什么对不上号？因为 PTX 规范只规定语义，不规定具体的 SASS 指令序列。全卡内存屏障里的 `ERRBAR`、`CGAERRBAR`，NVIDIA 并没有公开硬件细节；本书只记录 `sm_90a` 反汇编里看到的序列，换了编译器版本之后记得重新核对。

---

## 3. 速查一：算术、超越函数与类型转换

查这一组指令时，先看它走 FMA、ALU 还是 SFU 管线，见第 5 章第 1 节。算术与超越函数属第 5 级，位重排与打包类型转换属第 6 级。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 写法与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `fma.rn.f32`（`mad.rn.f32` 同） | `FFMA` | FMA 管线 · 第 5 级 | 导引三第 1 节、第 5 章第 1 节 | `fmaf(a,b,c)`、`__fmaf_rn` 或默认收缩的 `a*b+c`；1 对 1 编译为 `FFMA` |
| 2 | `add.f32`；`mul.f32` | `FADD`、`FMUL` | FMA 管线 · 第 5 级 | 导引三第 3 节、第 5 章第 1 节 | `a+b`、`a*b`、`__fadd_rn`、`__fmul_rn`；用 `__fadd_rn` / `__fmul_rn` 可阻止编译器把 `a*b+c` 收缩为 `FFMA`，代价是多发 1 条指令 |
| 3 | `div.full.f32`；`div.approx.f32` | `MUFU.RCP`、`FMUL` | SFU + FMA 管线 · 第 5 级 | 正文未单列（`div.approx.f32` → `MUFU.RCP + FMUL` 映射来自早期反汇编记录，原始样本未留存；近似除法语义见 PTX 规范；图 B-1 模式 5） | `div.approx.f32`（`__fdividef(a,b)` 或开启 `-use_fast_math` 时的 `a/b`）展开为倒数近似 `MUFU.RCP` 加乘法 `FMUL`；`div.full.f32`（`-prec-div=false` 时的 `a/b`）在此之外还要缩放操作数以覆盖全范围，指令更多（本书无反汇编样本）。两者都比 IEEE 除法 `div.rn.f32` 省去牛顿迭代与分支，代价是精度低于 IEEE 标准除法 |
| 4 | `ex2.approx.f32`；`ex2.approx.ftz.f32` | `MUFU.EX2`、`FMUL`、`FSETP` | SFU 管线 · 第 5 级 | 第 7 章第 9 节 | `exp2f(x)`、`__expf(x)` 或内联 PTX；`.ftz` 把非规格化数当 0 处理（非规格化数见第 6 章第 5 节），编译为裸的 1 条 `MUFU.EX2`；漏写 `.ftz` 会多出 3 条修正指令：1 条 `FSETP` 加 2 条带谓词的 `FMUL`（`MUFU.EX2` 前后各一条） |
| 5 | `ex2.approx.f16x2` | `MUFU.EX2.F16`、`PRMT` | SFU + ALU 管线 · 第 5 级 | 第 7 章第 8 节 | `h2exp2` 或内联 PTX；1 条 PTX 拆成 2 条标量 `MUFU.EX2.F16` 加 1 条 `PRMT` 重排，不能减半 SFU 周期（据当时的反汇编，原始记录未留存；见第 7 章第 8 节；`bf16x2` 形式的 SASS 后缀未知） |
| 6 | `rcp.approx.ftz.f32`；`rsqrt.approx.ftz.f32`；`lg2.approx.ftz.f32` | `MUFU.RCP`、`MUFU.RSQ`、`MUFU.LG2` | SFU 管线 · 第 5 级 | 第 5 章第 1 节、第 7 章第 3 节 | `rsqrtf(x)`、`__log2f(x)` 或内联 PTX；仅 `.approx.ftz` 形态为单条 `MUFU`，代价是近似误差高于标准库函数 |
| 7 | `tanh.approx.f32` | `MUFU.TANH` | SFU 管线 · 第 5 级 | 第 10 章第 8 节 | 内联 PTX 或 `__tanhf(x)`（默认选项下标准库 `tanhf` 为软件展开；开 `-use_fast_math` 时 `tanhf` 换成 `__tanhf`）；1 对 1 编译为 `MUFU.TANH` |
| 8 | `mul.rn.bf16x2`；`fma.rn.bf16x2` | `HMUL2`、`HFMA2` | FMA 管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 5 节 | `__hmul2`、`__hfma2`；BF16 打包指令带 `.BF16_V2` 后缀 |
| 9 | `mad.lo.s32`；`mad.wide.u32`；`mul.hi.u32` | `IMAD`、`IADD3` | `IMAD` 走 FMA；`IADD3` 走 ALU · 第 5 级 | 第 5 章第 1 节、第 6 章第 2 节 | 整数 `a*b+c`、指针偏移 `ptr + i*size`；`IMAD` 兼具寄存器搬运（`IMAD.MOV`）、左移（`IMAD.SHL`）与 64 位宽乘加（`IMAD.WIDE`） |
| 10 | `add.s32`；`sub.s32`；`add.s64` | `IADD3`、`VIADD`、`IMAD.IADD` | ALU（`IADD3`）或 FMA 管线重半边（`VIADD`、`IMAD.IADD`）· 第 5 级 | 第 5 章第 1 节、第 6 章第 2 节 | 整数 `a+b+c`、`a+b`；三输入加法用 `IADD3`（走 ALU）；双输入多编成走 FMA 重半边的 `VIADD`（见第 6 章第 2 节），也可能是 `IMAD.IADD` 或第 3 操作数填 `RZ` 的 `IADD3`；64 位加法拆成 `IADD3 + IADD3.X` |
| 11 | `and.b32`；`or.b32`；`xor.b32`；`lop3.b32` | `LOP3` | ALU 管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 2 节 | `a&b`、`a\|b`、`a^b`、`~a` 或内联 `lop3.b32`；`ptxas` 把任意 1–3 输入按位逻辑折叠成 1 条 `LOP3.LUT`（8 位真值表立即数） |
| 12 | `shl.b32`；`shr.b32`；`shf.l.wrap.b32`；`shf.r.clamp.b32` | `SHF`、`IMAD.SHL.U32` | ALU（或 FMA）管线 · 第 5 级 | 第 5 章第 1 节、第 6 章第 2 节、第 8 章第 3 节 | `a<<n`、`a>>n`、`__funnelshift_l`、`__funnelshift_r`；常数左移可编成 `SHF`（走 ALU）或 `IMAD.SHL.U32`（走 FMA 分担 ALU，见第 6 章第 2 节） |
| 12a | `dp4a.s32.s32`；`dp4a.u32.u32` | 本书反汇编未记录（操作码表为 `IDP` / `IDP4A`） | FMA 管线重半边（按剖析器手册；发射间隔没有测）· 第 5 级 | 第 5 章第 1 节；本书模型未用（见附录 D 第 3 节） | `__dp4a(a,b,c)` 或内联 PTX；单通道一次把 4 对打包的 8 位整数做点积并累加进 32 位整数，按剖析器手册走 FMA 管线的重半边（与 `IMAD` 同半边，不走 ALU） |
| 13 | `prmt.b32` | `PRMT` | ALU 管线 · 第 6 级 | 第 6 章第 2 节、第 7 章第 10 节 | `__byte_perm(x,y,sel)` 或内联 PTX；从两个源寄存器的 8 个字节里按 4 位选择器挑出 4 个字节拼进目标寄存器 |
| 14 | `popc.b32` | `POPC` | 具体管线未测 · 第 5 级 | 第 8 章第 6 节 | `__popc` 或内联 `popc.b32`；统计 32 位掩码中 1 的个数（见第 8 章第 6 节） |
| 15 | `setp.ne.s32` | `ISETP` | ALU 管线 · 第 5 级 | 第 4 章第 4 节（图 4-3） | 整数比较 `a != b`；`ISETP` 把比较结果写进谓词寄存器 `P0..P6`（见图 4-3） |
| 16 | `cvt.rn.bf16.f32` | `F2F.BF16.F32`（有时也编为 `F2FP.BF16.F32.PACK_AB Rd, RZ, Rs`） | SFU 管线 · 第 6 级 | 第 5 章第 1 节、第 8 章第 16 节 | `__float2bfloat16(x)`；当落成 `F2F` 时走 SFU 管线，每条 warp 指令花 8 个周期（折合每周期 4 个通道），会和 `MUFU.EX2` 抢 SFU；若将两个值配成一对转换，可改用下一项的 `F2FP` |
| 17 | `cvt.rn.bf16x2.f32`；`cvt.rn.f16x2.f32` | `F2FP.BF16.F32.PACK_AB`、`F2FP.F16.F32.PACK_AB` | 非 SFU 管线（具体管线未测）· 第 6 级 | 第 7 章第 9 节、第 8 章第 16 节 | `__floats2bfloat162_rn(a,b)`、`__floats2half2_rn(a,b)`；1 条指令把两个 FP32 舍入打包进 1 个 32 位寄存器，不走 SFU 管线（见第 8 章第 16 节）；代价是要求两个待转换值已经在同一线程配成一对 |
| 18 | `cvt.f32.bf16` | `PRMT`、`IMAD.U32`、`SHF.L.U32` | ALU（或 FMA）管线 · 第 6 级 | 导引三第 1 节、第 6 章第 1 节 | `__bfloat162float(h)`、`__bfloat1622float2`；BF16 正好是 FP32 的高 16 位，编译为字节重排 `PRMT R0,RZ,0x7610,R0` 或移位（走 ALU，`IMAD.U32` 走 FMA），不走 SFU |
| 19 | `cvt.rn.satfinite.e4m3x2.f32` | `F2FP.SATFINITE.E4M3.F32.PACK_AB_MERGE_C` | 具体管线没有测 · 第 6 级 | 第 7 章第 9 节 | `__nv_cvt_float2_to_fp8x2` 或内联 PTX；把两个 FP32 饱和打包成 16 位 FP8（E4M3）对，并保留目标寄存器的另一半 |

---

## 4. 速查二：全局与片上访存、异步拷贝

先分清数据走哪条路：经加载存储单元 **LSU** 进出寄存器的 `LDG / STG`、绕过寄存器直写 SMEM 的 `LDGSTS`，以及单线程发起的 TMA，三条路的区别见第 3 章第 5 节。

直接作用于 L2 的访问属第 2 级：绕过 L1 的读写、L2 留存策略、L2 原子归约。经本 SM L1 的普通全局读写、SMEM、TMA 和 `cp.async` 属第 3 级。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 写法与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 20 | `ld.global.b32`；`ld.global.v4.b32`；`st.global.v4.b32` | `LDG.E`、`LDG.E.64`、`LDG.E.128`、`LDG.E.U16`、`STG.E`、`STG.E.64`、`STG.E.128` | LSU → L1 → L2 · 第 3 级 | 第 3 章第 2 节、第 3 章第 3 节 | `*p`、`p[i]`、`reinterpret_cast<uint4*>(p)[i]`（16 B）；位宽直接体现为后缀（`.64 / .128 / .U16`），均带 `desc[URn]` 操作数（通用地址空间窗口见第 59 项）；若 16 B 向量只用其中几个分量，`ptxas` 会拆成标量 `LDG.E` |
| 21 | `ld.global.nc.u32`；`ld.global.nc.v4.f32` | `LDG.E.CONSTANT`、`LDG.E.128.CONSTANT`、`LDG.E.64.CONSTANT` | LSU → L1 只读路径 → L2 · 第 3 级 | 第 8 章第 8 节 | `__ldg(p)`、`const __restrict__ T* p` 或内联 `ld.global.nc`；`.nc` 编译为 `.CONSTANT` 后缀；只用于本 kernel 运行期间没人改写的数据（文档条件是“在 kernel 整个生命周期内只读”；`.nc` 走非一致的只读缓存，有人改写时可能读到旧值。开了 PDL 时，本书把与本 kernel 重叠运行的前序和后继 kernel 也算在内，属推论，见第 9 章第 5 节） |
| 22 | `ld.global.cg.v4.b32`；`st.global.cg.f32` | `LDG.E.STRONG.GPU`、`STG.E.STRONG.GPU` | LSU → L2（绕过 L1）· 第 2 级 | 第 2 章第 6 节 | `__ldcg(p)`、`__stcg(p,v)` 或内联 `ld / st.global.cg`，在 `sm_90a` 反汇编里编译成 `.STRONG.GPU`。注意 PTX 规范里 `.cg` 只是弱缓存提示，轮询同步标志要用 `ld.relaxed.gpu` 或 `ld.acquire.gpu`（见第 2 章第 6 节） |
| 23 | `ld.global.cs.v4.b32` | `LDG.E.EF`、`LDG.E.EF.128`、`LDG.E.EF.64` | LSU → L1 / L2 · 第 3 级 | 第 2 章第 4 节、附录 B 第 1 节 | `__ldcs(p)` 或内联 `ld.global.cs`；PTX 规范定义 `.cs` 在 L1 和 L2 都用 `evict_first`；早期反汇编记录记录了 `ld.global.cs` 编成 `LDG.E.EF` 并带 `desc[URn]` 操作数（原始样本未留存；`.EF` 与 `desc[URn]` 在硬件里怎样分管 L1 与 L2 未公开） |
| 24 | `createpolicy.fractional .L2::evict_first.b64`；`ld.global .L1::evict_first .L2::cache_hint` | `LDG.E.EF`、`LDG.E` | LSU + L2 · 第 2 级 | 第 2 章第 4 节、第 10 章第 2 节 | 内联 PTX；本书样本同时写了 L1 提示与 `createpolicy` 的 L2 留存提示，反汇编出现 `.EF / .EL` 后缀与 `desc[URn]` 操作数（L2 策略推测编码在 `desc[URn]` 里，未查明）；若被保留的数据本来就不会被挤出 L2，加提示不省时间（见第 2 章第 4 节） |
| 25 | `prefetch.global.L2 [a]`；`cp.async.bulk.prefetch.L2.global [a], size`；`prefetch.{param,const}.tensormap [a]` | 本书反汇编未记录（操作码表有 `CCTL`、`UBLKPF`、`UTMACCTL`；仓库笔记把描述符预取写作 `UTMACCTL.PF`，未核实） | L2 预取：LSU → L2（推断）；张量描述符预取：执行单元与目标缓存未公开 · 第 2–3 级 | 第 7 章第 6 节、第 9 章第 4–5 节 | 内联 `prefetch.global.L2`（推断归属 `CCTL`，未核实）；`cp.async.bulk.prefetch.L2` 由单线程预取一段连续字节（推断为 `UBLKPF`，未核实）；`prefetch.{param,const}.tensormap`（`sm_90`）把主机端建好的 128 B 张量描述符提前取入缓存（后继 kernel 可在 PDL 的 `wait` 之前预取静态描述符，见第 9 章第 5 节；执行单元与目标缓存未公开，收益没有测）。若 L2 预取过早被流式数据冲出，反而多读一次 HBM（见第 7 章第 6 节） |
| 26 | `ld.local`；`st.local` | 本书反汇编未记录 | LSU → L1 → L2（位于全局显存）· 第 3 级 | 第 3 章第 1 节、第 3 章第 8 节、第 10 章第 6 节 | 寄存器溢出（`ptxas -v` 报告 `spill`）、动态下标局部数组或未内联函数栈帧；出现局部内存读写说明寄存器读写退化成了显存往返 |
| 27 | `ld.param.*`；`ld.const` | `LDC`、`ULDC` | 常量缓存（每 SMSP 的 `IMC`、每 SM 的 `IDC`）· 第 3 级 | 第 3 章第 5 节、第 4 章第 4 节（图 4-3） | kernel 形参（含 `const __grid_constant__` 张量描述符）或 `__constant__` 只读变量；全卡常量内存共 64 KB，每个 SM 的常量缓存工作集为 8 KB（编程指南未说明该 8 KB 对应 `IMC` 还是 `IDC`）。指令里的立即数常量引用 `c[bank][offset]` 走每 SMSP 的 `IMC`，`LDC` 走 SM 级的 `IDC`（按剖析器手册），`ULDC` 直接读进 warp 共享的统一寄存器 `UR`（见第 7 章第 7 节）；全 warp 读同一地址时可快如读寄存器，读不同地址则按地址数串行化 |
| 28 | `ld.shared.b32`；`ld.shared.v4.b32`；`st.shared::cta.v4.b32` | `LDS`、`LDS.64`、`LDS.128`、`LDS.U8`、`LDS.U16`、`STS`、`STS.64`、`STS.128` | LSU → SMEM · 第 3 级 | 导引三第 3 节、第 3 章第 9 节 | `__shared__` 数组读写；1 对 1 带位宽后缀；同一波次不同通道撞上同一个 4 B bank 时会串行排队（见第 3 章第 9 节） |
| 29 | `cp.async.cg.shared.global [dst],[src],16`；`cp.async.ca.shared.global`；`cp.async.commit_group`；`cp.async.wait_group N` | `LDGSTS.E.BYPASS.128[.ZFILL]`、`LDGSTS.E[.64]`、`LDGDEPBAR`、`DEPBAR.LE` | LSU（L2 直写 SMEM）与记分牌 · 第 3 级 | 第 3 章第 5 节、第 3 章第 7 节、第 6 章第 8 节、第 7 章第 5–6 节 | `__pipeline_memcpy_async` 或内联 `cp.async`；不经私有寄存器直写 SMEM；`.cg`（仅 16 B）编译为绕过 L1 的 `.BYPASS.128`，越界填零时生成 `.ZFILL`。不像 TMA 会自动扣减 `mbarrier` 字节数，`cp.async` 靠 `commit_group`（`LDGDEPBAR`）封组、`wait_group N`（`DEPBAR.LE SB0, N`，早期反汇编记录见 `N = 0..2`，原始样本未留存）等待至多 `N` 组在途，或用 `cp.async.mbarrier.arrive` 挂到 `mbarrier`；代价是每个线程仍要自己算地址、发指令 |
| 30 | `cp.async.bulk.tensor .2d.shared::cluster.global .mbarrier::complete_tx::bytes` | 本书反汇编未记录 | SM 内专用 TMA 单元 · 第 3 级 | 第 3 章第 5 节、第 5 章第 7 节 | 内联 PTX；由 1 个线程发出，占 0 个数据寄存器；代价是主机端要先建描述符、块形状受限，且在 Hopper 上不能按离散行号收集（见第 3 章第 5 节、第 10 章第 10 节） |
| 30a | `tensormap.replace.tile.*`（`sm_90a`）；`tensormap.cp_fenceproxy .global.shared::cta .tensormap::generic.release.gpu`（`sm_90`）；`fence.proxy.tensormap::generic.acquire.gpu [tmap], 128` | 本书反汇编未记录（操作码表有 `UTMACCTL`） | SMEM → 全局内存 → TMA `tensormap` 代理 · 第 3 级 | 第 3 章第 5 节；本书未用（见附录 D 第 4 节） | 设备端修改张量描述符：先在 SMEM 里改字段，用 `cp_fenceproxy` 拷回全局内存并做 release，使用方须在同一 CTA 内执行 128 B 的 acquire 代理栅栏后再发 TMA；本书 kernel 都在主机端建 `const __grid_constant__` 描述符，省去这套栅栏 |
| 30b | `cp.async.bulk{.tensor} .shared::cluster.global .mbarrier::complete_tx::bytes .multicast::cluster [dst], ..., [mbar], ctaMask` | 本书反汇编未记录 | TMA 单元（多播路径未公开）· 第 2–3 级 | 第 5 章第 7 节、第 7 章第 12 节 | 建议配 `sm_90a`；按 16 位 `ctaMask` 把同一块全局数据写进同集群多个目标 CTA 共享内存的同一相对偏移，并各自扣减对应 CTA 的 `mbarrier`（省多少 L2 读取没有测） |
| 31 | `cp.async.bulk.tensor .2d.global.shared::cta .bulk_group`；`cp.async.bulk.commit_group`；`cp.async.bulk.wait_group{.read} N` | `UTMASTG.2D`、`UTMACMDFLUSH`、`DEPBAR.LE`（`.read` 后缀的 SASS 未核实） | TMA 单元 + 线程异步组记分牌 · 第 3 级 | 第 5 章第 8 节（本书 kernel 只用下一项归约写回加 `commit_group / wait_group.read 0`，未发普通 `UTMASTG`；`UTMASTG / UTMACMDFLUSH / DEPBAR.LE` 映射来自早期反汇编记录） | SMEM → 全局显存拷贝不支持 `mbarrier`，只能由发起线程按 `.bulk_group` 等待：普通覆盖写回编为 `UTMASTG`（单切片无累加时无需预先清零输出；写回越界部分可超出上界但不填零，左上角坐标不能为负），`commit_group` 编为独立的 `UTMACMDFLUSH`（手册名“TMA 命令冲刷”），不带 `.read` 的 `wait_group N` 编为 `DEPBAR.LE SB0, N`（`.read` 只等 TMA 读完张量描述符与源端 SMEM 即可复用或退出，SASS 形式未核实）；发起前须执行 `fence.proxy.async.shared::cta` 并完成块内同步 |
| 32 | `cp.reduce.async.bulk .tensor.2d.global.shared::cta .add.bulk_group` | `UTMAREDG.2D.ADD`、`UTMAREDG.3D.ADD` | TMA 单元 + 全局内存原子归约（推测在 L2） · 第 2 级 | 第 5 章第 8 节、第 6 章第 8 节、第 10 章第 8 节 | 内联 PTX；把 SMEM 分块直接发往全局内存做逐元素硬件原子加法（推测在 L2 完成，未查明），无需在 SM 内读回旧值；代价是浮点原子累加顺序不固定（见第 5 章第 8 节） |
| 33 | `cp.async.bulk .shared::cluster.global .mbarrier::complete_tx::bytes` | 本书反汇编未记录 | TMA 单元 · 第 3 级 | 第 3 章第 5 节 | 内联 PTX；免张量描述符的一维连续字节流搬运；要求地址与字节数按 16 B 对齐，搬非连续的多行时每行都要单独发 1 条（见第 3 章第 5 节） |
| 33a | `multimem.ld_reduce{.weak}.global.add{.acc::f32}.v4.bf16x2 d, [mc_a]`；`multimem.st{.weak}.global.v4.f32 [mc_a], b`；`multimem.red` | 本书反汇编未记录 | LSU → NVLink → NVSwitch（NVLink SHARP 网内归约与多播）· 第 2 级（跨卡） | 第 9 章第 9 节 | 内联 PTX（`sm_90+`）；地址必须是虚拟内存管理绑定的对称多播地址（普通 `ld`/`st` 访问行为未定义）：`ld_reduce` 由 NVSwitch 读取全部副本并求和返回，`st` 由 NVSwitch 一次写往全部副本（第 9 章第 9 节：NVSwitch 多播求和与阶段 7 后多播拼接） |

---

## 5. 速查三：屏障、集群共享内存与 Tensor Core

生产者用 TMA 或 `st.async` 搬数据、用 SM 同步单元 `SYNCS` 的 `mbarrier` 通知到达，消费者用 `HGMMA / QGMMA` 在 Tensor Core 上算；`mbarrier`、DSMEM 与 `wgmma` 分别见第 3 章第 7 节、第 7 章第 12 节与第 5 章第 6 节。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 写法与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 34 | `mbarrier.init.shared::cta.b64 [addr], count`；`mbarrier.inval.shared::cta.b64 [addr]` | `SYNCS.EXCH.64`、`SYNCS.CCTL.IV` | SM 同步单元（`SYNCS`）· 第 3 级 | 第 3 章第 7 节 | 内联 PTX；`init` 编译为 `SYNCS.EXCH.64`（写入 64 位屏障字），`inval` 编译为 `SYNCS.CCTL.IV` |
| 35 | `mbarrier.arrive.shared::cta.b64`；`mbarrier.arrive.expect_tx .shared::cta.b64 state,[addr],txcount` | `SYNCS.ARRIVE.TRANS64`、`SYNCS.ARRIVE.TRANS64.A1T0` | `SYNCS` 单元 · 第 3 级 | 第 3 章第 7 节、第 5 章第 7 节 | 内联 PTX；普通报到带 `.A1T0`（报到计数加 1、期望字节 0），登记 TMA 字节数用带寄存器操作数的 `.TRANS64`；若消费者在共享内存读（`LDS`）尚未返回前向 `empty[s]` 报到，会触发读后写竞态（见第 3 章第 7 节） |
| 36 | `mbarrier.try_wait.parity .shared::cta.b64 p,[addr],phase`；`mbarrier.test_wait` | `SYNCS.PHASECHK.TRANS64.TRYWAIT`、`SYNCS.PHASECHK.TRANS64` | `SYNCS` 单元 · 第 3 级 | 第 3 章第 7 节、第 5 章第 7 节 | 内联 PTX；`try_wait` 编译为 `.TRYWAIT`，在硬件里等待直到相位位翻转或超时，未翻转时由 `@!P BRA` 重试 |
| 37a | `fence.proxy.async .shared::cta` | `FENCE.VIEW.ASYNC.S` | LSU / 内存管线 · 第 3 级 | 第 5 章第 8 节、第 7 章第 10 节 | 普通线程写完 SMEM 后，必须执行这道异步代理栅栏，TMA 或 `wgmma` 的异步代理才能看到新数据（代理与跨代理栅栏见第 3 章第 7 节） |
| 37b | `fence.proxy.async .global` | `FENCE.VIEW.ASYNC.G` | LSU / 内存管线 · 第 3 级 | 第 5 章第 8 节、第 8 章第 11 节 | 普通存储写全局内存、随后由 TMA（异步代理）读取或归约时，在本线程内衔接通用代理与异步代理（代理见第 3 章第 7 节）。读侧：放在 `ld.acquire.gpu` 之后、发 TMA 之前；写侧用法见第 8 章第 11 节 |
| 38 | `st.async.shared::cluster .mbarrier::complete_tx::bytes .v4.f32 [ra],{..},[mbar]`；`red.async.relaxed.cluster .shared::cluster .mbarrier::complete_tx::bytes .op.type [ra], b, [mbar]` | 本书反汇编未记录（操作码表为 `STAS`、`REDAS`） | 集群互连 + 远端 `mbarrier` · 第 2 级 | 第 7 章第 12 节、第 9 章第 3 节 | `st.async` 把寄存器数据异步写进同集群 CTA 的 SMEM 并按字节扣减目标 `mbarrier`；`red.async`（本书未用）在同伴 SMEM 上直接做异步归约并扣减字节，但 `.shared::cluster` 形态只支持 `.inc/.dec .u32`、`.min/.max .u32/.s32`、按位 `.and/.or/.xor .b32` 与整数加 `.add .u32/.s32/.u64`（无 `.f32`，按位无 `.b64`），且禁止指向本 CTA 自身——因此第 9 章第 3 节的 FP32 部分和（含写给自己的 1 份，且需固定累加顺序）改用按序号分格加 `st.async` |
| 38a | `mapa.shared::cluster.u32 d, a, cta`；`getctarank.shared::cluster.u32 d, a` | 本书反汇编未记录 | 执行单元未公开（早期审计推测为 ALU 地址运算，未核实）· 第 2–3 级 | 第 7 章第 12 节、第 9 章第 3 节 | `cluster.map_shared_rank` 或内联 PTX；每个 CTA 的 `.shared::cta` 窗口都落在 `.shared::cluster` 窗口内，`mapa` 把本地共享内存变量或 `mbarrier` 地址换成第 `cta` 号同伴 CTA 里的对应集群共享地址（供普通集群共享内存读写或 `st.async` 使用，见第 9 章第 3 节），`getctarank` 从集群共享地址反查目标 CTA 序号 |
| 39 | `barrier.cluster.arrive {.relaxed/.release}.aligned`；`barrier.cluster.wait {.acquire}.aligned` | `MEMBAR.ALL.GPU`、`ERRBAR`、`CGAERRBAR`、`UCGABAR_ARV`、`UCGABAR_WAIT`、`CCTL.IVALL` | 集群屏障单元 · 第 2 级 | 第 9 章第 3 节 | `cooperative_groups::this_cluster().sync()` 或内联 PTX；默认 `cluster.sync()` 编译为 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR + UCGABAR_ARV`（带 release 语义的报到）和 `UCGABAR_WAIT + CCTL.IVALL`（带 acquire 语义的等待，等待前序写被 L2 确认并使本 SM 的 L1 失效）。只有屏障前写的数据在屏障后不再被读，或数据另有完成通知（如 `st.async` 加 `mbarrier`）时，才能用 `.relaxed`；否则屏障不再保证数据的先后 |
| 40 | `mma.sync.aligned.m16n8k16 .row.col.f32.bf16.bf16.f32`（或 `.f16`） | `HMMA.16816.F32.BF16`、`HMMA.16816.F32` | 本 SMSP 的 Tensor Core · 第 5 级 | 第 5 章第 4 节、第 6 章第 8 节、第 7 章第 2 节 | 内联 PTX；1 对 1，操作数 $A$、$B$ 与累加器 $D$ 均在向量寄存器中 |
| 41 | `mma.sync.aligned.m16n8k32 .row.col.f32.e4m3.e4m3.f32` | `F2FP.F16.E4M3.UNPACK_B`、`HMMA.16816.F32` | 管线没有测 + Tensor Core · 第 5 级 | 第 5 章第 4 节、第 7 章第 2 节 | 内联 PTX；`sm_90a` 无单 warp 原生 FP8 矩阵乘指令，1 条 PTX（$k = 32$）被 `ptxas` 拆为 `F2FP` 解包加 2 条 `HMMA.16816.F32`（各算 $k = 16$） |
| 42 | `wgmma.mma_async.sync.aligned .m64n64k16.f32.bf16.bf16` | `HGMMA.64x64x16.F32.BF16` | 全 SM 4 个 Tensor Core · 第 5 级 | 第 5 章第 4 节、第 5 章第 6 节 | 内联 PTX；只在 `sm_90a` 上有（见附录 A 开头）；1 对 1，$m = 64$ 固定，$n$ 取 $8..256$（步长 8），$A$ 与 $B$ 通过统一寄存器描述符 `gdesc[URn]` 从 SMEM 读取；代价是必须由 4 个 warp 一起发射且累加器占向量寄存器（见第 10 章第 10 节）。谓词操作数 `scale-d` 控制是否读旧累加器（0 做 $D = A \cdot B$，见第 7 章第 7 节首块清零用法，首次发射前仍须 `wgmma.fence`；1 做 $D = A \cdot B + D$，见第 5 章第 6 节），浮点形态（16 位、TF32、FP8）还支持 `imm-scale-a / imm-scale-b` $\in \{-1, 1\}$ 对输入逐元素取反。附注：8 位整数 INT8（$k = 32$，累加 `.s32`；`mma.sync` 与 PTX 8.4 起的 `wgmma.mma_async` 均允许 $A$、$B$ 在 `.s8 / .u8` 间混用；操作码表有 `IMMA`、`IGMMA`，`sm_90a` 具体反汇编形态本书反汇编未记录）本书模型未用，见第 5 章第 4 节与附录 D 第 3 节 |
| 43 | `wgmma.mma_async.sync.aligned .m64n32k32.f32.e4m3.e4m3` | `QGMMA.64x32x32.F32.E4M3.E4M3` | 全 SM 4 个 Tensor Core · 第 5 级 | 第 5 章第 4 节、第 7 章第 10 节 | 内联 PTX；只在 `sm_90a` 上有（见附录 A 开头）；FP8 `wgmma` 编译为原生 `QGMMA`（$k = 32$，吞吐见第 5 章第 4 节）；左矩阵 $A$ 从各 warp 的向量寄存器传入（RS 模式，见第 5 章第 4 节） |
| 44 | `wgmma.fence.sync.aligned` | `WARPGROUP.ARRIVE` | 执行单元未公开 · 第 4 级 | 第 5 章第 6 节、第 10 章第 10 节、附录 A 第 2 节 | 内联 PTX；只在 `sm_90a` 上有（见附录 A 开头）；1 对 1，在首次 `wgmma` 前执行，也在普通指令读写累加器寄存器（或 RS 模式下 $A$ 的寄存器分片）之后、下一条访问这些寄存器的 `wgmma` 之前执行，只保证这些寄存器的访问顺序；SMEM 里矩阵的先写后读要另用 `fence.proxy.async`（第 37a 项）。因为带 `.aligned`，warpgroup 的 4 个 warp 都必须执行同一条它；`.sync` 只让同一 warp 的 32 个线程等齐，4 个 warp 之间是否互相等待，PTX 没有写明（见附录 A 第 2 节） |
| 45 | `wgmma.commit_group .sync.aligned` | `HGMMA`、`QGMMA`（末尾带 `gsb0` 标志） | 最后一条 `HGMMA / QGMMA` 上的控制位 · 第 6 级 | 第 5 章第 6 节、第 6 章第 6 节 | 内联 PTX；只在 `sm_90a` 上有（见附录 A 开头）；无独立 SASS 指令，编码为该批次最后一条 `HGMMA / QGMMA` 指令末尾的 `gsb0` 组标志 |
| 46 | `wgmma.wait_group .sync.aligned N` | `WARPGROUP.DEPBAR.LE` | warpgroup 记分牌 · 第 4 级 | 第 5 章第 6 节、第 6 章第 6 节 | 内联 PTX；只在 `sm_90a` 上有（见附录 A 开头）；编译为 `WARPGROUP.DEPBAR.LE gsb0, N`，阻塞直到在途未完成的 `wgmma` 组数不超过 $N$；异步区间里混入改写累加器的普通指令或分支同步不一致时，编译器会在每条 `HGMMA` 后自动插 `WARPGROUP.DEPBAR.LE gsb0, 0`（见第 6 章第 6 节） |
| 47 | `ldmatrix.sync.aligned .m8n8.x4{.trans}.shared.b16` | `LDSM.16.M88.4`、`LDSM.16.M88`、`LDSM.16.M88.2`、`LDSM.16.MT88.4` | LSU → SMEM · 第 3 级 | 第 7 章第 10 节 | 内联 PTX；1 对 1，`.trans` 编译为带转置的 `.MT88`，一个 warp 按 $8 \times 8$ 小块把 SMEM 读进寄存器分片（见第 7 章第 10 节） |
| 48 | `stmatrix.sync.aligned .m8n8.x4{.trans}.shared.b16` | `STSM.16.M88.4`、`STSM.16.MT88.4`、`STSM.16.M88`、`STSM.16.MT88.2` | LSU → SMEM · 第 3 级 | 第 5 章第 8 节 | 内联 PTX；`ldmatrix` 的逆操作，把累加器寄存器分片按交错布局直接写入 SMEM，供随后 TMA 写回或块归约 |
| 48a | `movmatrix.sync.aligned .m8n8.trans.b16 d, a` | 本书反汇编未记录（操作码表为 `MOVM`） | warp 寄存器内矩阵转置 · 第 3–4 级 | 第 7 章第 10 节（对比提及，本书未用） | 内联 PTX（`sm_75+`）；在单个 warp 的寄存器之间把 $8 \times 8$ 的 16 位矩阵转置；第 7 章第 10 节的 $V$ 本来就在 SMEM、转置后仍要写回 SMEM 供 `wgmma` 读取，用 `ldmatrix.trans` 一条指令同时完成读取与 16 位转置即可，无需额外做寄存器内 `movmatrix` |
| 49 | `setmaxnreg.inc.sync.aligned .u32 N`；`setmaxnreg.dec.sync.aligned .u32 N` | `USETMAXREG.TRY_ALLOC.CTAPOOL`（`inc`）、`USETMAXREG.DEALLOC.CTAPOOL`（`dec`） | SM 块内寄存器池分配器 · 第 3 级 | 第 3 章第 8 节、第 7 章第 7 节、第 10 章第 10 节 | 内联 PTX；$N$ 取 $24..256$（8 的倍数），`dec` 把生产者多余寄存器退回本 CTA 池，`inc` 为消费者申领寄存器（池里寄存器不够时阻塞）；要求整个 warpgroup 执行同一条指令（`.sync.aligned`，见附录 A 第 2 节） |

---

## 6. 速查四：warp 操作、内存栅栏、原子操作、网格交接与控制流

warp 内协作 `SHFL`（见第 4 章第 5 节）和 `VOTE`（见第 7 章第 9 节与第 8 章第 6 节）属第 4 级；按剖析器手册，`SHFL` 由 LSU 管线发往本 SM 合一的 L1 数据缓存 / 纹理 / 共享内存单元（记作 `L1TEX`，内部洗牌通路未公开）。全卡内存屏障、L2 原子与释放获取交接属第 2 级，见第 2 章第 6 节。PDL 网格交接与整网格同步属第 1 级，见第 1 章第 4 节、第 7 章第 12 节与第 8 章第 6 节。

| 序号 | PTX | SASS | 管线 · 第几级 | 本书在哪里用到 | 写法与说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 50 | `shfl.sync.idx.b32`；`shfl.sync.bfly.b32`；`shfl.sync.up.b32`；`shfl.sync.down.b32` | `SHFL.IDX`、`SHFL.BFLY`、`SHFL.UP` | LSU → `L1TEX` 单元 · 第 4 级 | 第 4 章第 5 节 | `__shfl_sync(m,v,lane)`、`__shfl_xor_sync`、`__shfl_up_sync`、`__shfl_down_sync`；`__shfl_xor_sync` 编译为 `.BFLY`（蝶形洗牌） |
| 51 | `vote.sync.ballot.b32`；`vote.sync.any.pred`；`vote.sync.all.pred` | `VOTE.ANY` | warp 投票单元 · 第 4 级 | 第 7 章第 9 节、第 8 章第 6 节 | `__ballot_sync(m,p)`（见第 8 章第 6 节）、`__any_sync`（见第 7 章第 9 节）、`__all_sync`；`ballot` 编译为 `VOTE.ANY Rd, PT, Ps`（返回 32 位掩码） |
| 51a | `redux.sync.{add,min,max}.{u32,s32}`；`redux.sync.{and,or,xor}.b32` | 本书反汇编未记录（操作码表为 `REDUX`） | warp 归约至统一寄存器 `UR` · 第 4 级 | 第 4 章第 5 节（对比提及，本书 kernel 未用） | `__reduce_add_sync` 等或内联 PTX（`sm_80+`）；把 warp 内活跃通道的 32 位整数或位掩码归约进统一寄存器 `UR`（延迟没有测）；`sm_90` 上不支持浮点 `redux.sync`（`.f32` 的 `.min/.max` 需 Blackwell 编译目标，且无 `.add.f32`），所以 FP32 求和仍用 5 步 `SHFL.BFLY + FADD` |
| 52 | `bar.warp.sync mask` | `WARPSYNC.ALL`、`WARPSYNC`、`WARPSYNC.COLLECTIVE`、`BSSY`、`BSYNC` | warp 调度器的重汇合单元 · 第 4 级 | 第 4 章第 4 节、第 10 章第 9 节 | `__syncwarp(mask)` 或内联 `bar.warp.sync`；全掩码在需要独立指令时编译为 `WARPSYNC.ALL`（结构化 `if` 后若已由 `BSSY / BSYNC` 汇合，编译器可省掉 `WARPSYNC`）；`BSSY / BSYNC` 是编译器在分化分支前后自动插入的汇合指令对（见第 4 章第 4 节、第 10 章第 9 节） |
| 52a | `elect.sync d\|p, membermask` | 本书反汇编未记录（操作码表为 `ELECT`） | warp 代表线程选举 · 第 4 级 | 第 3 章第 7 节、第 5 章第 8 节 | `cuda::ptx::elect_sync` 或内联 PTX（`sm_90`）；从掩码活跃通道里确定性地选出 1 个代表线程，只把它的谓词 `p` 置真，供单线程发 TMA 或 `mbarrier` 指令；若改写 `if (threadIdx.x == 0)`，编译器无法确认仅单线程执行，可能插入逐通道剥离循环导致串行化（其对 `UR` 或分支栈的具体影响与周期差没有测） |
| 53 | `bar.sync 0`（即 `barrier.sync.aligned 0`） | `BAR.SYNC.DEFER_BLOCKING` | SM 块内屏障单元 · 第 4 级 | 导引三第 3 节、第 4 章第 4 节 | `__syncthreads()`；1 对 1；到达不齐时，等待的时间等于最晚与最早到达之差 |
| 54 | `bar.sync id, n`；`bar.arrive id, n` | `BAR.SYNC.DEFER_BLOCKING`、`BAR.ARV` | SM 块内屏障单元 · 第 4 级 | 第 5 章第 8 节、第 7 章第 7 节 | 内联 `bar.sync id, n`、`bar.arrive id, n`（缺省带 `.aligned`；当只让 CTA 内的一部分 warp 参与时，这种写法跟规范里 `.aligned` 的字面要求如何对应，本书没有查明，见附录 A 第 2 节）；每个 CTA 内的命名屏障号 `id`（`0..15`）与线程数 `n` 编码为立即数（见第 5 章第 8 节、第 7 章第 7 节；整个 SM 的硬件屏障槽还是独立的驻留池上限之一，具体容量未公开），`BAR.ARV` 只报到不等待 |
| 55 | `fence.acq_rel.cta`；`fence.acq_rel.gpu`；`fence.sc.cta`；`fence.sc.gpu` | `MEMBAR.ALL.CTA`、`MEMBAR.ALL.GPU`、`MEMBAR.SC.GPU`、`ERRBAR`、`CGAERRBAR`、`CCTL.IVALL` | LSU / 内存系统确认 · 第 2 级（`.cta` 属第 3 级） | 第 2 章第 6 节、第 3 章第 7 节、第 8 章第 11 节 | `__threadfence_block()`（`fence.sc.cta`）、`__threadfence()`（语义同 `fence.sc.gpu`；本书 `nvcc` 样本里内联 `fence.sc.gpu` 展开为 `MEMBAR.SC.GPU + ERRBAR + CGAERRBAR + CCTL.IVALL` 4 条，另一份 NVRTC［版本未记录］编译的 `__threadfence()` 前面还多 1 条 `MEMBAR.ALL.CTA`，共 5 条，未保留 PTX，多出该条的原因没有查明）；只需要 `acq_rel` 语义时，写内联 `fence.acq_rel.cta`（单条 `MEMBAR.ALL.CTA`）或 `fence.acq_rel.gpu`（`nvcc` 样本展开为 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR + CCTL.IVALL` 4 条；第 8 章第 11 节的 NVRTC［版本未记录］样本前面同样多 1 条 `MEMBAR.ALL.CTA`，共 5 条，多出原因没有查明）。全卡内存屏障等待此前的写入被 L2 确认并使本 SM 的 L1 失效。单向的生产者-消费者交接用 `acq_rel` 就够；`acq_rel` 不禁止本线程的写与之后对另一地址的读交换顺序，双方先写自己的标志、再读对方的标志互等（Dekker 情形）时，需要 `fence.sc` 禁止这一种交换 |
| 56 | `fence.release.gpu` | 本书反汇编未记录 | LSU / 内存系统确认 · 第 2 级 | 第 2 章第 6 节、第 9 章第 5 节 | 内联 PTX；它只规定顺序：本线程之前的读写排在它之后的强写入或 `griddepcontrol.launch_dependents` 之前。强写入指带内存序修饰的写，如 `st.relaxed`；普通 `st` 是弱写入。要让别的线程看见，需要接上两种写法之一：之后的一次强写入（如写标志的 `st.relaxed`，与对方的获取读成对，见第 2 章第 6 节）；或按程序顺序排在它之后的 `griddepcontrol.launch_dependents`（同一内存同步域，即默认设置；见第 9 章第 5 节）。`sm_90` 起支持 |
| 57 | `atom.global.add.u32`；`atom.global.add.f32`；`atom.global.exch`；`atom.global.inc` | `ATOMG.E.ADD.STRONG.GPU`、`ATOMG.E.ADD.S32.STRONG.GPU`、`ATOMG.E.EXCH.STRONG.GPU`、`ATOMG.E.INC.STRONG.GPU` | LSU → L2 原子单元 · 第 2 级 | 第 2 章第 6 节、第 6 章第 8 节 | 使用返回值的 `atomicAdd`、`atomicExch`、`atomicCAS`、`atomicInc`、`fetch_add`；在 L2 执行读改写并要等旧值返回，比只发不等的 `REDG` 多一次 L2 往返；按第 6 章第 8 节那个 kernel 的写法，BF16 标量原子加会被编成比较交换重试循环（把两个值打包的 `.bf16x2` 成对形式见第 5 章第 8 节） |
| 58 | `red.global.add.f32`；`red.global.add.v4.f32`；`red.global.add.s32`；`red.global.min.u64` | `REDG.E.ADD.S32.STRONG.GPU`、`REDG.E.ADD.F32.FTZ.RN.STRONG.GPU`、`REDG.E.ADD.F32x4.FTZ.RN.STRONG.GPU` | LSU → L2 归约单元 · 第 2 级 | 第 2 章第 8 节、第 7 章第 12 节、第 9 章第 3 节 | 忽略返回值的 `atomicAdd(p,v)`、向量 `atomicAdd(float2* / float4*)`；编译器自动转为只发不等的 `REDG`（代价是拿不到旧值） |
| 59 | `ld.acquire.gpu.global.u32 [a]`；`red.release.gpu.global.add.s32 [a],v`；`atom.acq_rel.gpu` | `LDG.E.STRONG.GPU`、`CCTL.IVALL`、`MEMBAR.ALL.GPU`、`ERRBAR`、`CGAERRBAR`、`REDG`、`ATOMG`、`ATOM` | LSU + L2 · 第 2 级 | 第 2 章第 6 节、第 7 章第 12 节、第 8 章第 11 节 | `cuda::atomic_ref<int, thread_scope_device>`（`store / load / fetch_add`）或内联 `ld.acquire.gpu`、`red.release.gpu`；PTX 只保证顺序；L1 失效、等 L2 确认是本 SM 的实现方式（一致性在 L2、L1 不一致见第 2 章第 6 节）：`ld.acquire.gpu` 展开为 `LDG.E.STRONG.GPU + CCTL.IVALL`，`red.release.gpu` 展开为 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR + REDG`；C++ 指针是通用地址：`.shared`、`.local`、`.const` 是通用地址空间里的窗口，`.param` 窗口落在 `.global` 窗口内（`cvta` 做空间转换，如内联 PTX 用的 `cvta.to.shared`，见第 3 章第 5 节；`isspacep` 与 SASS 操作码表里的 `QSPC` 查空间）；编译器能证明状态空间时发专用 `LDS` / `LDG` / `ATOMG`，否则发通用 `LD` / `ST` / `ATOM`（如普通指针上的 `cuda::atomic_ref` 生成 `ATOM.E.ADD.S32.STRONG.GPU`，前后带 `MEMBAR.ALL.GPU + ERRBAR + CGAERRBAR` 与 `CCTL.IVALL`），由硬件在运行时判窗口 |
| 60 | `griddepcontrol.wait`；`griddepcontrol.launch_dependents` | `ACQBULK`、`PREEXIT` | 网格硬件派发器与 SM · 第 1 级 | 第 1 章第 4 节、第 8 章第 8 节、第 9 章第 5 节 | `cudaGridDependencySynchronize()`、`cudaTriggerProgrammaticLaunchCompletion()` 或内联 `griddepcontrol`（见第 8 章第 8 节）。`wait → ACQBULK`：阻塞直到前序网格完成且写入可见。`launch_dependents → PREEXIT`：所有 CTA 发出它或退出后，后继网格可以被调度。按 PTX 规范，若前序线程在 `launch_dependents` 之前先执行 `fence.release.gpu`（两个网格在同一内存同步域，即默认设置），它此前的写入从后继网格启动起即可见；否则只保证在后继执行 `griddepcontrol.wait` 之后可见（见第 9 章第 5 节）。触发过早会让后继占着 SM 空等（见第 1 章第 4 节、第 7 章第 11 节） |
| 61 | 标准库实现（未公开，本书推断：全局原子计数 + 全卡内存屏障 + 轮询 + `bar.sync`） | 本书反汇编未记录 | L2 原子单元 + 各 SM 轮询 · 第 1 级 | 第 2 章第 6 节、第 7 章第 12 节、第 8 章第 6 节 | `cooperative_groups::this_grid().sync()`（配合 `cudaLaunchCooperativeKernel`）；本书推断由标准库组合块内屏障、全卡内存屏障与 L2 计数器轮询实现（轮询用哪种读取未核实），要求全网格所有 CTA 同时驻留（见第 2 章第 6 节、第 7 章第 12 节、第 8 章第 6 节） |
| 62 | `mov.u64 d, %clock64`；`mov.u64 d, %globaltimer` | `CS2R` | 特殊寄存器读取 · 第 4 级 | 第 2 章第 2 节、第 10 章第 5–6 节 | `clock64()`、`clock()` 或内联读取 `%globaltimer`、`%clock64`；本书反汇编里 `clock64()` 编译为 `CS2R R2, SR_CLOCKLO`，读 `%globaltimer` 编译为 `CS2R R4, SR_GLOBALTIMERLO`，各用 1 条指令读出 64 位；`%clock64` 读本 SM 的时钟周期计数器（按 SM 时钟递增），`%globaltimer` 读纳秒级全局计时器（最小步长实测 32 ns，PTX 规范不保证跨 SM 同步，见第 10 章第 5 节）；`clock()` 只读 32 位的 `%clock`，本书反汇编未记录 |
| 63 | `bra`；`bra.uni`；`exit` | `BRA`、`EXIT`、`BSSY`、`BSYNC` | 分支与发射单元 · 第 4 级 | 第 4 章第 4 节、第 10 章第 9 节 | `if / for`、`return`；整个 warp 一致的跳转标 `.U`，分化分支包在 `BSSY ... BSYNC` 内（分支分化代价见第 4 章第 4 节、第 10 章第 9 节） |
| 63a | `nanosleep.u32 t` | 本书反汇编未记录（操作码表为 `NANOSLEEP`） | warp 睡眠让槽 · 第 4 级 | 第 7 章第 12 节、第 8 章第 7 节 | `__nanosleep(t)` 或内联 PTX（`sm_70+`）；让线程挂起约 `t` 纳秒（规范只保证落在 $[0, 2t]$ 内，上限 1 ms），期间剖析器记为 `sleeping` 停顿（被挂起或让出控制权的 warp 均归入此项），把发射槽让给同 SMSP 其他 warp；适合轮询退避（第 7 章第 12 节，收益没有测），不能充当固定延迟计时器（第 8 章第 7 节） |
| 64 | `mov.u32 %tid.x`；`%ctaid.x`；`%ntid.x`；`%nctaid.x`；`%cluster_ctarank`；`%cluster_nctarank` | `S2R`、`S2UR`、`R2UR`；`%ntid / %nctaid` 为 `LDC`、`ULDC`（集群序号寄存器本书反汇编未记录） | 特殊寄存器、统一寄存器与常量区 · 第 3–4 级 | 导引三第 2 节、第 7 章第 7 节、第 9 章第 3 节 | `threadIdx.x`、`blockIdx.x` 保存在每个 SM 的只读特殊寄存器 `SR_TID.X`、`SR_CTAID.X` 里，经 `S2R` 读入每线程向量寄存器 `R`，或经 `S2UR` 直接读进整个 warp 共享的统一寄存器 `UR`（`R2UR` 把 `R` 拷入 `UR`，见第 7 章第 7 节）；`blockDim.x`（`%ntid.x`）与 `gridDim.x`（`%nctaid.x`）在 `sm_90a` 上由启动参数常量区 `c[0x0][0x0 / 0xc]` 经 `LDC` / `ULDC` 读出（常量缓存读取按第 3 级计，见第 27 项；特殊寄存器与统一寄存器按第 4 级计）；`sm_90` 集群内 CTA 序号 `%cluster_ctarank`（`cluster.block_rank()`，`0..%cluster_nctarank-1`，见第 9 章第 3 节）本书反汇编未记录 |

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
- `DEPBAR` → 速查二 第 29 项（`cp.async` 的 `wait_group`）；速查二 第 31 项（TMA 写回的 `wait_group`）；wgmma 的等待是 `WARPGROUP.DEPBAR.LE`，见 `WARPGROUP` → 速查三 第 46 项
- `ELECT` → 速查四 第 52a 项
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
- `IDP / IDP4A` → 速查一 第 12a 项
- `IGMMA / IMMA` → 速查三 第 42 项（附注）
- `IMAD` → 速查一 第 9 项；速查一 第 10 项；速查一 第 12 项；速查一 第 18 项
- `ISETP` → 速查一 第 15 项
- `LD / ST` → 速查四 第 59 项
- `LDC` → 速查二 第 27 项；速查四 第 64 项
- `LDG` → 速查二 第 20 项；速查二 第 21 项；速查二 第 22 项；速查二 第 23 项；速查二 第 24 项；速查四 第 59 项
- `LDGDEPBAR` → 速查二 第 29 项
- `LDGSTS` → 速查二 第 29 项
- `LDS` → 速查二 第 28 项
- `LDSM` → 速查三 第 47 项
- `LOP3` → 速查一 第 11 项
- `MEMBAR` → 速查三 第 39 项；速查四 第 55 项；速查四 第 59 项
- `MOVM` → 速查三 第 48a 项
- `MUFU` → 速查一 第 3 项；速查一 第 4 项；速查一 第 5 项；速查一 第 6 项；速查一 第 7 项
- `NANOSLEEP` → 速查四 第 63a 项
- `POPC` → 速查一 第 14 项
- `PREEXIT` → 速查四 第 60 项
- `PRMT` → 速查一 第 5 项；速查一 第 13 项；速查一 第 18 项
- `QGMMA` → 速查三 第 43 项；速查三 第 45 项
- `QSPC` → 速查四 第 59 项
- `R2UR` → 速查四 第 64 项
- `REDAS / STAS` → 速查三 第 38 项
- `REDG` → 速查四 第 58 项；速查四 第 59 项
- `REDUX` → 速查四 第 51a 项
- `S2R` → 速查四 第 64 项
- `S2UR` → 速查四 第 64 项
- `SHF` → 速查一 第 12 项；速查一 第 18 项
- `SHFL` → 速查四 第 50 项
- `STG` → 速查二 第 20 项；速查二 第 22 项
- `STS` → 速查二 第 28 项
- `STSM` → 速查三 第 48 项
- `SYNCS` → 速查三 第 34 项；速查三 第 35 项；速查三 第 36 项
- `UBLKPF` → 速查二 第 25 项
- `UCGABAR` → 速查三 第 39 项
- `ULDC` → 速查二 第 27 项；速查四 第 64 项
- `USETMAXREG` → 速查三 第 49 项
- `UTMACCTL` → 速查二 第 25 项；速查二 第 30a 项
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
