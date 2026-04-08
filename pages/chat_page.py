"""
AI 聊天页面
调用 Qwen 大模型进行对话
"""
from typing import Dict, Any, List
from pages.base import BasePage


class ChatPage(BasePage):
    """AI 聊天页面"""

    def __init__(self):
        super().__init__(
            page_id="chat",
            title="AI 智能助手",
            template="chat.html",
        )

    def get_data(self) -> List[Dict[str, Any]]:
        """聊天页面无需预加载数据"""
        return []

    def get_context(self) -> Dict[str, Any]:
        """聊天页面上下文"""
        return {
            "title": self.title,
        }
