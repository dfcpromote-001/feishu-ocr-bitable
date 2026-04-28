# 飞书截图 OCR 入库多维表

这个项目用于接收飞书机器人图片消息，将截图 OCR 识别后，按业务规则解析并写入飞书多维表。

当前推荐使用飞书长连接模式：

```text
发送截图给机器人
  -> 接收图片消息
  -> 下载图片
  -> OCR 识别
  -> 按业务规则解析截图内容
  -> 写入飞书多维表
```

完整部署和配置说明见：

```text
docs/SETUP_GUIDE.md
```

## 快速开始

```bash
git clone <你的 GitHub 仓库地址>
cd feishu-ocr-bitable

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
```

可以直接启动长连接；如果 `.env` 缺少必要配置，程序会在终端提示输入并写入本地 `.env`：

```bash
source .venv/bin/activate
python -m app.longconn_runner
```

也可以先手动运行配置向导：

```bash
source .venv/bin/activate
python -m app.tools.setup_env
```

确认真实模式：

```env
USE_MOCK_OCR=false
USE_MOCK_BITABLE=false
```

启动长连接：

```bash
source .venv/bin/activate
python -m app.longconn_runner
```

## 多维表写入字段

当前营业截图场景下，程序只写入 4 个字段：

```text
日期
门店
营业额科目
日营业额
```

`星期`、`月份`、`月营业额`、`实收系数`、`公司月实收金额` 建议在多维表中用公式或汇总字段维护。

## 常用命令

运行测试：

```bash
source .venv/bin/activate
pytest
```

查看当前 `.env` 指向的多维表字段：

```bash
source .venv/bin/activate
python -m app.tools.inspect_bitable_fields
```

重新输入飞书和多维表配置：

```bash
source .venv/bin/activate
python -m app.tools.setup_env
```

## 主要文件

```text
app/longconn_runner.py              飞书长连接入口
app/services/ocr_service.py         OCR 识别和本地降级
app/services/parser_service.py      OCR 文本解析，可按截图格式扩展规则
app/config/store_config.py          门店兜底映射
app/services/bitable_service.py     多维表 upsert
app/tools/inspect_bitable_fields.py 多维表字段诊断
docs/SETUP_GUIDE.md                 完整操作说明
```
