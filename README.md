# GPU 是怎么工作的，以及怎么优化 GPU 性能

在线阅读（合并版，图嵌在正文里）：https://yfei1.github.io/gpu-book-zh/

一本中文 GPU 教程（草稿，正在逐轮审读）。全书以 H200 为例，一章往里放大一级硬件；一个 gemv kernel 从最朴素的写法一步步演化到排行榜提交版。

## 章节

- [前言](book/preface.md)
- [第 0 章：单层模型算什么，最快能跑多快？](book/ch00.md)
- [第 0.5 章：一段最小的 CUDA 程序](book/ch00_5.md)
- [第 1 章 [第 0 级]：一层模型在时间线上怎么排 kernel？](book/ch01.md)
- [第 2 章 [第 1 级]：点开一个 kernel，整张 H200 芯片怎么接住它？](book/ch02.md)
- [第 3 章 [第 2 级]：点开 1 个 SM：哪一项资源先用完，数据怎样搬进 SMEM？](book/ch03.md)
- [第 4 章 [第 3 级]：点开 1 个 SMSP，调度器每个周期怎么选 warp 并发射指令？](book/ch04.md)
- [第 5 章 [第 4 级]：指令发出去后，在哪个物理管线里算？](book/ch05.md)
- [第 6 章 [第 5 级]：一行代码如何变成机器指令与寄存器里的比特？](book/ch06.md)

## 交互图

下载后用浏览器直接打开（单文件 HTML，无外部依赖）。

- [图 0-1 一层模型的一步：数据怎么流过七个阶段](figs/ch00-a.html)
- [图 2-1 132 个 SM 怎样做完 2304 个 CTA（每个 SM 一次只做 1 个）](figs/ch02-a.html)
- [图 2-2 每个 SM 要同时读几行 W，HBM 才跑得满](figs/ch02-b.html)
- [图 3-1 一个 SM 能同时放下几个 CTA](figs/ch03-a.html)
- [图 3-2 一条 warp 读指令取回几个扇区](figs/ch03-coal.html)
- [图 3-3 把 16 KiB 搬进 SMEM 的四种方式](figs/ch03-b.html)
- [图 3-4 环形缓冲：几个槽才能一边搬一边算](figs/ch03-c.html)
- [图 4-1 调度器每个周期选哪个 warp](figs/ch04-a.html)
