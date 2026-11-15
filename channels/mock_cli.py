"""
本地终端交互式模拟器 (Mock CLI)
无需配置复杂的企业微信网络与公网穿透，直接在终端模拟客户进线与全流程交互。
"""
import sys
import os
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv()

# 确保项目根路径进入 sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from storage.csv_storage import CsvStorage
from agent.tools import ToolExecutor
from agent.engine import NativeAgent
from agent.prompts import WELCOME_MESSAGE


def main():
    print("=" * 65)
    print(" 🤖 旅拍客服机器人 (WeCom Robot) - 本地终端交互模拟器")
    print(" 说明: 直接扮演客户发消息，输入 'exit' 或 'quit' 退出")
    print("=" * 65)

    # 1. 初始化存储与执行器
    csv_path = os.getenv("CSV_DATA_PATH", "data/photo_delivery.csv")
    full_csv_path = os.path.join(BASE_DIR, csv_path)
    storage = CsvStorage(full_csv_path)
    tool_executor = ToolExecutor(storage)

    # 2. 初始化纯原生 Agent 引擎
    agent = NativeAgent(tool_executor=tool_executor, debug=True)

    # 3. 模拟客户进线，自动弹出欢迎语
    print("\n【系统事件: 客户进入会话】")
    print("-----------------------------------------------------------------")
    print(f"\033[92m[萌萌@修图中心旅咔]\033[0m:\n{WELCOME_MESSAGE}")
    print("-----------------------------------------------------------------")

    history = []

    # 4. 交互循环
    while True:
        try:
            user_input = input("\n\033[94m[你 (客户)]\033[0m: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("\n[模拟器已退出]")
                break

            # 调用原生 Agent
            reply, history = agent.chat(user_input, history)

            print(f"\n\033[92m[萌萌@修图中心旅咔]\033[0m:\n{reply}")

        except KeyboardInterrupt:
            print("\n\n[模拟器已强制中断]")
            break
        except Exception as e:
            print(f"\n\033[91m[运行异常]\033[0m: {e}")


if __name__ == "__main__":
    main()
