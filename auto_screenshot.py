#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自动化截图脚本
功能：启动 Web 服务 -> 截图 -> 关闭服务
"""

import subprocess
import time
import signal
import sys
from pathlib import Path

from capture_screenshot import capture


def auto_screenshot(
    url: str = "http://127.0.0.1:8000/",
    output_path: str = "output/crs_screenshot.png",
    window_width: int = 1100,
    window_height: int = 768,
    wait_time: int = 5,
):
    """
    自动启动服务、截图并关闭服务
    
    参数:
        url: 访问的 URL
        output_path: 截图保存路径
        window_width: 浏览器窗口宽度
        window_height: 浏览器窗口高度
        wait_time: 等待服务启动的时间（秒）
    """
    server_process = None
    
    try:
        # 1. 启动 Web 服务
        print("=" * 60)
        print("正在启动 Web 服务...")
        print("=" * 60)
        
        # 使用 subprocess 启动服务
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).parent)
        )
        
        # 等待服务启动
        print(f"等待 {wait_time} 秒让服务完全启动...")
        time.sleep(wait_time)
        
        # 2. 截图
        print("\n" + "=" * 60)
        print("正在截取网页...")
        print("=" * 60)
        
        screenshot_path = capture(
            url=url,
            output_path=output_path,
            window_width=window_width,
            window_height=window_height,
        )
        
        print(f"\n✅ 截图成功！")
        print(f"📸 截图已保存到: {screenshot_path}")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        return False
        
    finally:
        # 3. 关闭 Web 服务
        if server_process:
            print("\n" + "=" * 60)
            print("正在关闭 Web 服务...")
            print("=" * 60)
            
            server_process.send_signal(signal.SIGTERM)
            server_process.wait(timeout=5)
            print("✅ Web 服务已关闭")
        
        print("\n" + "=" * 60)
        print("✅ 全部完成！")
        print("=" * 60)
    
    return True


if __name__ == "__main__":
    # 运行自动化截图
    success = auto_screenshot()
    sys.exit(0 if success else 1)
