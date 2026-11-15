"""
客户会话状态管理器 (SessionManager)
负责记录每个微信外部客户的接待状态：
1. BOT_ACTIVE: 机器人自动接待（自动回复网盘链接、闲聊）
2. HUMAN_TAKEOVER: 真人客服已接管（机器人保持静默，严禁插话打扰真人沟通）
"""
import time
from typing import Dict, Any, List, Optional
from enum import Enum


class SessionState(str, Enum):
    BOT_ACTIVE = "bot_active"          # 机器人托管中
    HUMAN_TAKEOVER = "human_takeover"  # 人工接管中 (机器人静默)


class CustomerSession:
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.state: SessionState = SessionState.BOT_ACTIVE
        self.history: List[Dict[str, Any]] = []
        self.takeover_time: Optional[float] = None
        self.takeover_reason: Optional[str] = None
        self.last_active_time: float = time.time()

    def touch(self):
        self.last_active_time = time.time()

    def set_human_takeover(self, reason: str):
        self.state = SessionState.HUMAN_TAKEOVER
        self.takeover_time = time.time()
        self.takeover_reason = reason
        self.touch()

    def reset_to_bot(self):
        self.state = SessionState.BOT_ACTIVE
        self.takeover_time = None
        self.takeover_reason = None
        self.touch()

    def is_human_takeover(self, timeout_hours: int = 24) -> bool:
        """检查是否处于人工接管中，若超过设定的超时时间（默认24小时）则自动回退给机器人"""
        if self.state != SessionState.HUMAN_TAKEOVER:
            return False
        # 超时保护：超过 24 小时未结束接待，自动释放回机器人
        if self.takeover_time and (time.time() - self.takeover_time > timeout_hours * 3600):
            self.reset_to_bot()
            return False
        return True


class SessionManager:
    """全局单例内存会话管理器"""

    def __init__(self):
        self._sessions: Dict[str, CustomerSession] = {}

    def get_or_create(self, customer_id: str) -> CustomerSession:
        if customer_id not in self._sessions:
            self._sessions[customer_id] = CustomerSession(customer_id)
        return self._sessions[customer_id]

    def is_human_active(self, customer_id: str) -> bool:
        """判断该客户是否正在由真人接管"""
        session = self.get_or_create(customer_id)
        return session.is_human_takeover()

    def trigger_human_takeover(self, customer_id: str, reason: str):
        """将该客户标记为人工接管"""
        session = self.get_or_create(customer_id)
        session.set_human_takeover(reason)

    def release_to_bot(self, customer_id: str):
        """人工接待完毕，释放给机器人"""
        session = self.get_or_create(customer_id)
        session.reset_to_bot()

    def get_history(self, customer_id: str) -> List[Dict[str, Any]]:
        session = self.get_or_create(customer_id)
        return session.history

    def update_history(self, customer_id: str, new_history: List[Dict[str, Any]]):
        session = self.get_or_create(customer_id)
        session.history = new_history
        session.touch()


# 默认单例
session_mgr = SessionManager()
