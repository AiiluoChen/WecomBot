# WeCom Robot - 旅拍客服自动化机器人

基于**纯原生极简 Agent 循环（Native Minimal Agent Loop）**构建的企业微信旅拍修图中心客服机器人。

## 🌟 核心特性

- **1:1 还原真实业务场景**：新客进线自动迎宾、三要素提取（时间-门店/尾号-姓名）查片并下发百度网盘分享文案、亲切人设闲聊、疑难/客诉一键转人工。
- **纯原生极简 Agent 循环**：无 LangChain 等庞大重型黑盒，仅依靠 OpenAI 标准客户端的 Tool-Calling 循环（核心引擎仅 60 行代码），透明、易读、可控。
- **开箱即用与跨机迁移**：
  - 数据存储（CSV）采用抽象基类设计，后续可无缝替换为 MySQL 或企业微信智能表格。
  - 附带本地交互模拟器（Mock CLI），免配置网络环境秒测全流程。
  - 附带 Dockerfile 和 docker-compose.yml，一键打包推送到任何云服务器。

---

## 🚀 快速开始

### 1. 企微真机实时联调（🔥 最推荐：零配置直连你的企业微信）

利用刚才已经扫码授权的 `wecom-cli` 凭证，**无需配置域名、无需内网穿透**，直接在手机企微里和机器人对话：

```bash
cd /Users/aiiluo/Documents/Code/WocomRobot
python3 channels/wecom_polling.py
```
- 启动后，你的手机企业微信会立即收到机器人发送的欢迎语与须知。
- 你在手机企微里直接回复：`11月2日 北京门店 陈麻子`、`你们拍照好看吗` 或 `转人工`。
- 机器人会在手机里实时回复你百度网盘链接或闲聊！

---

### 2. 本地控制台模拟器测试（无需手机）

直接在终端内扮演客户进行端到端对话测试：

```bash
cd /Users/aiiluo/Documents/Code/WocomRobot
python3 channels/mock_cli.py
```

---

### 3. 生产环境 Webhook 接入（微信客服 / 自建应用）

```bash
python main.py
```
服务将在 `http://0.0.0.0:8000` 启动：
- 健康检查：`GET /health`
- HTTP 聊天接口：`POST /chat` （入参 `{"message": "11月2日 北京门店 陈麻子"}`）
- 企微 Webhook 回调：`GET/POST /wecom/callback`

---

### 3. 一键 Docker 部署与迁移

在任何目标 Linux 服务器上：
```bash
# 1. 复制工程目录
scp -r WocomRobot user@your-server-ip:/opt/

# 2. 检查 .env 中的 API_KEY 配置
cd /opt/WocomRobot

# 3. 一键容器化运行
docker compose up -d --build
```

---

## 📊 本地测试数据集 (CSV)

交付测试数据维护在 `data/photo_delivery.csv`：

| customer_name | shoot_date | store_name | phone_tail | pan_url | pan_pwd | status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **陈麻子** | 2026-11-02 | 北京门店 | 6224 | https://pan.baidu.com/s/1PZO09k8_lXMCtSpUDIAATw | 19qz | ready |
| **李小萌** | 2026-11-05 | 大理双廊店 | 8819 | https://pan.baidu.com/s/1AAbcde9_sampleUrlDemo | 8a2b | ready |
| **张晓华** | 2026-11-13 | 三亚海棠湾店 | 1234 | - | - | retouching |

> 日期支持自然语言模糊匹配，例如 `11月2日`、`11-02`、`2026-11-02` 均能正确匹配对应记录。

---

## ⚙️ 企业微信官方配置项说明 (.env)

当准备将机器人接入企业微信微信客服或自建应用时，在 [.env](file:///Users/aiiluo/Documents/Code/WocomRobot/.env) 中补齐以下参数：

```ini
# 1. 企业ID (企微管理后台【我的企业】底部查看)
WECOM_CORP_ID=wwxxxxxxxxxxxxxxxx

# 2. 微信客服 Secret (企微管理后台【应用管理】->【微信客服】进入查看)
WECOM_KF_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 3. 回调验证 Token (在微信客服/自建应用【API接收消息】中生成)
WECOM_TOKEN=xxxxxxxxxxxx

# 4. 消息加解密密钥 (在【API接收消息】中生成，43位字符)
WECOM_ENCODING_AES_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 5. 转人工默认接待客服的 UserID (触发转人工时派单给该员工)
WECOM_DEFAULT_SERVICER=woGoxID...
```

### 🔒 人工接管静默与释放机制
- 当客户触发转人工后，系统自动将该客户标记为 `HUMAN_TAKEOVER`，**机器人立即进入静默模式**，不再自动插话。
- 真人客服沟通完毕后，可调用释放接口恢复机器人托管：
  ```bash
  curl -X POST "http://localhost:8000/wecom/session/release?customer_id=客户ID"
  ```

---

## 📂 项目结构规划

```
WocomRobot/
├── .env                      # 本地环境变量 (已配置 DeepSeek API)
├── .env.example              # 环境变量模板
├── Dockerfile                # 标准容器化镜像配置
├── docker-compose.yml        # 容器编排
├── requirements.txt          # Python 依赖清单
├── README.md                 # 项目详细说明文档
├── docs/
│   └── index.html            # 方案设计与交互示意 HTML
├── data/
│   └── photo_delivery.csv    # 本地网盘提取测试表
├── agent/
│   ├── engine.py             # 纯原生 Native Agent Loop 核心引擎 (约 60 行)
│   ├── prompts.py            # 客服人设 System Prompt 与欢迎语/交付模版
│   └── tools.py              # query_photo_pan 与 escalate_to_human 工具注册
├── storage/
│   ├── base.py               # 存储抽象基类 (便于未来无缝迁移到数据库/智能表格)
│   └── csv_storage.py        # CSV 数据存储与智能日期归一化实现
├── channels/
│   ├── mock_cli.py           # 本地终端交互式测试器 (无需外部网络)
│   └── wecom_webhook.py      # 企业微信官方回调路由处理
└── main.py                   # FastAPI 服务启动总入口
```
