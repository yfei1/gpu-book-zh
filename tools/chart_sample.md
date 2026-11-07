# 图表块样例

下面是三种图表块的写法，数据都是真的。

gemv 演化链（evolution/GEMV_NUMBERS.md，H200，清缓存，中位数）：

```chart
type: steps
title: gemv 十个版本的耗时（qkv_gate，T = 1）
unit: µs
baseline: {label: cuBLAS torch.mv, value: 19.2}
floor: {label: 读 W 的下界, value: 7.9}
note: v0 太慢，柱子被截断；v2 是 CUDA graph，kernel 与 v1 相同。每个数含 4.6 µs 空 kernel 开销。
data:
  - {label: v0, value: 674.58, note: 每行 1 个线程}
  - {label: v1, value: 54.08, note: 每行 1 个 CTA}
  - {label: v2, value: 54.19, noise: true, note: CUDA graph，kernel 不变}
  - {label: v3, value: 43.34, note: K 切两半，每行 2 个 CTA（尾波）}
  - {label: v4, value: 44.29, noise: true, note: L2 提示，不算一步}
  - {label: v5, value: 17.49, note: 16 B 向量化读取，合并访问}
  - {label: v6, value: 21.63, note: 每 CTA 1 个 warp，在途字节少，变慢}
  - {label: v7, value: 15.15, note: 每线程 8 条 16 B 读取在途}
  - {label: v8, value: 14.74, note: warp shuffle 归约}
  - {label: v9, value: 14.83, low: 14.5, high: 15.26, noise: true, note: 移位解包，字节没变}
  - {label: v10, value: 13.92, note: 12 位权重}
```

qkv_gate 的 g0 与 g5（research/gemm_evolution.md，图重放时间）：

```chart
type: grouped
title: qkv_gate 从 cuBLAS（g0）到最终版（g5）
unit: µs
note: 每个数含约 4.96 µs 空图重放开销；T = 8 和 32 的 g5 读 12 位权重。
data:
  groups: [T = 8, T = 32, T = 128, T = 256]
  series:
    - {name: g0 cuBLAS, values: [18.20, 18.60, 21.32, 22.90]}
    - {name: g5 最终版, values: [12.89, 14.30, 17.35, 21.36]}
```

一层 decode 的读取时间下界（各阶段读的字节 ÷ 4.8 TB/s，数来自图 0-1）：

```chart
type: stacked
title: 一层 decode 的 HBM 读取时间下界
unit: µs
note: 各段 = 该阶段读的字节 ÷ 4.8 TB/s；合计即整层下界，约 40 µs。
data:
  - {label: qkv_gate, value: 7.86}
  - {label: attention, value: 0.10}
  - {label: o, value: 3.50}
  - {label: router, value: 1.75}
  - {label: pooler, value: 13.98}
  - {label: experts, value: 11.04}
  - {label: unpooler, value: 1.75}
```

只有一个 series 的 grouped 就是普通柱状图（蓝色，没有变化行）：

```chart
type: grouped
title: qkv_gate 最终版（g5）在不同 T 下的耗时
unit: µs
data:
  groups: [T = 8, T = 32, T = 128, T = 256]
  series:
    - {name: g5 最终版, values: [12.89, 14.30, 17.35, 21.36]}
```
