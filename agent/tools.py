"""
工具箱定义 (Tools Schema) 与本地执行器
支持查询照片网盘链接以及与企微官方转人工 API 深度联动。
"""
from typing import Dict, Any, Optional
from storage.base import StorageBase
from core.session_manager import session_mgr
from channels.wecom_client import wecom_client


# OpenAI 兼容的 Tools 规范定义
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "query_photo_pan",
            "description": "根据客户的拍摄时间、门店或电话后4位、真实姓名，在系统数据源中检索其照片的百度网盘链接和提取码。",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {
                        "type": "string",
                        "description": "客户真实姓名，例如：陈麻子、李小萌"
                    },
                    "shoot_date": {
                        "type": "string",
                        "description": "客户提及的拍摄日期，例如：11月2日、2026-11-02、11-02"
                    },
                    "store_or_phone": {
                        "type": "string",
                        "description": "客户提及的拍摄门店（如北京门店、大理双廊店）或者手机号后4位（如6224），二选一"
                    }
                },
                "required": ["customer_name", "shoot_date", "store_or_phone"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "当识别到客户投诉、强烈不满、要求重修/退款、或者明确要求人工客服时，触发人工转接与内部告警，并将机器人置为静默模式。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "转人工原因：如投诉不满意、深度精修重修、客户主动要求人工、数据未查到等"
                    },
                    "customer_intent": {
                        "type": "string",
                        "description": "客户当前核心诉求与关键上下文简述"
                    }
                },
                "required": ["reason"]
            }
        }
    }
]


class ToolExecutor:
    """工具本地执行器，解耦数据存储与业务动作"""

    def __init__(self, storage: StorageBase):
        self.storage = storage
        self.current_customer_id: str = "default_user"
        self.current_open_kfid: str = ""

    def set_context(self, customer_id: str, open_kfid: str = ""):
        """设置当前处理的客户上下文 ID"""
        self.current_customer_id = customer_id
        self.current_open_kfid = open_kfid

    def query_photo_pan(
        self,
        customer_name: str,
        shoot_date: Optional[str] = None,
        store_or_phone: Optional[str] = None
    ) -> Dict[str, Any]:
        """查询照片交付记录，强制三要素完整校验"""
        if not customer_name or not shoot_date or not store_or_phone:
            return {
                "status": "missing_info",
                "message": "查询拒绝：必须同时具备【拍摄时间】、【拍摄门店或电话后4位】、【客户姓名】三项要素。请引导客户补充缺失的信息，严禁自行编造链接。"
            }

        record = self.storage.query_delivery(
            customer_name=customer_name,
            shoot_date=shoot_date,
            store_or_phone=store_or_phone
        )
        if not record:
            return {
                "status": "not_found",
                "message": f"未在系统中找到名为【{customer_name}】的照片交付记录，请与客户核对拍摄日期或门店。"
            }
        
        status = record.get("status", "ready")
        if status == "ready":
            return {
                "status": "ready",
                "customer_name": record["customer_name"],
                "pan_url": record.get("pan_url", ""),
                "pan_pwd": record.get("pan_pwd", ""),
                "store_name": record.get("store_name", ""),
                "shoot_date": record.get("shoot_date", "")
            }
        elif status == "retouching":
            return {
                "status": "retouching",
                "customer_name": record["customer_name"],
                "message": "照片仍在精修制作排期中，底片将于次日20点前发完，精修需约7个工作日。"
            }
        else:
            return {
                "status": status,
                "customer_name": record["customer_name"],
                "message": f"当前状态：{status}"
            }

    def escalate_to_human(self, reason: str, customer_intent: str = "") -> Dict[str, Any]:
        """
        触发转人工动作：
        1. 标记会话状态为 HUMAN_TAKEOVER（机器人立刻闭嘴静默）
        2. 调用企微 upgrade_service 转派给真实客服 / 推送工单预警
        """
        print(f"\n[🚨 转人工触发] 客户 [{self.current_customer_id}] | 原因: {reason} | 诉求: {customer_intent}")

        # 1. 状态流转 -> 机器人静默
        session_mgr.trigger_human_takeover(self.current_customer_id, reason=reason)

        # 2. 企微接口动作 -> 通知/转接真人客服
        wecom_client.upgrade_to_human(
            open_kfid=self.current_open_kfid,
            external_userid=self.current_customer_id,
            reason=reason
        )

        return {
            "status": "escalated",
            "message": "已成功记录工单，机器人已进入静默模式，会话已流转给真人客服。",
            "ticket_reason": reason
        }
