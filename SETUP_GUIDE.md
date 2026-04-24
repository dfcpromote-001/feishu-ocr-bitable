# 飞书截图 OCR 入库多维表完整操作说明

本文档说明如何从 GitHub 拉取项目、配置飞书机器人、配置多维表、启动服务，并完成“把截图发给飞书机器人，机器人 OCR 识别后按业务规则写入飞书多维表”的全流程。

## 1. 整体流程

```text
用户发送截图给飞书机器人
  -> 飞书长连接推送图片消息事件
  -> 程序下载消息图片
  -> 调用飞书 OCR；限频时降级到本地 RapidOCR
  -> 按业务规则解析截图内容
  -> 映射成多维表字段值
  -> 按“日期 + 门店”查找已有记录
  -> 已存在则更新，不存在则新增
```

当前仓库已落地的是“营业截图入库”场景，真实写入多维表的字段是 4 个：

```text
日期
门店
营业额科目
日营业额
```

`星期`、`月份`、`月营业额`、`实收系数`、`公司月实收金额` 建议在多维表里做成公式/汇总字段，不由程序写入。

如果后续要处理其他截图或更多字段，可以扩展 `app/services/parser_service.py` 的解析规则、`app/config/store_config.py` 的业务映射，以及 `app/services/bitable_service.py` 的写入字段。

## 2. 从 GitHub 拉取项目

在本地选择一个目录，执行：

```bash
git clone <你的 GitHub 仓库地址>
cd feishu-ocr-bitable-public
```

如果已经拉取过项目，更新代码：

```bash
git pull
```

## 3. 安装 Python 环境

项目支持 Python 3.9 及以上版本，推荐使用 Python 3.12。首次安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

以后每次进入项目后先激活虚拟环境：

```bash
source .venv/bin/activate
```

## 4. 配置环境变量

复制示例配置：

```bash
cp .env.example .env
```

可以手动编辑 `.env`，也可以使用交互式配置向导。

手动编辑 `.env`：

```env
APP_NAME=feishu-screenshot-ingestion
APP_ENV=dev
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000

FEISHU_VERIFICATION_TOKEN=your_feishu_verification_token
FEISHU_APP_ID=your_feishu_app_id
FEISHU_APP_SECRET=your_feishu_app_secret

BITABLE_APP_TOKEN=your_bitable_app_token
BITABLE_TABLE_ID=your_bitable_table_id
REQUEST_TIMEOUT_SECONDS=20

USE_MOCK_OCR=false
USE_MOCK_BITABLE=false

USE_LOCAL_OCR_FALLBACK=true
LOCAL_OCR_PROVIDER=rapidocr
LOCAL_OCR_FALLBACK_ON_ANY_FEISHU_OCR_ERROR=false
```

说明：

```text
FEISHU_APP_ID       飞书开放平台应用的 App ID，通常是 cli_xxx
FEISHU_APP_SECRET   飞书开放平台应用的 App Secret
BITABLE_APP_TOKEN   多维表 app_token
BITABLE_TABLE_ID    具体数据表 table_id，不是视图 id
USE_MOCK_OCR        false 表示真实识别截图
USE_MOCK_BITABLE    false 表示真实写入多维表
```

如果只是本地验证程序逻辑，可以临时设置：

```env
USE_MOCK_OCR=true
USE_MOCK_BITABLE=true
```

看到日志里出现 `[MOCK OCR]` 或 `[MOCK BITABLE]` 时，说明没有走真实飞书接口。

### 4.1 交互式配置向导

首次启动长连接时，如果 `.env` 不存在，或关键配置为空/仍是 `your_xxx` 占位值，程序会在终端提示输入：

```bash
source .venv/bin/activate
python -m app.longconn_runner
```

也可以单独运行配置向导：

```bash
source .venv/bin/activate
python -m app.tools.setup_env
```

配置向导会提示输入：

```text
FEISHU_VERIFICATION_TOKEN
FEISHU_APP_ID
FEISHU_APP_SECRET
BITABLE_APP_TOKEN
BITABLE_TABLE_ID
```

输入完成后会写入本地 `.env`。`.env` 已被 `.gitignore` 忽略，不会提交到 GitHub。

## 5. 配置飞书开放平台应用

### 5.1 创建应用

进入飞书开放平台，创建企业自建应用。记录：

```text
App ID
App Secret
```

把它们填入 `.env` 的：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

### 5.2 启用机器人

在应用能力里启用机器人能力。配置完成后，把机器人添加到用于发送截图的会话或群里。

### 5.3 配置事件订阅

推荐使用“长连接”接收事件，本地不需要公网回调地址。

在事件订阅里添加事件：

```text
im.message.receive_v1
```

