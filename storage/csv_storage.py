"""
本地 CSV 数据存储实现 (CsvStorage)
用于单机测试与快速交付，包含智能日期归一化与模糊匹配逻辑。
"""
import csv
import os
import re
from typing import Optional, Dict, Any, List
from .base import StorageBase


def normalize_date(date_str: Optional[str]) -> str:
    """
    将多样化的自然语言日期归一化为 MM-DD 格式以方便比对
    例如: "11月2日", "11-02", "11.02", "2026-11-02", "2026/11/2" -> "11-02"
    """
    if not date_str:
        return ""
    s = str(date_str).strip()
    # 匹配月和日: 支持 "11月2日", "11-02", "11.2", "11/2"
    m = re.search(r'(?:(\d{4})[-/年\.\s])?(\d{1,2})[-/月\.\s](\d{1,2})', s)
    if m:
        month = int(m.group(2))
        day = int(m.group(3))
        return f"{month:02d}-{day:02d}"
    return s


class CsvStorage(StorageBase):
    def __init__(self, csv_path: str = "data/photo_delivery.csv"):
        self.csv_path = csv_path
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.csv_path):
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            with open(self.csv_path, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["customer_name", "shoot_date", "store_name", "phone_tail", "pan_url", "pan_pwd", "status"])

    def _load_all(self) -> List[Dict[str, str]]:
        if not os.path.exists(self.csv_path):
            return []
        records = []
        with open(self.csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append({k.strip(): v.strip() for k, v in row.items() if k})
        return records

    def query_delivery(
        self,
        customer_name: str,
        shoot_date: Optional[str] = None,
        store_or_phone: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        多重条件弹性匹配：
        1. 必须匹配客户姓名（支持去除空格后一致）
        2. 若提供了拍摄时间，校验日期归一化后是否一致
        3. 若提供了门店或尾号，匹配门店包含或尾号一致
        """
        records = self._load_all()
        target_name = customer_name.strip()
        norm_target_date = normalize_date(shoot_date)
        target_store_or_phone = store_or_phone.strip() if store_or_phone else ""

        for r in records:
            name_in_record = r.get("customer_name", "")
            # 姓名必须匹配
            if target_name not in name_in_record and name_in_record not in target_name:
                continue

            # 日期校验（若输入了日期）
            if norm_target_date:
                record_date_norm = normalize_date(r.get("shoot_date", ""))
                if record_date_norm and record_date_norm != norm_target_date:
                    continue

            # 门店或手机尾号校验（若输入了门店或尾号）
            if target_store_or_phone:
                r_store = r.get("store_name", "")
                r_phone = r.get("phone_tail", "")
                # 检查是否匹配门店或手机后4位
                store_matched = (target_store_or_phone in r_store or r_store in target_store_or_phone) if r_store else False
                phone_matched = (target_store_or_phone in r_phone or r_phone in target_store_or_phone) if r_phone else False
                if not (store_matched or phone_matched):
                    continue

            # 匹配成功，返回标准命中的字典
            return {
                "customer_name": r.get("customer_name"),
                "shoot_date": r.get("shoot_date"),
                "store_name": r.get("store_name"),
                "phone_tail": r.get("phone_tail"),
                "pan_url": r.get("pan_url"),
                "pan_pwd": r.get("pan_pwd"),
                "status": r.get("status", "ready")
            }

        return None
