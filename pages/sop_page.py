"""主播带新计划 · SOP 执行台页面。

读写型页面：Python 侧只负责渲染 HTML 壳，数据全部通过 /api/sop/* 加载。
"""
from pages.base import BasePage


class SOPPage(BasePage):
    def __init__(self):
        super().__init__(
            page_id="sop",
            title="主播带新计划执行台",
            template="sop.html",
        )
