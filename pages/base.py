"""
页面基类
定义页面的通用接口
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List


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
    
    @abstractmethod
    def get_data(self) -> List[Dict[str, Any]]:
        """
        获取页面数据
        
        Returns:
            数据列表
        """
        pass
    
    def get_context(self) -> Dict[str, Any]:
        """
        获取模板上下文
        
        Returns:
            模板上下文字典
        """
        from datetime import datetime
        
        return {
            "title": self.title,
            "rows": self.get_data(),
            "cutoff_time": datetime.now().strftime("%Y-%m-%d %H:00:00"),
        }