这个事件用于接收用户发给机器人的图片消息。

### 5.4 开通应用权限

至少需要以下能力：

```text
接收消息事件
读取/下载消息图片资源
回复消息
OCR 图片识别
多维表记录读取
多维表记录新增
多维表记录更新
```

多维表权限建议直接开通：

```text
bitable:app
```

如果使用细粒度权限，至少需要记录读取、新增、更新相关权限。

权限变更后必须执行：

```text
创建版本 -> 发布版本
```

否则本地程序拿到的 tenant_access_token 仍可能是旧权限。

### 5.5 给多维表添加文档应用权限

开放平台权限只是应用 scope，具体某个多维表还需要授权给应用。

在多维表页面操作：

```text
右上角更多
添加文档应用
搜索应用名称
添加应用
授予可编辑权限
```

不要搜索 `cli_xxx`。通常要搜索应用名称。

如果只开了开放平台权限，但没有给多维表添加文档应用权限，可能出现：

```text
GET records 200 OK
POST records 403 Forbidden
```

## 6. 配置飞书多维表

### 6.1 确认 app_token 和 table_id

`.env` 中需要填写：

```env
BITABLE_APP_TOKEN=多维表 app_token
BITABLE_TABLE_ID=数据表 table_id
```

注意：

```text
table_id 是数据表 id，不是视图 id。
如果 table_id 指到空表或错误表，会出现 FieldNameNotFound。
```

可以用诊断命令查看当前配置指向的真实字段：

```bash
source .venv/bin/activate
python -m app.tools.inspect_bitable_fields
```

输出应该能看到：

```text
日期
门店
营业额科目
日营业额
```

### 6.2 当前营业截图场景的必填字段

在多维表中创建以下字段，字段名必须完全一致：

```text
日期          日期字段
门店          单选字段
营业额科目    单选字段
日营业额      数字字段
```

单选项需要提前创建。例如：

```text
门店：
示例门店C-业务类型
示例门店B-业务类型
示例门店A-业务类型
示例门店D-业务类型
示例门店E-业务类型

营业额科目：
示例科目A
示例科目B
```

### 6.3 公式/汇总字段

以下字段建议由多维表公式或汇总视图生成：

```text
星期
月份
月营业额
实收系数
公司月实收金额
```

程序不会写这些字段。这样可以避免接口写入公式字段失败，也方便后续在多维表里调整财务口径。

### 6.4 分组显示

截图里的分组效果是多维表视图配置，不是程序写入时指定的。

在多维表视图里设置：

```text
分组字段：门店
排序字段：日期，降序
```

程序写入某条记录后，多维表会根据 `门店` 单选字段自动把它放到对应分组下。

## 7. 配置业务映射

程序会优先读取多维表 `门店` 单选字段中的选项，并把 OCR 识别出来的门店名归一化匹配到这些选项。

例如多维表里有：

```text
示例门店A-业务类型
```

OCR 识别到：

```text
示例门店A店
```

程序会去掉 `店`、`-示例业务类型` 等后缀后自动匹配。新增门店时，优先在多维表的 `门店` 单选字段里添加选项。

如果 OCR 名称和多维表选项差异太大，自动匹配失败，再在代码里补充兜底别名。当前营业截图场景的兜底门店映射在：

```text
app/config/store_config.py
```

格式：

```python
"OCR 识别出来的门店名": StoreMeta(
    store_name="多维表门店单选项",
    subject="营业额科目单选项",
    receipt_ratio=0.54,
),
```

当前已配置的真实门店包括：

```text
示例门店C店 -> 示例门店C-业务类型
示例门店B店 -> 示例门店B-业务类型
示例门店A店 -> 示例门店A-业务类型
示例门店D店 -> 示例门店D-业务类型
示例门店E店 -> 示例门店E-业务类型
```

如果日志出现：

```text
STORE_MAPPING_FAILED: 未找到门店映射: xxx
```

先确认多维表 `门店` 单选项是否存在；如果存在但仍无法自动匹配，再在 `STORE_CONFIG` 中补充该 OCR 门店名到多维表单选项的映射。

## 8. 启动服务

推荐使用长连接启动：

```bash
source .venv/bin/activate
python -m app.longconn_runner
```

启动时关注日志：

```text
use_mock_ocr=False use_mock_bitable=False
```

如果看到 `true`，说明 `.env` 还在 mock 模式。

## 9. 发送截图测试

1. 确认机器人已加入会话。
2. 给机器人发送截图。
3. 查看本地终端日志。

成功时会看到类似：

```text
receive image message
download message image done
[LOCAL OCR] rapidocr done, lines=45
start parse OCR text
upsert start: date=2026-04-18 store=示例门店A-业务类型 daily_total=2928.2
[FEISHU BITABLE] created record_id=...
revenue import summary: success=2 failed=0 upserted=2
```

