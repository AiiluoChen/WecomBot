#!/usr/bin/env python3
"""
pan_sync.py — 百度网盘子文件夹增量同步脚本
==============================================
功能：
  1. 通过 BaiduPCS-Py 扫描百度网盘指定根目录下的所有一级子文件夹
  2. 对新增/尚未分享的子文件夹自动生成分享链接与提取码
  3. 解析文件夹名称，提取客户信息字段
  4. 增量写入 data/photo_delivery.csv（机器人直接读取，代码无需改动）

运行方式：
  python3 sync/pan_sync.py

环境变量（写在 .env 或直接 export）：
  BAIDU_BDUSS          必填，网页版百度网盘登录 Cookie 中的 BDUSS 值
  BAIDU_STOKEN         必填，网页版百度网盘登录 Cookie 中的 STOKEN 值
  BAIDU_PAN_ROOT_DIR   百度网盘扫描根目录，默认 /相册交付
  BAIDU_SHARE_PWD      统一提取码（4位字母数字），留空则随机生成
  CSV_DATA_PATH        照片交付 CSV 路径，默认 data/photo_delivery.csv
  SYNC_DRY_RUN         设为 1 则只打印不写入（调试用）

文件夹命名规则（晚些由用户补充后填写 parse_folder_name 函数）：
  当前为占位实现，收到命名规则后直接替换该函数即可，其余代码不变。

依赖安装：
  pip install BaiduPCS-Py python-dotenv
"""

import csv
import os
import re
import json
import random
import string
import subprocess
import sys
from pathlib import Path
from typing import Optional

# ── 加载环境变量 ───────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    # 优先加载项目根目录的 .env
    _root = Path(__file__).parent.parent
    load_dotenv(_root / ".env", override=False)
except ImportError:
    pass  # 没装 python-dotenv 也没关系，直接读系统环境变量

# ── 配置 ───────────────────────────────────────────────────────────────────────
BDUSS       = os.getenv("BAIDU_BDUSS", "")
STOKEN      = os.getenv("BAIDU_STOKEN", "")
PAN_ROOT    = os.getenv("BAIDU_PAN_ROOT_DIR", "/相册交付")
SHARE_PWD   = os.getenv("BAIDU_SHARE_PWD", "")   # 留空=随机4位
CSV_PATH    = os.getenv("CSV_DATA_PATH", "data/photo_delivery.csv")
DRY_RUN     = os.getenv("SYNC_DRY_RUN", "0") == "1"
DEFAULT_STATUS = "ready"

# BaiduPCS-Py 可执行文件名（pip 安装后通常在 PATH 中）
BPCS_CMD = os.getenv("BPCS_CMD", "BaiduPCS-Py")

# ── 工具函数 ───────────────────────────────────────────────────────────────────

def random_pwd(n: int = 4) -> str:
    """生成随机 n 位小写字母+数字提取码"""
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def bpcs(args: list[str]) -> tuple[int, str]:
    """
    调用 BaiduPCS-Py 命令，返回 (returncode, stdout_text)。
    若 BDUSS/STOKEN 已通过 `BaiduPCS-Py useradd` 持久化登录则无需每次传入。
    """
    cmd = [BPCS_CMD] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout + result.stderr


def list_subdirs(root: str) -> list[str]:
    """
    列出百度网盘 root 目录下的一级子文件夹名称列表。
    BaiduPCS-Py ls 输出示例（每行一条）：
      d  2026-11-02 15:30  /相册交付/陈麻子_2026-11-02_大理双廊店
    """
    code, out = bpcs(["ls", root, "--no-highlight"])
    if code != 0:
        print(f"[ERROR] 列举目录失败: {out}", file=sys.stderr)
        return []

    dirs = []
    for line in out.splitlines():
        line = line.strip()
        # 以 'd' 开头的行为文件夹
        if line.startswith("d ") or line.startswith("d\t"):
            # 最后一个字段为完整路径，取文件夹名
            parts = line.split()
            if parts:
                full_path = parts[-1]
                folder_name = full_path.rstrip("/").split("/")[-1]
                dirs.append(folder_name)
    return dirs


def create_share(pan_path: str) -> tuple[str, str]:
    """
    对百度网盘中的 pan_path 创建分享链接，返回 (url, pwd)。
    若 SHARE_PWD 为空则随机生成4位提取码。
    """
    pwd = SHARE_PWD if SHARE_PWD else random_pwd()
    code, out = bpcs([
        "share", pan_path,
        "-p", pwd,
        "--pt", "0"   # 0 = 永久有效；改为 7 则7天
    ])
    if code != 0:
        print(f"[WARN] 创建分享失败 {pan_path}: {out}", file=sys.stderr)
        return "", pwd

    # 从输出中提取分享链接（通常格式为 https://pan.baidu.com/s/xxxx）
    url_match = re.search(r"https?://pan\.baidu\.com/s/\S+", out)
    url = url_match.group(0).rstrip("?") if url_match else ""
    return url, pwd


