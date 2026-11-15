"""
项目主启动入口 (FastAPI Server)
整合极简原生 Agent、本地存储适配器与 Webhook 接口服务。
"""
import os
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

# 加载 .env 环境变量
load_dotenv()

from storage.csv_storage import CsvStorage
from agent.tools import ToolExecutor
from agent.engine import NativeAgent
from channels.wecom_webhook import router as wecom_router, set_agent_instance

app = FastAPI(
    title="WeCom Robot 旅拍客服自动化系统",
    description="基于纯原生极简 Agent 循环的客服装配与网盘交付系统",
    version="1.0.0"
)

# 1. 基础服务组件初始化
csv_path = os.getenv("CSV_DATA_PATH", "data/photo_delivery.csv")
storage = CsvStorage(csv_path)
tool_executor = ToolExecutor(storage)
agent = NativeAgent(tool_executor=tool_executor, debug=True)

# 注入 Agent 与 ToolExecutor 至 Webhook 通道
set_agent_instance(agent, tool_executor)
app.include_router(wecom_router)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health_check():
    return {"status": "ok", "agent": "ready", "model": os.getenv("MODEL_NAME", "deepseek-chat")}


@app.post("/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest):
    """供第三方系统或小程序调用的标准 HTTP 聊天接口"""
    reply, _ = agent.chat(req.message)
    return ChatResponse(reply=reply)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"🚀 WeCom Robot 服务正在启动: http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=True)
