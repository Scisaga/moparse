# 实际Markdown修改证据

本页对照本次修改开始时保存的05正文与本次CPU回放06正文；两者都不是expected。逐项评分来自共同程序，实际值的字符改善不重复计算为业务正确项。下面的差异来自候选自己的final.md，不读取expected、IR或原PDF。

## P07

173个quality800样本中，0个样本的实际Markdown发生变化。

## P08

173个quality800样本中，1个样本的实际Markdown发生变化。

样本：`hkex-key-tables-p011`。修改前：`benchmark/reports/20261101-business-coverage-05/p08/candidate/artifacts/quality800-r1-hkex-key-tables-p011/final.md`；修改后：`benchmark/reports/20261101-expected-only-06/p08/candidate/artifacts/quality800-r1-hkex-key-tables-p011/final.md`。

```diff
--- 05/final.md
+++ 06/final.md
@@ -80 +80 @@
-- 范围：Key Market Statistics；ADT of Northbound Trading of Stock Connect1 (RMBbn)；2024：\\( 150.1^4 \\)（附注：4 New record high in 2024）；2023：108.3；Change：39%。
+- 范围：Key Market Statistics；ADT of Northbound Trading of Stock Connect1 (RMBbn)；2024：150.1（附注：4 New record high in 2024）；2023：108.3；Change：39%。
@@ -84 +84 @@
-- 范围：Key Market Statistics；ADT of Southbound Trading of Stock Connect1 ($bn)；2024：\\( 48.2^4 \\)（附注：4 New record high in 2024）；2023：31.1；Change：55%。
+- 范围：Key Market Statistics；ADT of Southbound Trading of Stock Connect1 ($bn)；2024：48.2（附注：4 New record high in 2024）；2023：31.1；Change：55%。
@@ -88 +88 @@
-- 范围：Key Market Statistics；ADV of derivatives contracts traded on the Futures Exchange ('000 contracts)；2024：\\( 830^4 \\)（附注：4 New record high in 2024）；2023：742；Change：12%。
+- 范围：Key Market Statistics；ADV of derivatives contracts traded on the Futures Exchange ('000 contracts)；2024：830（附注：4 New record high in 2024）；2023：742；Change：12%。
@@ -92 +92 @@
-- 范围：Key Market Statistics；ADV of stock options contracts traded on the Stock Exchange ('000 contracts)；2024：\\( 720^4 \\)（附注：4 New record high in 2024）；2023：612；Change：18%。
+- 范围：Key Market Statistics；ADV of stock options contracts traded on the Stock Exchange ('000 contracts)；2024：720（附注：4 New record high in 2024）；2023：612；Change：18%。
@@ -100 +100 @@
-- 范围：Key Market Statistics；ADT of Northbound Bond Connect (RMBbn)；2024：\\( 41.6^4 \\)（附注：4 New record high in 2024）；2023：40.0；Change：4%。
+- 范围：Key Market Statistics；ADT of Northbound Bond Connect (RMBbn)；2024：41.6（附注：4 New record high in 2024）；2023：40.0；Change：4%。
```

本次变化只移除已有明确关联附注支持的标量数学包装，附注内容和归属继续打印。裸指数、无关联附注、变量和复合公式不适用；合成反例验证这些情况保留原字面。P07没有此类正文变化，不将评分读取修复报成P07新增正文收益。
