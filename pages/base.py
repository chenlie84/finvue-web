"""
页面基类
定义页面的通用接口
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import datetime


class BasePage(ABC):
    """页面基类"""
    
    def __init__(self, page_id: str, title: str, template: str):
        """
        初始化页面
        
        Args:
            page_id: 页面唯一标识
            title: 页面标题
            template: 模板文件名
        """
        self.page_id = page_id
        self.title = title
        self.template = template
    
    def get_data(self) -> List[Dict[str, Any]]:
        """
        获取页面数据。默认返回空列表，读写型页面（如 SOP 执行台）可不覆盖此方法。

        Returns:
            数据列表
        """
        return []
    
    def get_context(self) -> Dict[str, Any]:
        """
        获取模板上下文
        
        Returns:
            模板上下文字典
        """
        rows = self.get_data()
        cutoff_time = self._get_cutoff_time_from_rows(rows)

        return {
            "title": self.title,
            "rows": rows,
            "cutoff_time": cutoff_time,
        }

    @staticmethod
    def _get_cutoff_time_from_rows(rows: List[Dict[str, Any]]) -> str:
        """
        根据数据中的“时间”字段计算截止时间（整点），若不存在则使用当前时间
        """
        cutoff_dt: datetime | None = None

        for row in rows or []:
            value = row.get("时间")
            if not value:
                continue

            if isinstance(value, datetime):
                dt = value
            else:
                try:
                    dt = datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
                except (TypeError, ValueError):
                    continue

            if cutoff_dt is None or dt > cutoff_dt:
                cutoff_dt = dt

        if cutoff_dt is None:
            cutoff_dt = datetime.now()

        cutoff_dt = cutoff_dt.replace(minute=0, second=0, microsecond=0)
        return cutoff_dt.strftime("%Y-%m-%d %H:00:00")