同一张图重复发送时，程序会按“日期 + 门店”查找已有记录：

```text
无记录 -> 新增
已有记录且日营业额相同 -> 跳过，不重复登记
已有记录且日营业额不同 -> 保留较高的日营业额
```

## 10. 常用诊断命令

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

启动 mock 模式联调：

```env
USE_MOCK_OCR=true
USE_MOCK_BITABLE=true
```

启动真实模式：

```env
USE_MOCK_OCR=false
USE_MOCK_BITABLE=false
```

修改 `.env` 后需要重启 `python -m app.longconn_runner`。

## 11. 常见问题

### 11.1 飞书 OCR 报 99991400

日志：

```text
OCR rate limited
use local OCR fallback provider=rapidocr code=99991400
```

这是飞书 OCR 限频或额度相关问题。当前项目会自动降级到本地 RapidOCR：

```env
USE_LOCAL_OCR_FALLBACK=true
LOCAL_OCR_PROVIDER=rapidocr
```

只要后续出现：

```text
[LOCAL OCR] rapidocr done
```

说明本地 OCR 已继续处理。

### 11.2 parser returned empty records

说明 OCR 有文本，但解析器没有从当前截图格式中识别出可入库的业务记录。

排查：

```text
1. 查看日志中的 ocr_text
2. 确认截图里是否有日期
3. 确认金额标签是否是解析器支持的格式
4. 必要时修改 app/services/parser_service.py
```

当前已支持：

```text
营业金额(元)
营收金额（元）
```

### 11.3 STORE_MAPPING_FAILED

日志：

```text
STORE_MAPPING_FAILED: 未找到门店映射: xxx
```

处理：

```text
1. 确认多维表“门店”单选字段中是否已有对应门店选项
2. 如果没有，先在多维表中新增该单选项
3. 如果已有选项但名称差异太大，再在 app/config/store_config.py 中添加兜底映射
4. 重启服务
```

### 11.4 99991672 Access denied

说明应用缺少开放平台权限。

处理：

```text
1. 开通 bitable:app 或对应记录读写权限
2. 创建版本并发布
3. 重启服务
```

### 11.5 91403 Forbidden

如果 `GET records` 成功但 `POST records` 返回 403，通常是具体多维表没有给应用可编辑权限。

处理：

```text
1. 打开多维表
2. 添加文档应用
3. 搜索应用名称
4. 授予可编辑权限
```

### 11.6 FieldNameNotFound

日志：

```text
Feishu API error: code=1254045 msg=FieldNameNotFound
```

说明 `.env` 的 `BITABLE_TABLE_ID` 指向的数据表里没有程序提交的字段。

执行：

```bash
python -m app.tools.inspect_bitable_fields
```

确认真实字段是否包含：

```text
日期
门店
营业额科目
日营业额
```

如果输出只有：

```text
文本
```

说明当前 table_id 指向的是空表或还没有建字段。

## 12. 代码结构

```text
app/longconn_runner.py
  飞书长连接入口，监听图片消息

app/clients/feishu_client.py
  飞书 tenant token、图片下载、OCR、多维表 API

app/services/ocr_service.py
  OCR 识别；飞书 OCR 失败时可降级 RapidOCR

app/services/parser_service.py
  从 OCR 文本解析业务记录；当前示例为日期、门店、日营业额

app/config/store_config.py
  OCR 门店名到多维表门店单选项的兜底映射

app/services/bitable_service.py
  按日期+门店 upsert 多维表记录

app/tools/inspect_bitable_fields.py
  诊断当前 table_id 的真实字段列表

app/tools/setup_env.py
  交互式生成或更新本地 .env 配置
```

## 13. 上线前检查清单

```text
[ ] .env 中 USE_MOCK_OCR=false
[ ] .env 中 USE_MOCK_BITABLE=false
[ ] FEISHU_APP_ID / FEISHU_APP_SECRET 正确
[ ] BITABLE_APP_TOKEN / BITABLE_TABLE_ID 正确
[ ] 飞书应用已发布最新版本
[ ] 飞书应用已开机器人和消息事件
[ ] 飞书应用已开 OCR 和多维表读写权限
[ ] 多维表已添加文档应用并授予可编辑权限
[ ] 多维表已创建 日期/门店/营业额科目/日营业额 字段
[ ] 多维表单选项已创建
[ ] 多维表门店单选项可覆盖常见 OCR 门店名；必要时 store_config.py 已补充兜底映射
[ ] python -m app.tools.inspect_bitable_fields 能看到目标字段
[ ] pytest 通过
```
