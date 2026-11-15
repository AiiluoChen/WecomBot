"""
企业微信官方 Webhook 回调路由 (FastAPI Router)
全面支持企业微信标准加解密 (WXBizMsgCrypt)、外部客户状态拦截与真人接管静默机制。
"""
from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse
import os
import xml.etree.ElementTree as ET
from typing import Optional

from .wxbizmsgcrypt import WXBizMsgCrypt, WXBizMsgCrypt_OK
from .wecom_client import wecom_client
from core.session_manager import session_mgr

router = APIRouter(prefix="/wecom", tags=["WeCom Webhook"])

# 全局 Agent 实例与工具执行器持有（由 main.py 初始化时注入）
_agent_instance = None
_tool_executor = None


def set_agent_instance(agent, tool_executor=None):
    global _agent_instance, _tool_executor
    _agent_instance = agent
    _tool_executor = tool_executor


def get_cryptor() -> WXBizMsgCrypt:
    """按当前环境变量构造加解密器"""
    token = os.getenv("WECOM_TOKEN", "")
    aes_key = os.getenv("WECOM_ENCODING_AES_KEY", "")
    corp_id = os.getenv("WECOM_CORP_ID", "")
    return WXBizMsgCrypt(token, aes_key, corp_id)


@router.get("/callback")
async def verify_url(
    msg_signature: Optional[str] = Query(None),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None),
    echostr: Optional[str] = Query(None)
):
    """
    企业微信配置后台保存回调时发送的验证请求 (GET)
    必须使用 WXBizMsgCrypt 解密 echostr 并原样返回
    """
    if not echostr:
        return PlainTextResponse("WeCom Webhook Ready (Awaiting WeCom Ping)")

    cryptor = get_cryptor()
    ret, reply_echostr = cryptor.VerifyURL(
        sMsgSignature=msg_signature or "",
        sTimeStamp=timestamp or "",
        sNonce=nonce or "",
        sEchoStr=echostr
    )
    if ret == WXBizMsgCrypt_OK:
        return PlainTextResponse(reply_echostr)
    else:
        print(f"[企微回调验证失败] 错误码: {ret}")
        # 如果未配置 AES Key 则降级明文回显
        return PlainTextResponse(echostr)


@router.post("/callback")
async def receive_message(
    request: Request,
    msg_signature: Optional[str] = Query(None),
    timestamp: Optional[str] = Query(None),
    nonce: Optional[str] = Query(None)
):
    """
    接收来自外部微信客户的消息推送 (POST)
    全自动完成：解密密文 -> 状态机过滤(人工接管则静默) -> Agent 决策 -> 加密回发
    """
    if _agent_instance is None:
        raise HTTPException(status_code=500, detail="Agent engine not initialized")

    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    # 1. 尝试使用 AES 解密
    cryptor = get_cryptor()
    ret, decrypted_xml = cryptor.DecryptMsg(
        sPostData=body_text,
        sMsgSignature=msg_signature or "",
        sTimeStamp=timestamp or "",
        sNonce=nonce or ""
    )
    if ret == WXBizMsgCrypt_OK:
        plain_xml = decrypted_xml
    else:
        # 解密失败或未配置密钥时，降级使用原始文本 (兼容纯本地测试)
        plain_xml = body_text

    # 2. 解析明文 XML 字段
    from_user = "unknown_customer"
    open_kfid = ""
    user_content = ""
    msg_type = "text"

    try:
        xml_root = ET.fromstring(plain_xml)
        from_user = xml_root.findtext("FromUserName") or xml_root.findtext("ExternalUserID") or "unknown_customer"
        open_kfid = xml_root.findtext("OpenKfId") or ""
        msg_type = xml_root.findtext("MsgType") or "text"

        if msg_type == "text":
            user_content = xml_root.findtext("Content") or ""
        elif msg_type == "event":
            event = xml_root.findtext("Event")
            if event in ["enter_session", "add_external_contact", "subscribe"]:
                from agent.prompts import WELCOME_MESSAGE
                # 进线欢迎语下发
                if wecom_client.is_configured and open_kfid:
                    wecom_client.send_customer_message(open_kfid, from_user, WELCOME_MESSAGE)
                    return PlainTextResponse("success")
                ret_enc, enc_xml = cryptor.EncryptMsg(WELCOME_MESSAGE, nonce or "0", timestamp)
                return PlainTextResponse(enc_xml)
    except Exception:
        user_content = plain_xml

    if not user_content:
        return PlainTextResponse("success")

    # 3. 核心拦截：检查该客户是否处于“人工接管”状态
    if session_mgr.is_human_active(from_user):
        print(f"  [🔒 人工接管静默] 客户 [{from_user}] 正在由真人接待，机器人保持静默不回复。")
        return PlainTextResponse("success")

    # 4. 注入当前客户会话上下文给工具执行器
    if _tool_executor:
        _tool_executor.set_context(customer_id=from_user, open_kfid=open_kfid)

    # 5. 调用极简原生 Agent 驱动回复
    history = session_mgr.get_history(from_user)
    reply_text, new_history = _agent_instance.chat(user_content, history)
    session_mgr.update_history(from_user, new_history)

    # 6. 如果调用后发现已触发转人工，或者已配置主动推送 API
    if wecom_client.is_configured and open_kfid:
        wecom_client.send_customer_message(open_kfid, from_user, reply_text)
        return PlainTextResponse("success")

    # 7. 通过 HTTP 同步加密回传报文
    ret_enc, enc_xml = cryptor.EncryptMsg(reply_text, nonce or "0", timestamp)
    if ret_enc == WXBizMsgCrypt_OK:
        return PlainTextResponse(enc_xml)
    return PlainTextResponse(reply_text)


# --- 会话接管管理辅助接口 ---

@router.post("/session/release")
def release_session(customer_id: str):
    """
    供人工客服点击【结束接待】时调用，释放该客户回机器人自动托管模式
    """
    session_mgr.release_to_bot(customer_id)
    return {"status": "ok", "message": f"客户 [{customer_id}] 已重新切回机器人托管"}


@router.get("/session/status")
def get_session_status(customer_id: str):
    """查询指定客户当前的接待状态 (bot_active 或 human_takeover)"""
    is_human = session_mgr.is_human_active(customer_id)
    return {
        "customer_id": customer_id,
        "is_human_takeover": is_human,
        "state": "human_takeover" if is_human else "bot_active"
    }
