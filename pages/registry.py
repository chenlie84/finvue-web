"""
页面注册中心
管理所有可用的页面
"""
from typing import Dict, Type
from pages.base import BasePage
from pages.crs_page import CRSPage
from pages.chat_page import ChatPage


class PageRegistry:
    """页面注册表"""
    
    _pages: Dict[str, BasePage] = {}
    
    @classmethod
    def register(cls, page: BasePage):
        """
        注册页面
        
        Args:
            page: 页面实例
        """
        cls._pages[page.page_id] = page
    
    @classmethod
    def get(cls, page_id: str) -> BasePage:
        """
        获取页面
        
        Args:
            page_id: 页面ID
            
        Returns:
            页面实例
            
        Raises:
            KeyError: 页面不存在
        """
        if page_id not in cls._pages:
            raise KeyError(f"Page '{page_id}' not found")
        return cls._pages[page_id]
    
    @classmethod
    def get_all(cls) -> Dict[str, BasePage]:
        """获取所有页面"""
        return cls._pages.copy()
    
    @classmethod
    def list_page_ids(cls) -> list:
        """获取所有页面ID"""
        return list(cls._pages.keys())


# 注册所有页面
def init_pages():
    """初始化并注册所有页面"""
    PageRegistry.register(CRSPage())
    PageRegistry.register(ChatPage())


# 自动初始化
init_pages()
