"""
小红书Cookie自动获取工具
运行此脚本，在打开的浏览器中登录小红书，脚本会自动提取Cookie并保存
"""

import os
import time
from DrissionPage import ChromiumPage, ChromiumOptions


def find_chrome_path():
    """自动查找Google Chrome浏览器路径"""
    common_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe"),
    ]

    for path in common_paths:
        if os.path.exists(path):
            return path
    return None


if __name__ == "__main__":
    print("="*60)
    print("小红书Cookie自动获取工具")
    print("="*60)

    chrome_path = find_chrome_path()
    co = ChromiumOptions()
    if chrome_path:
        co.set_browser_path(chrome_path)

    print("\n🚀 正在启动浏览器...")
    page = ChromiumPage(addr_or_opts=co)

    print("📱 正在打开小红书...")
    page.get("https://www.xiaohongshu.com")

    print("\n" + "="*60)
    print("⚠️  请在浏览器中登录小红书（扫码或账号密码）")
    print("⚠️  登录成功后，按回车键继续...")
    print("="*60)
    input()

    # 提取Cookie
    cookies = page.cookies(all_domains=True)
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies if 'xiaohongshu.com' in c.get('domain', '')])

    if cookie_str:
        with open("key.env", "w", encoding="utf-8") as f:
            f.write(f"xhs_cookie={cookie_str}\n")

        print("\n✅ Cookie已保存到 key.env 文件")
        print(f"📝 Cookie长度: {len(cookie_str)} 字符")
    else:
        print("\n❌ 未获取到Cookie，请确认已登录")

    page.quit()
    print("\n✅ 完成！现在可以运行 xiaohongshu_scraper.py 了")
