# 文档识别与结构化 · doc-ocr-extract

审小牛 AuditOx 基础技能。把合同、发票、票据、对账单的原始文件转成可复用的结构化文档，供其他审计技能消费。

**全程本地运行，客户资料不出本机。**

## 30 秒上手

```bash
# 1. 环境自检（首次必跑）
python scripts/env_check.py

# 2. 识别一个文件
python scripts/run_ocr.py "D:/项目/发票扫描件.pdf"

# 3. 识别一整个目录
python scripts/run_ocr.py "D:/项目/原始凭证" -o "D:/项目/02_工作底稿/识别结果"
```

输出默认落在输入同级目录的 `ocr-output/`。

## 产出什么

| 文件 | 内容 | 谁用 |
|---|---|---|
| `<名>.md` | 版面还原的 Markdown 全文，多页带页码标记，低置信度行前缀 `[?]` | 人工阅读、LLM 精读 |
| `<名>.json` | 结构化字段，每个字段带页码、坐标、原文、来源方式 | 下游审计技能、程序处理 |
| `<名>.lines.json` | 原始 OCR 文本行（含坐标与置信度） | 调试、二次抽取 |
| `_index.json` | 批次索引 + 跨文档异常 | 批量检索、汇总 |
| `_review.md` | 人工复核清单（P0/P1/P2 分级） | **每次必看** |

## 支持什么

| 类型 | 抽取内容 |
|---|---|
| 增值税发票 | 发票代码/号码、开票日期、购销方名称与税号、不含税金额、税额、价税合计（大小写）、税率、货物明细、备注、收款人/复核人/开票人 |
| 合同 | 标题、编号、签订日期地点、甲乙方（名称/住所/法定代表人）、条款树（条号+标题+正文+页码）、合同金额、履行期限、付款条件、违约条款、质保期、签署信息 |
| 票据/回单 | 全文 + 关键字段（识别能力弱于发票，建议配合人工） |
| 通用文档 | 全文 Markdown |

输入格式：PDF（电子/扫描）、JPG、JPEG、PNG、BMP、TIFF、WEBP。

## 性能

| 输入类型 | 耗时 |
|---|---|
| 电子 PDF（有文本层） | **<0.5 秒/份**（直读文本层，不跑 OCR） |
| 扫描件 / 照片（GPU） | 1–2 秒/页 |
| 扫描件 / 照片（CPU） | 4–8 秒/页 |

同一文件二次运行走缓存，耗时趋近 0。加 `--no-cache` 可强制重跑。

## 准确性怎么保证

四层校验，逐层拦错：

1. **字符级** —— OCR 置信度门控，关键字段低于 0.90 就标 `low_confidence`
2. **格式级** —— 统一社会信用代码 GB32100 校验位、发票号位数、日期合法性
3. **逻辑级** —— 金额勾稽（不含税+税额=价税合计）、大小写一致、明细合计一致
4. **跨文档级** —— 同批次发票号重复、同一税号对应多个名称

三条铁律：

- **只标记，不修正** —— 勾稽失败时绝不调金额凑平，只报差额
- **无溯源即不可信** —— 每个字段都能定位到原页坐标
- **抽不到就留空** —— 绝不用"常见值"填充

### 质量分级

| 等级 | 含义 | 怎么用 |
|---|---|---|
| A | 齐全、勾稽通过、置信度达标 | 直接用 |
| B | 齐全但有提示项 | 抽查后使用 |
| C | 勾稽失败 / 必填缺失 / 校验位不通过 | **必须人工核对** |
| D | 号码与日期都没抽到 | 只当全文用 |

## 参数

```
python scripts/run_ocr.py <输入> [-o 输出目录] [--type 类型] [--device auto|gpu|cpu]
                       [--dpi 200] [--no-cache] [--quiet]
```

| 参数 | 说明 |
|---|---|
| `-o, --out` | 输出目录，默认 `<输入>/ocr-output` |
| `--type` | 强制类型：`invoice` / `contract` / `receipt` / `generic`，默认 `auto` 自动判别 |
| `--device` | `auto`（默认，有 GPU 用 GPU）/ `gpu` / `cpu` |
| `--dpi` | PDF 渲染精度，默认 200；老旧扫描件可设 300 提高识别率（更慢） |
| `--no-cache` | 禁用结果缓存 |
| `--quiet` | 精简输出 |

## 安装

```bash
# Python 3.10–3.12
python -m venv ocr-venv
ocr-venv\Scripts\activate          # Windows
# source ocr-venv/bin/activate     # Linux/macOS

# PaddlePaddle GPU（按你的 CUDA 版本换源：cu126 / cu129）
pip install paddlepaddle-gpu==3.4.0 \
  --index-url https://www.paddlepaddle.org.cn/packages/stable/cu129/

# 无 GPU 时改装 CPU 版
# pip install paddlepaddle==3.4.0

pip install paddleocr==3.7.0 pymupdf
python scripts/env_check.py
```

首次识别自动下载 PP-OCRv6 模型（约 140MB）到 `~/.paddlex/official_models/`，之后完全离线。

## 已知局限

| 局限 | 应对 |
|---|---|
| `‰` 常被 OCR 识成 `%`（违约金日万分之几 → 百分之几，差 10 倍） | 输出 `daily_rate_note` 提示核对原件 |
| 手写体识别率低 | 手写内容需人工录入 |
| 印章只判有无，不认印章文字 | 印章真伪另行核验 |
| 复杂合并单元格表格可能列错位 | 检查 `items` 后人工修正 |
| 合同只切结构，不做语义判断 | 语义判断交给下游技能或人工 |

## 目录结构

```
doc-ocr-extract/
├── SKILL.md                     技能说明
├── README.md                    本文件
├── CHANGELOG.md                 更新记录
├── rules/                       抽取与校验规则（可审计、可修改）
│   ├── 01-文档分类与版式判别.md
│   ├── 02-发票字段抽取规则.md
│   ├── 03-合同要素抽取规则.md
│   └── 04-准确性校验与人工复核.md
├── scripts/
│   ├── run_ocr.py               主入口
│   ├── env_check.py             环境自检
│   ├── make_sample.py           生成测试样本（发票+合同图）
│   ├── make_sample_pdf.py       生成测试样本（多页 PDF）
│   └── ocr_core/
│       ├── loader.py            文件归一化（PDF 文本层优先）
│       ├── engine.py            PaddleOCR 封装
│       ├── classify.py          文档类型判别
│       ├── extract_invoice.py   发票字段抽取
│       ├── extract_contract.py  合同结构抽取
│       ├── validate.py          确定性校验（校验位/勾稽/大写金额）
│       └── writer.py            输出层
├── samples/                     脱敏测试样本
├── tests/                       回归测试
└── output/                      示例运行结果
```

## 为什么不用 Unlimited-OCR

`baidu/Unlimited-OCR-2` 权重 6.69GB，本机 RTX 4060 Laptop 8GB 显存加载后仅剩约 1GB 给激活，会频繁 OOM 或回退 CPU 推理，速度与稳定性都不可控。且其输出为无坐标的 Markdown，无法满足审计"每个数字回原页核对"的溯源要求。

本技能改用 PaddleOCR（模型 140MB，显存占用 <2GB）+ 确定性规则抽取，在 8GB 卡上稳定运行，并天然满足溯源要求。
