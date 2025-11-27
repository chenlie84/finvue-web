from pathlib import Path
from typing import Optional
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

import config


def capture(
    url: str = "http://127.0.0.1:8000/",
    output_path: str = "output/crs_screenshot.png",
    window_width: int = 1100,
    window_height: int = 768,
    chromedriver_path: Optional[str] = None,
) -> str:
    """
    使用 Selenium 截图指定 URL，并保存为图片。

    参数:
        url: 要截图的页面地址，本地 FastAPI 默认为 http://127.0.0.1:8000/
        output_path: 输出图片路径
        window_width: 浏览器窗口宽度（默认适配当前页面宽度）
        window_height: 浏览器窗口高度
        chromedriver_path: ChromeDriver 路径，如果为 None 则使用 config 中的配置
    """
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 如果没有传入路径，使用配置文件中的路径
    if chromedriver_path is None:
        chromedriver_path = config.CHROMEDRIVER_PATH

    # 配置 ChromeDriver 启动选项
    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--remote-debugging-port=9222')
    
    # 提高截图质量的设置
    options.add_argument('--force-device-scale-factor=2')  # 2倍分辨率
    options.add_argument('--high-dpi-support=2')  # 高DPI支持
    options.add_argument('--disable-font-subpixel-positioning')  # 改善字体渲染
    
    driver = None
    try:
        print(f"正在启动Chrome浏览器...")
        
        # 启动 ChromeDriver
        if chromedriver_path:
            print(f"使用 ChromeDriver: {chromedriver_path}")
            driver = webdriver.Chrome(executable_path=chromedriver_path, options=options)
        else:
            print("使用系统默认 ChromeDriver")
            driver = webdriver.Chrome(options=options)
        
        print(f"正在访问 {url}")
        driver.get(url)
        
        # 等待网页加载完成
        print("等待页面加载...")
        time.sleep(3)
        
        # 设置窗口大小（因为 scale-factor=2，所以需要2倍尺寸）
        driver.set_window_size(window_width * 2, window_height * 2)
        
        # 执行JavaScript来确保高质量渲染
        driver.execute_script("document.body.style.zoom='100%'")
        
        # 再等待一下确保渲染完成
        time.sleep(1)
        
        print(f"正在保存截图到 {output_file}")
        driver.save_screenshot(str(output_file))
        print("截图完成")
        
    except Exception as e:
        print(f"\n截图失败: {e}")
        raise
    finally:
        if driver:
            driver.quit()

    return str(output_file)


if __name__ == "__main__":
    path = capture()
    print(f"Screenshot saved to: {path}")
