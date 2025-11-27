import os

# 通过环境变量切换环境，默认为 DEV 本地开发
ENV = os.environ.get("environment", "DEV")  # "PROD" or "DEV"


if ENV == "DEV":
    # 本地开发数据库
    MYSQL_HOST = "127.0.0.1"
    MYSQL_PORT = 3306
    MYSQL_DATABASE = "demo"
    MYSQL_USER = "root"
    MYSQL_PASSWORD = "Python3.8"
    # ChromeDriver 路径（本地开发环境）
    CHROMEDRIVER_PATH = None  # None 表示使用系统默认或 webdriver-manager
else:
    # 线上数据库
    MYSQL_HOST = "mysql0200.3337-wm.db.idc"
    MYSQL_PORT = 3337
    MYSQL_DATABASE = "process_analysis"
    MYSQL_USER = "process_analysis"
    MYSQL_PASSWORD = "ns7ubvy96ncHncOTOeHS"
    # ChromeDriver 路径（线上环境）
    CHROMEDRIVER_PATH = '/data1/users/zhaoxu/HTML2IMAGE/bin/chromedriver'
