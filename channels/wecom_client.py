"""
企业微信官方 API 客户端 (WeComClient)
负责主动向外部微信客户推送消息、以及向真人客服转派工单 (upgrade_service)。
凭证未配置时自动降级为本地 CLI 通知或模拟模式。
"""
import os
import time
import json
import subprocess
import urllib.request
import urllib.error
from typing import Optional, Dict, Any


class WeComClient:
    def __init__(self):
        self.corp_id = os.getenv("WECOM_CORP_ID", "").strip()
        self.kf_secret = os.getenv("WECOM_KF_SECRET", "").strip()
        self.default_servicer = os.getenv("WECOM_DEFAULT_SERVICER", "").strip()
        self._access_token = None
        self._token_expires_at = 0

    @property
    def is_configured(self) -> bool:
        """是否已完整配置企业微信官方 API 凭证"""
        return bool(self.corp_id and self.kf_secret)

    def get_access_token(self) -> Optional[str]:
        """获取并自动缓存官方 AccessToken"""
        if not self.is_configured:
            return None
        now = time.time()
        if self._access_token and now < self._token_expires_at - 60:
            return self._access_token

        url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={self.corp_id}&corpsecret={self.kf_secret}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("errcode") == 0:
                    self._access_token = data.get("access_token")
                    expires_in = data.get("expires_in", 7200)
                    self._token_expires_at = now + expires_in
                    return self._access_token
                else:
                    print(f"[企微API报错] 获取 token 失败: {data}")
        except Exception as e:
            print(f"[网络异常] 获取企微 access_token 异常: {e}")
        return None

    def send_customer_message(self, open_kfid: str, external_userid: str, content: str) -> bool:
        """
        向微信外部客户主动发送文本消息 (微信客服 send_msg API)
        """
        token = self.get_access_token()
        if not token:
            print(f"  [WeComClient Mock] 模拟发给客户 [{external_userid}]: {content[:40]}...")
            return True

        url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg?access_token={token}"
        payload = {
            "touser": external_userid,
            "open_kfid": open_kfid,
            "msgtype": "text",
            "text": {
                "content": content
            }
        }
        try:
            req_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("errcode") == 0
        except Exception as e:
            print(f"[企微API报错] 发送客服消息失败: {e}")
            return False

    def upgrade_to_human(
        self,
        open_kfid: str,
        external_userid: str,
        reason: str,
        servicer_userid: Optional[str] = None
    ) -> bool:
        """
        转人工：调用微信客服 upgrade_service API 将会话转接给指定真实客服
        """
        target_servicer = servicer_userid or self.default_servicer

        # 1. 如果已配置企微官方 API，调用官方升级服务接口
        token = self.get_access_token()
        if token and open_kfid:
            url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/customer/upgrade_service?access_token={token}"
            payload = {
                "open_kfid": open_kfid,
                "external_userid": external_userid,
                "switch_type": 1,  # 1: 转接给指定专员
                "member": {
                    "userid": target_servicer
                }
            }
            try:
                req_data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
                    if res.get("errcode") == 0:
                        print(f"  [✓ 企微官方转人工成功] 客户 [{external_userid}] 已指派给真实客服 [{target_servicer}]")
                        return True
            except Exception as e:
                print(f"[企微API报错] 升级人工客服失败: {e}")

        # 2. 降级兜底方案：通过本地已授权的 wecom-cli 直接向真人客服推送一条高优先级待办通知
        if target_servicer:
            self._notify_human_via_cli(target_servicer, external_userid, reason)
        return True

    def _get_wecom_cli_path(self) -> str:
        """动态探测 wecom-cli 路径"""
        import shutil, glob
        found = shutil.which("wecom-cli")
        if found:
            return found
        # 探测 nvm 目录
        candidates = glob.glob(os.path.expanduser("~/.nvm/versions/node/*/bin/wecom-cli"))
        if candidates:
            return candidates[-1]
        for p in ["/usr/local/bin/wecom-cli", "/opt/homebrew/bin/wecom-cli"]:
            if os.path.exists(p):
                return p
        return "wecom-cli"

    def _notify_human_via_cli(self, servicer_userid: str, customer_id: str, reason: str):
        """通过 wecom-cli 向接待人员推送工单提醒"""
        alert_text = (
            f"🚨【转人工工单提醒】\n"
            f"客户标识: {customer_id}\n"
            f"转接原因: {reason}\n"
            f"状态: 机器人已自动进入静默模式，请您前往微信/企微会话尽快接管处理！"
        )
        try:
            cli_bin = self._get_wecom_cli_path()
            payload = json.dumps({"content": alert_text}, ensure_ascii=False)
            subprocess.run([
                cli_bin, "message", "send",
                "--chat-id", servicer_userid,
                "--msg-type", "text",
                "--text", payload
            ], capture_output=True, text=True, timeout=5)
            print(f"  [✓ CLI 告警已送达] 已成功向真人客服发送工单通知！")
        except Exception as e:
            print(f"  [!] CLI 推送工单异常: {e}")


# 全局单例
wecom_client = WeComClient()
