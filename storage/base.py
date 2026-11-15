"""
数据存储层抽象基类 (StorageBase)
实现数据持久化与业务逻辑解耦，方便未来无缝迁移至 MySQL、PostgreSQL 或企业微信智能表格。
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


class StorageBase(ABC):
    @abstractmethod
    def query_delivery(
        self,
        customer_name: str,
        shoot_date: Optional[str] = None,
        store_or_phone: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        根据客户要素查询交付记录
        :param customer_name: 客户姓名
        :param shoot_date: 拍摄日期
        :param store_or_phone: 拍摄门店名称或手机后4位
        :return: 命中记录字典，未找到返回 None
        """
        pass
