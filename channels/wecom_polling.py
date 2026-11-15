"""
企微免穿透实时联调监听器 (WeCom Polling Runner)
基于已绑定的 wecom-cli 凭证，直接与你的企业微信单聊打通！
无需公网域名、无需内网穿透、无需企微管理员后台配置，手机发消息即可实时自动回复。
"""
import subprocess
import json
import time
import os
import sys
import re
import glob
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 1. 自动注入 nvm 中的 node/wecom-cli 路径至环境变量，避免子进程找不到命令
nvm_bins = glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin"))
for b in nvm_bins:
    if b not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{b}:{os.environ.get('PATH', '')}"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

load_dotenv()

from storage.csv_storage import CsvStorage
from agent.tools import ToolExecutor
from agent.engine import NativeAgent
from agent.prompts import WELCOME_MESSAGE


def get_cli_bin() -> str:
    """动态获取 wecom-cli 可执行文件绝对路径"""
    import shutil
    found = shutil.which("wecom-cli")
    if found:
        return found
    candidates = glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/wecom-cli"))
    if candidates:
        return candidates[-1]
    for p in ["/usr/local/bin/wecom-cli", "/opt/homebrew/bin/wecom-cli"]:
        if os.path.exists(p):
            return p
    return "wecom-cli"


def get_authorized_user_id() -> str:
    """获取已授权的真人用户干净的 ID (woGox...)"""
    cli_bin = get_cli_bin()
    try:
        cmd = [cli_bin, "identity", "whoami"]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # 精确正则匹配 woGox 开头的真人用户 ID
        m = re.search(r'ID[：:]\s*(woGox[a-zA-Z0-9_\-]+)', res.stdout)
        if m:
            return m.group(1).strip()
    except Exception as e:
        print(f"[警告] 从 whoami 获取身份失败: {e}")

    # 回退使用 .env 或保底 ID
    fallback = os.getenv("WECOM_DEFAULT_SERVICER", "woGoxIDAAA18LCgBG6BdXpceqMbbQ6nw").strip()
    return fallback


def send_wecom_message(chat_id: str, content: str):
    """向企微单聊发送消息"""
    cli_bin = get_cli_bin()
    payload = json.dumps({"content": content}, ensure_ascii=False)
    cmd = [
        cli_bin, "message", "send",
        "--chat-id", chat_id,
        "--msg-type", "text",
        "--text", payload
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"  [!] 发送消息失败: {res.stderr.strip() or res.stdout.strip()}")


def fetch_recent_messages(chat_id: str, lookback_minutes: int = 30) -> list:
    """拉取最近单聊消息列表"""
    cli_bin = get_cli_bin()
    now = datetime.now()
    begin = (now - timedelta(minutes=lookback_minutes)).strftime("%Y-%m-%d %H:%M:%S")
    end = now.strftime("%Y-%m-%d %H:%M:%S")

    cmd = [
        cli_bin, "chat", "messages", "list",
        "--chat-id", chat_id,
        "--begin-time", begin,
        "--end-time", end
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        idx = res.stdout.find("{")
        if idx != -1:
            data = json.loads(res.stdout[idx:])
            return data.get("messages", [])
    except Exception as e:
        print(f"  [!] 轮询拉取消息报错: {e}")
    return []


def main():
    print("=" * 68)
    print(" 🚀 WeCom Robot - 企微真机实时联调监听服务 (已修复增强版)")
    print(" 模式: 基于当前已授权的 wecom-cli 开发者通道与你的手机端实时收发")
    print("=" * 68)

    chat_id = get_authorized_user_id()
    print(f"[*] 监听目标会话 ID: {chat_id}")

    # 初始化本地 Agent
    csv_path = os.path.join(BASE_DIR, os.getenv("CSV_DATA_PATH", "data/photo_delivery.csv"))
    storage = CsvStorage(csv_path)
    tool_executor = ToolExecutor(storage)
    agent = NativeAgent(tool_executor=tool_executor, debug=True)

    # 记录机器人自己发出的文本集合，坚决避免自己回复自己
    bot_sent_texts = set()

    # 1. 发送欢迎语
    greeting = f"🎉 萌萌在线客服已就绪！\n\n{WELCOME_MESSAGE}\n\n👉 提示：请直接在手机企微回复拍摄信息（如：11月2日 北京门店 陈麻子）体验自动交付。"
    bot_sent_texts.add(greeting.strip())
    print("[*] 正在向你的企业微信发送欢迎指引...")
    send_wecom_message(chat_id, greeting)
    print("[✓] 欢迎语已送达你的企业微信，请查看手机端！")

    # 启动时先把已经存在的消息标记为已处理，只响应启动后的新消息
    print("[*] 正在同步历史消息...")
    init_msgs = fetch_recent_messages(chat_id, lookback_minutes=60)
    processed_fingerprints = set()
    for m in init_msgs:
        content = m.get("text", {}).get("content", "").strip()
        send_time = m.get("send_time", "")
        processed_fingerprints.add(f"{send_time}_{content}")
    print(f"[*] 已同步 {len(processed_fingerprints)} 条历史消息，开始实时监听新消息...")

    history = []
    print("\n[🟢 监听中] 请在手机企业微信【小陈/机器人】聊天框中发送消息 (按 Ctrl+C 退出)...")

    while True:
        try:
            msgs = fetch_recent_messages(chat_id, lookback_minutes=15)
            # 按时间正序处理
            msgs_sorted = sorted(msgs, key=lambda x: x.get("send_time", ""))

            for m in msgs_sorted:
                if m.get("msg_type") == "text":
                    text_obj = m.get("text", {})
                    content = text_obj.get("content", "").strip()
                    send_time = m.get("send_time", "")
                    fingerprint = f"{send_time}_{content}"

                    # 1. 过滤已处理的消息
                    if fingerprint in processed_fingerprints:
                        continue

                    # 2. 过滤机器人自己发出的内容（避免循环回复）
                    if content in bot_sent_texts or "🎉 萌萌在线客服已就绪" in content or "【超级会员 V4】" in content:
                        processed_fingerprints.add(fingerprint)
                        continue

                    # 捕获到真人发来的新消息！
                    processed_fingerprints.add(fingerprint)
                    print(f"\n📩 [企微收到你的消息] ({send_time}): \033[94m{content}\033[0m")

                    # 驱动极简原生 Agent
                    reply, history = agent.chat(content, history)
                    print(f"🤖 [Agent 决策回复]:\n\033[92m{reply}\033[0m")

                    # 记录并发送给企微
                    bot_sent_texts.add(reply.strip())
                    send_wecom_message(chat_id, reply)
                    print("📤 [已成功推送至你的手机企业微信]")

            time.sleep(2)

        except KeyboardInterrupt:
            print("\n[!] 监听服务已手动退出")
            break
        except Exception as e:
            print(f"[!] 监听循环异常: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()