# ── ★ 核心解析函数 —— 晚些收到命名规则后填这里 ───────────────────────────────

def parse_folder_name(folder_name: str) -> Optional[dict]:
    """
    将文件夹名解析为机器人所需的字段字典。

    TODO: 收到用户的命名规则后，在此处实现具体解析逻辑。
          函数签名与返回结构保持不变，机器人代码无需任何改动。

    当前为示例占位——假设命名格式：
        {客户姓名}_{拍摄日期YYYY-MM-DD}_{门店名}
    示例：陈麻子_2026-11-02_大理双廊店

    返回字段（与 csv_storage.py 完全对齐）：
        customer_name  客户姓名
        shoot_date     拍摄日期（原始字符串，机器人内部会归一化）
        store_name     门店名称
        phone_tail     手机后4位（文件夹名中若没有则填空）
        status         交付状态（默认 ready）

    若无法解析则返回 None，该文件夹将被跳过并打印警告。
    """
    # ——— 示例规则（收到真实规则后替换这段）———
    parts = folder_name.split("_")
    if len(parts) < 3:
        # 命名不符合规范，跳过
        return None

    return {
        "customer_name": parts[0].strip(),
        "shoot_date":    parts[1].strip(),
        "store_name":    "_".join(parts[2:]).strip(),  # 门店名可能含下划线
        "phone_tail":    "",                            # 文件夹名中若有手机尾号可在此提取
        "status":        DEFAULT_STATUS,
    }
    # ——— 示例规则结束 ———


# ── CSV 增量写入 ────────────────────────────────────────────────────────────────

FIELDNAMES = ["customer_name", "shoot_date", "store_name", "phone_tail",
              "pan_url", "pan_pwd", "status"]


def load_existing_keys(csv_path: str) -> set[str]:
    """
    读取现有 CSV，返回已入库的唯一键集合（customer_name + shoot_date）。
    用于增量判断：已存在的记录不重复创建分享链接。
    """
    keys = set()
    if not os.path.exists(csv_path):
        return keys
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = f"{row.get('customer_name','')}|{row.get('shoot_date','')}"
            keys.add(key)
    return keys


def append_records(csv_path: str, records: list[dict]):
    """将新记录追加到 CSV，若文件不存在则创建并写入表头。"""
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerows(records)


# ── 主流程 ─────────────────────────────────────────────────────────────────────

def main():
    if not BDUSS or not STOKEN:
        print(
            "[WARN] 未设置 BAIDU_BDUSS / BAIDU_STOKEN 环境变量。\n"
            "       如已通过 `BaiduPCS-Py useradd` 持久化登录，可忽略此警告。"
        )

    print(f"[INFO] 扫描百度网盘目录: {PAN_ROOT}")
    subdirs = list_subdirs(PAN_ROOT)
    print(f"[INFO] 发现 {len(subdirs)} 个子文件夹")

    if not subdirs:
        print("[INFO] 无子文件夹，退出。")
        return

    existing_keys = load_existing_keys(CSV_PATH)
    print(f"[INFO] CSV 中已有 {len(existing_keys)} 条记录，仅同步增量")

    new_records = []
    for folder in subdirs:
        info = parse_folder_name(folder)
        if info is None:
            print(f"[SKIP] 命名无法解析，跳过: {folder}")
            continue

        key = f"{info['customer_name']}|{info['shoot_date']}"
        if key in existing_keys:
            print(f"[SKIP] 已存在，跳过: {folder}")
            continue

        # 生成分享链接
        pan_path = f"{PAN_ROOT.rstrip('/')}/{folder}"
        print(f"[SHARE] 正在为 {pan_path} 创建分享链接...")

        if DRY_RUN:
            url, pwd = "https://pan.baidu.com/s/DRY_RUN", "test"
            print(f"  [DRY_RUN] url={url}  pwd={pwd}")
        else:
            url, pwd = create_share(pan_path)

        if not url:
            print(f"[WARN] 未能获取分享链接，跳过: {folder}")
            continue

        record = {
            "customer_name": info["customer_name"],
            "shoot_date":    info["shoot_date"],
            "store_name":    info["store_name"],
            "phone_tail":    info.get("phone_tail", ""),
            "pan_url":       url,
            "pan_pwd":       pwd,
            "status":        info.get("status", DEFAULT_STATUS),
        }
        new_records.append(record)
        print(f"  ✅ {info['customer_name']} | {info['shoot_date']} | {url}")

    if new_records and not DRY_RUN:
        append_records(CSV_PATH, new_records)
        print(f"\n[DONE] 新增 {len(new_records)} 条记录 → {CSV_PATH}")
    elif new_records and DRY_RUN:
        print(f"\n[DRY_RUN] 将写入 {len(new_records)} 条记录（未实际写入）")
    else:
        print("\n[DONE] 无新增记录。")


if __name__ == "__main__":
    main()
