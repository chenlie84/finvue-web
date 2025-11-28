"""
CRS填写客户数页面
"""
from typing import Dict, Any, List

from pages.base import BasePage
from db_utils import fetch_all_rows


class CRSPage(BasePage):
    """CRS填写客户数页面"""
    
    def __init__(self):
        super().__init__(
            page_id="crs",
            title="CRS填写客户数",
            template="crs_report.html"
        )
    
    def get_data(self) -> List[Dict[str, Any]]:
        """获取CRS数据"""
        return fetch_all_rows()
