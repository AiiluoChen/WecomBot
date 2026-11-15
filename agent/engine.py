"""
纯原生极简 Agent 核心引擎 (NativeAgent)
不使用任何重型框架，依托标准 OpenAI 客户端实现清晰、可靠、零黑盒的 Tool-Calling 循环。
"""
import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI
from .prompts import SYSTEM_PROMPT
from .tools import TOOLS_SCHEMA, ToolExecutor


class NativeAgent:
    def __init__(
        self,
        tool_executor: ToolExecutor,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        system_prompt: str = SYSTEM_PROMPT,
        debug: bool = True
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
        self.model_name = model_name or os.getenv("MODEL_NAME", "deepseek-chat")
        self.system_prompt = system_prompt
        self.tool_executor = tool_executor
        self.debug = debug

        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

        # 本地工具函数映射表
        self.tool_map = {
            "query_photo_pan": self.tool_executor.query_photo_pan,
            "escalate_to_human": self.tool_executor.escalate_to_human,
        }

    def chat(self, user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> (str, List[Dict[str, Any]]):
        """
        核心交互方法：接收用户输入与历史，驱动原生 Agent 循环，返回机器人回复与更新后的上下文
        """
        if history is None:
            history = []

        # 构建本轮消息链条：系统人设 + 对话历史 + 当前输入
        messages: List[Dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        max_turns = 5  # 防止工具调用循环死循环
        turn_count = 0

        while turn_count < max_turns:
            turn_count += 1
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                temperature=0.3
            )

            assistant_msg = response.choices[0].message
            # 记录 assistant 的输出（无论包含文字还是 tool_calls）
            messages.append(assistant_msg)

            # 1. 如果没有调用工具：说明模型做出了直接回复（如闲聊、追问、已完成交付）
            if not assistant_msg.tool_calls:
                reply_text = assistant_msg.content or ""
                # 更新外部历史记录 (仅保留 user 与 assistant 的纯文本交互)
                new_history = list(history)
                new_history.append({"role": "user", "content": user_message})
                new_history.append({"role": "assistant", "content": reply_text})
                return reply_text, new_history

            # 2. 如果触发了工具调用：逐个执行对应工具
            for tool_call in assistant_msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args_raw = tool_call.function.arguments
                
                try:
                    fn_args = json.loads(fn_args_raw)
                except Exception:
                    fn_args = {}

                if self.debug:
                    print(f"  [⚡ Agent Tool Call] -> {fn_name}({fn_args})")

                # 执行本地函数
                if fn_name in self.tool_map:
                    exec_fn = self.tool_map[fn_name]
                    result = exec_fn(**fn_args)
                else:
                    result = {"error": f"Unknown tool: {fn_name}"}

                # 将工具返回结果作为 role: tool 回传进 messages 列表
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })

        # 超出循环轮次的安全兜底
        return "亲亲，萌萌这边系统稍微有点繁忙，请稍等片刻再试哦！", history
