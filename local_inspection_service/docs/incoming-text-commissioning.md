# 包材文字检验部署与验收门

## 当前引擎

- Python: `paddleocr==3.7.0`, `paddlex[ocr-core]==3.7.1`,
  `paddlepaddle==3.2.2`。
- 模型: `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`。
- 原因: 生产主机已验证并缓存 PaddleOCR/PaddleX 3.7 的 v6 模型；同一
  固定运行时也继续支持既有通用 OCR 使用的 `PP-OCRv6_small`，避免新功能
  上线导致旧文字配件识别回归。
- 坐标: 标签透视校正只在 VantaLine 中执行一次；OCR 的文档方向分类和
  展平关闭，避免 OCR polygon 与规则 ROI 落在不同坐标系。
- 第二路佐证只处理关键字段 ROI，防止整图双跑破坏工位延迟目标。

## 生产依赖

1. 安装系统运行库 `libgomp1`；缺失时 PaddlePaddle 无法导入。
2. 安装并锁定 `requirements.txt` 中的 Python 依赖。
3. 在无外网生产机上线前，离线打包并校验五个模型目录：
   `PP-LCNet_x1_0_textline_ori`、`PP-OCRv6_medium_det/rec`，以及旧路径
   使用的 `PP-OCRv6_small_det/rec`。
4. 对 PostgreSQL 执行
   `storage/migrations/2026_08_06_incoming_text_v1.sql`，验证两个业务表、
   capture 唯一索引和单 active 标准索引。
5. 服务启动后先预热模型，再开放拍照工位。
6. 验收签字前不要设置 `VANTALINE_INCOMING_TEXT_AUTOMATIC_DECISIONS_VERIFIED`；
   此时候选 PASS/FAIL 一律降级为 `REVIEW_REQUIRED`。验收完成后才设为 `true`。

## 真实模型证据

使用下面的独立工具，不允许用 API smoke 中的 OCR test double 代替：

```bash
python3 local_inspection_service/scripts/verify_incoming_text_real_ocr.py \
  correct.jpg wrong-case.jpg missing-model.jpg --warm-runs 2
```

当前客户截图上的初步结果（不是合同验收集）：

- v6 medium 的目标机冷启动和整图耗时以本次生产预热记录为准。
- 一次整图识别加一个关键字段 ROI 佐证约 2.80 秒；多关键字段的端到端
  P95 仍须在客户固定工位测量。
- 带编辑器标尺和批注的大截图约 3.55 秒，不应作为生产相机输入。
- 正确样图可读出 `MODEL:PPLBP-2020`，置信度约 0.986。
- 缺型号样图未读出 MODEL 字段。
- 带红圈和中文批注的小写 `o` 样图不能作为自动 FAIL 的干净证据；必须由
  客户提供未标注原始照片和真实缺陷样品。
- 固定文字字段可显式勾选“忽略空格差异”，用于处理 OCR 分词造成的
  `MODEL: PPLBP-2020` / `MODEL:PPLBP-2020` 差别；大小写和标点仍严格比较。

## 启用门

在锁定客户原始验收集前，功能只能作为付费试点，不得签署“生产自动验收
完成”。必须证明关键缺陷零错误放行、正确样品自动通过率不低于 95%、固定
工位端到端 P95 不超过 3 秒。任一项未满足时保持 `REVIEW_REQUIRED` 或停用。
