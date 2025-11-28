# 数据可视化项目 - 扩展指南

## 项目结构

```
data_viz/
├── pages/              # 页面模块目录
│   ├── __init__.py
│   ├── base.py        # 页面基类
│   ├── crs_page.py    # CRS页面实现
│   └── registry.py    # 页面注册中心
├── templates/         # HTML模板
│   ├── crs_report.html
│   └── ...
├── static/           # 静态资源
├── main.py          # FastAPI主应用
└── ...
```

## 如何添加新页面

### 1. 创建页面类

在 `pages/` 目录下创建新的页面类，例如 `sales_page.py`：

```python
"""
销售数据页面
"""
from typing import Dict, Any, List
from pages.base import BasePage


class SalesPage(BasePage):
    """销售数据页面"""
    
    def __init__(self):
        super().__init__(
            page_id="sales",           # 页面唯一ID
            title="销售数据统计",       # 页面标题
            template="sales_report.html"  # 模板文件名
        )
    
    def get_data(self) -> List[Dict[str, Any]]:
        """获取销售数据"""
        # 这里实现你的数据获取逻辑
        # 可以从数据库查询、API调用等
        return [
            {"region": "北京", "sales": 1000},
            {"region": "上海", "sales": 2000},
        ]
```

### 2. 注册页面

在 `pages/registry.py` 的 `init_pages()` 函数中注册新页面：

```python
def init_pages():
    """初始化并注册所有页面"""
    PageRegistry.register(CRSPage())
    PageRegistry.register(SalesPage())  # 添加这一行
```

### 3. 创建HTML模板

在 `templates/` 目录下创建对应的HTML模板文件 `sales_report.html`：

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <title>{{ title }}</title>
    <link rel="stylesheet" href="/static/style.css" />
  </head>
  <body>
    <!-- 你的页面HTML结构 -->
    <h1>{{ title }}</h1>
    <p>截止时间：{{ cutoff_time }}</p>
    
    <table>
      {% for row in rows %}
      <tr>
        <td>{{ row.region }}</td>
        <td>{{ row.sales }}</td>
      </tr>
      {% endfor %}
    </table>
  </body>
</html>
```

### 4. 访问新页面

完成以上步骤后，可以通过以下方式访问：

**Web 访问：**
- `http://localhost:8000/sales`

**API 查看所有页面：**
- `http://localhost:8000/api/pages`

## 页面基类说明

`BasePage` 提供了以下方法：

- `get_data()`: **必须实现**，返回页面数据
- `get_context()`: 获取模板上下文（包含title、rows、cutoff_time等）

## 自定义配置

如果需要自定义某些行为，可以在页面类中重写基类方法：

```python
class CustomPage(BasePage):
    def get_context(self) -> Dict[str, Any]:
        """自定义模板上下文"""
        context = super().get_context()
        # 添加额外的数据
        context["extra_data"] = "something"
        return context
```

## 示例：完整的新页面

参考 `pages/crs_page.py` 获取完整示例。

## 启动服务

```bash
# 启动Web服务
python main.py

# 访问页面
# http://localhost:8000/      # 默认CRS页面
# http://localhost:8000/crs   # CRS页面
# http://localhost:8000/api/pages  # 查看所有页面
```

