#!/usr/bin/env python3
"""
keep_alive.py — 百度网盘 Cookie 定期保活脚本
============================================
功能：
  通过周期性向百度网盘官方接口发送鉴权请求（如获取用户信息、模板变量），
  刷新会话活跃时间，防止 BDUSS / STOKEN 长期不使用而失效。

用法：
  python3 sync/keep_alive.py
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

# 自动寻找并读取 .env
def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k not in os.environ:
                        os.environ[k] = v

load_env()

BDUSS = os.getenv("BAIDU_BDUSS", "").strip()
STOKEN = os.getenv("BAIDU_STOKEN", "").strip()

def ping():
    if not BDUSS or not STOKEN:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] 缺少 BAIDU_BDUSS 或 BAIDU_STOKEN，请在 .env 中配置")
        sys.exit(1)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Cookie': f'BDUSS={BDUSS}; STOKEN={STOKEN}',
        'Referer': 'https://pan.baidu.com/disk/main'
    }

    url = 'https://pan.baidu.com/api/gettemplatevariable?clienttype=0&app_id=250528&web=1&fields=[%22bdstoken%22,%22uk%22]'
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            errno = data.get("errno")
            now_str = time.strftime('%Y-%m-%d %H:%M:%S')
            if errno == 0:
                uk = data.get("result", {}).get("uk")
                print(f"[{now_str}] [SUCCESS] 百度网盘保活心跳成功 | UK: {uk}")
                return True
            else:
                print(f"[{now_str}] [WARN] 百度网盘保活返回异常: {data}")
                return False
    except Exception as e:
        now_str = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{now_str}] [ERROR] 百度网盘保活请求失败: {e}")
        return False

if __name__ == "__main__":
    success = ping()
    sys.exit(0 if success else 1)
