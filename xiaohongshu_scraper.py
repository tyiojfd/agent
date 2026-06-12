import os
import re
import time
import json
import random
import requests
from pathlib import Path
from urllib.parse import quote
from DrissionPage import ChromiumPage, ChromiumOptions
from dotenv import load_dotenv


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


def first_time_login():
    """首次运行登录流程"""
    print("\n" + "="*60)
    print("🎉 欢迎使用小红书笔记爬虫")
    print("="*60)
    print("\n检测到首次运行，需要先登录小红书获取Cookie\n")

    chrome_path = find_chrome_path()
    co = ChromiumOptions()
    if chrome_path:
        co.set_browser_path(chrome_path)

    print("🚀 正在启动浏览器...")
    page = ChromiumPage(addr_or_opts=co)
    page.get("https://www.xiaohongshu.com")

    print("\n" + "="*60)
    print("⚠️  请在浏览器中登录小红书（扫码或账号密码）")
    print("⚠️  登录成功后，按回车键继续...")
    print("="*60)
    input()

    cookies = page.cookies(all_domains=True)
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies if 'xiaohongshu.com' in c.get('domain', '')])

    if cookie_str:
        with open("key.env", "w", encoding="utf-8") as f:
            f.write(f"xhs_cookie={cookie_str}\n")
        print("\n✅ Cookie已保存")
        page.quit()
        return True
    else:
        print("\n❌ 未获取到Cookie，请确认已登录")
        page.quit()
        return False

# ================== 用户配置区 ==================
SEARCH_KEYWORDS = ["鲁迅故里"]
SCROLL_TIMES = 3
MAX_DOWNLOAD = 10  # 最多采集多少个笔记
MAX_PAGES = 2  # 每个关键词最多翻几页
# ================================================

# ================== 请求头配置 ==================
load_dotenv("key.env")
cookie = os.getenv("xhs_cookie", "")
headers = {
    "cookie": cookie,
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "referer": "https://www.xiaohongshu.com/"
}
# ================================================

os.makedirs("xiaohongshu_data", exist_ok=True)
PROCESSED_FILE = "xiaohongshu_processed_ids.txt"
METADATA_FILE = "xiaohongshu_metadata.json"
COMMENT_DATA_FILE = "xiaohongshu_comments.json"


def load_processed():
    """加载已处理的笔记ID"""
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    return set()


def save_processed(note_id):
    """保存已处理的笔记ID"""
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(f"{note_id}\n")


def load_metadata():
    """加载已有的元数据"""
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_metadata(metadata_list):
    """保存元数据到JSON文件"""
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(metadata_list, f, ensure_ascii=False, indent=2)


def load_comment_data():
    """加载已有的评论数据"""
    if os.path.exists(COMMENT_DATA_FILE):
        with open(COMMENT_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_comment_data(comment_list):
    """保存评论数据到JSON文件"""
    with open(COMMENT_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(comment_list, f, ensure_ascii=False, indent=2)


def get_note_detail(note_id, browser_page):
    """通过笔记ID获取详细信息（使用浏览器）"""
    try:
        url = f"https://www.xiaohongshu.com/explore/{note_id}"

        # 使用浏览器访问（避免反爬）
        browser_page.get(url)
        time.sleep(2)  # 等待页面加载

        html = browser_page.html

        # 从HTML提取标题
        title_match = re.search(r'<meta name="og:title" content="(.*?)"', html)
        if not title_match:
            # 尝试其他标题提取方式
            title_match = re.search(r'<title>(.*?)</title>', html)

        title = title_match.group(1) if title_match else note_id
        title = title.replace(' - 小红书', '').strip()

        # 从HTML提取图片URL列表
        img_urls = re.findall(r'<meta name="og:image" content="(.*?)"', html)

        # 如果没找到og:image，尝试其他方式
        if not img_urls:
            img_urls = re.findall(r'"url":"(https://[^"]*?\.(?:jpg|jpeg|png|webp)[^"]*?)"', html)
            # 清理转义字符
            img_urls = [url.replace('\\/', '/') for url in img_urls]

        return {
            "title": title,
            "images": img_urls[:10],  # 最多取10张图
            "url": url
        }
    except Exception as e:
        print(f"  ⚠️  获取笔记详情失败: {e}")
        return None


def download_images(note_id, title, img_urls):
    """下载笔记的所有图片到独立文件夹"""
    clean_title = re.sub(r'[\\/:*?"<>|]', '_', title).strip()[:30]
    note_folder = os.path.join("xiaohongshu_data", f"{clean_title}_{note_id}")
    img_folder = os.path.join(note_folder, "images")
    os.makedirs(img_folder, exist_ok=True)

    saved_paths = []
    for idx, img_url in enumerate(img_urls, 1):
        try:
            img_resp = requests.get(img_url, headers=headers, timeout=10)
            if img_resp.status_code == 200:
                filename = f"{idx}.jpg"
                filepath = os.path.join(img_folder, filename)

                with open(filepath, "wb") as f:
                    f.write(img_resp.content)

                saved_paths.append(filepath)
                time.sleep(0.5)
        except Exception:
            print(f"  ⚠️  图片{idx}下载失败")

    return note_folder, saved_paths


def save_note_content(note_folder, title, content):
    """保存笔记文案到txt文件"""
    content_file = os.path.join(note_folder, "content.txt")
    with open(content_file, "w", encoding="utf-8") as f:
        f.write(f"标题: {title}\n\n")
        f.write(f"内容:\n{content}\n")


def save_note_metadata(note_folder, metadata):
    """保存笔记元数据到JSON文件"""
    metadata_file = os.path.join(note_folder, "metadata.json")
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def save_note_comments(note_folder, comments_data):
    """保存笔记评论到JSON文件"""
    comments_file = os.path.join(note_folder, "comments.json")
    with open(comments_file, "w", encoding="utf-8") as f:
        json.dump(comments_data, f, ensure_ascii=False, indent=2)


def fetch_comments(note_id, browser_page, min_likes=0):
    """从页面HTML中提取评论"""
    comments = []
    comment_stats = {"count": 0, "total_likes": 0}

    try:
        url = f"https://www.xiaohongshu.com/explore/{note_id}"
        browser_page.get(url)
        time.sleep(3)

        html = browser_page.html

        # 检测是否被风控
        if "请打开小红书App扫码查看" in html or "验证" in browser_page.title:
            return comments, comment_stats  # 静默跳过，不打印错误

        browser_page.scroll.to_bottom()
        time.sleep(2)

        # 从HTML提取评论JSON
        import re
        comment_pattern = r'"comments":\s*(\[.*?\]).*?"has_more"'
        matches = re.findall(comment_pattern, html, re.DOTALL)

        if matches:
            try:
                comments_data = json.loads(matches[0])

                for comment in comments_data:
                    likes = comment.get("like_count", 0)
                    if likes >= min_likes:
                        comments.append({
                            "用户": comment.get("user_info", {}).get("nickname", "未知"),
                            "内容": comment.get("content", ""),
                            "点赞数": likes,
                            "时间": comment.get("create_time", "")
                        })

                comment_stats = {
                    "count": len(comments),
                    "total_likes": sum(c["点赞数"] for c in comments)
                }
            except:
                pass

    except:
        pass

    return comments, comment_stats


# ================== 主程序 ==================
if __name__ == "__main__":
    # 检查是否首次运行
    if not os.path.exists("key.env"):
        print("\n检测到首次运行...")
        if not first_time_login():
            print("\n❌ 登录失败，程序退出")
            exit(1)
        print("\n✅ 配置完成，开始爬取...\n")
        # 重新加载环境变量
        load_dotenv("key.env")
        cookie = os.getenv("xhs_cookie", "")
        headers["cookie"] = cookie
    elif not os.getenv("xhs_cookie"):
        print("⚠️  警告：key.env存在但Cookie为空")
        print("请运行 python get_cookie.py 重新获取Cookie")
        exit(1)

    # 自动查找Chrome路径
    chrome_path = find_chrome_path()
    co = ChromiumOptions()

    if chrome_path:
        print(f"✅ 找到Chrome: {chrome_path}")
        co.set_browser_path(chrome_path)

    # 使用独立的自动化配置文件（避免与日常Chrome冲突）
    # 首次运行需要手动登录小红书，之后会保存登录状态
    automation_profile = os.path.join(os.getcwd(), "chrome_automation_profile")
    co.set_user_data_path(automation_profile)
    print(f"📁 使用独立配置: {automation_profile}")

    # 优化参数
    co.set_argument('--no-first-run')
    co.set_argument('--no-default-browser-check')
    co.set_argument('--disable-popup-blocking')

    print("🚀 正在启动浏览器...")
    page = ChromiumPage(addr_or_opts=co)
    print("✅ 浏览器已启动")
    processed = load_processed()
    metadata_list = load_metadata()
    comment_data_list = load_comment_data()
    download_count = 0

    print(f"已处理 {len(processed)} 个笔记，本次最多采集 {MAX_DOWNLOAD} 个\n")

    for keyword in SEARCH_KEYWORDS:
        print(f"\n{'='*50}")
        print(f"开始搜索关键词: {keyword}")
        print(f"{'='*50}")

        page_num = 0
        while download_count < MAX_DOWNLOAD and page_num < MAX_PAGES:
            page_num += 1
            print(f"\n📄 第 {page_num} 页")

            # 启动网络监听（监听搜索API）
            page.listen.start('api/sns/web/v1/search/notes')

            # 访问搜索页面
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={quote(keyword)}&source=web_explore_feed"
            page.get(search_url)
            time.sleep(3)

            # 等待并获取API响应
            try:
                resp = page.listen.wait(timeout=10)
                json_data = resp.response.body

                if not json_data or not isinstance(json_data, dict):
                    print("  ⚠️  未获取到有效数据")
                    continue

                items = json_data.get('data', {}).get('items', [])
                if not items:
                    print("  未找到笔记")
                    break

                print(f"  找到 {len(items)} 个笔记")

                for idx, item in enumerate(items, 1):
                    if download_count >= MAX_DOWNLOAD:
                        break

                    try:
                        # 从API数据中提取信息
                        note_id = item.get('id', '')
                        if not note_id:
                            continue

                        # 跳过已处理的笔记
                        if note_id in processed:
                            continue

                        # 提取笔记信息
                        note_card = item.get('note_card', {})
                        title = note_card.get('display_title', note_id)
                        content = note_card.get('desc', '')  # 笔记文案内容
                        cover_url = note_card.get('cover', {}).get('url_default', '')

                        # 提取图片列表
                        image_list = note_card.get('image_list', [])

                        # 正确提取图片URL（从info_list中获取）
                        img_urls = []
                        for img in image_list:
                            info_list = img.get('info_list', [])
                            # 优先使用 WB_DFT（默认/高质量版本）
                            for info in info_list:
                                if info.get('image_scene') == 'WB_DFT' and info.get('url'):
                                    img_urls.append(info['url'])
                                    break

                        # 调试：输出API返回的图片数量
                        print(f"\n🔍 发现笔记: {note_id}")
                        print(f"  📝 标题: {title[:40]}...")
                        print(f"  [调试] API返回的image_list长度: {len(image_list)}")
                        print(f"  [调试] 提取到的图片URL数量: {len(img_urls)}")

                        # 如果没有image_list，使用封面图
                        if not img_urls and cover_url:
                            img_urls = [cover_url]
                            print(f"  [调试] 使用封面图代替")

                        print(f"  🖼️  最终图片数量: {len(img_urls)}")

                        # 下载图片到独立文件夹
                        if img_urls:
                            note_folder, saved_paths = download_images(note_id, title, img_urls)
                            print(f"  ✅ 下载了 {len(saved_paths)} 张图片")
                        else:
                            clean_title = re.sub(r'[\\/:*?"<>|]', '_', title).strip()[:30]
                            note_folder = os.path.join("xiaohongshu_data", f"{clean_title}_{note_id}")
                            os.makedirs(note_folder, exist_ok=True)
                            saved_paths = []
                            print(f"  ⚠️  无图片可下载")

                        # 保存文案内容
                        save_note_content(note_folder, title, content)

                        # 构建元数据
                        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
                        note_metadata = {
                            "id": note_id,
                            "type": "note",
                            "title": title,
                            "content": content,
                            "source": "小红书",
                            "url": note_url,
                            "folder": note_folder,
                            "images": saved_paths,
                            "image_count": len(saved_paths),
                            "likes": note_card.get('interact_info', {}).get('liked_count', 0),
                            "collects": note_card.get('interact_info', {}).get('collected_count', 0),
                            "comments": note_card.get('interact_info', {}).get('comment_count', 0),
                            "author": note_card.get('user', {}).get('nickname', '未知'),
                            "author_id": note_card.get('user', {}).get('user_id', '')
                        }

                        # 保存笔记独立的metadata.json
                        save_note_metadata(note_folder, note_metadata)
                        print(f"  💾 已保存到文件夹: {note_folder}")

                        # 抓取并保存评论
                        comments, comment_stats = fetch_comments(note_id, page)
                        if comments:
                            save_note_comments(note_folder, {
                                "note_id": note_id,
                                "comments": comments,
                                "stats": comment_stats
                            })
                            print(f"  💬 抓取了 {comment_stats['count']} 条评论")
                        else:
                            print(f"  💬 暂无评论")

                        # 同时添加到总的元数据列表
                        metadata_list.append(note_metadata)

                        # 标记为已处理
                        save_processed(note_id)
                        processed.add(note_id)

                        # 增量保存
                        save_metadata(metadata_list)

                        download_count += 1
                        time.sleep(0.5)

                    except Exception as e:
                        if idx <= 3:
                            print(f"  [调试] 处理笔记{idx}时出错: {e}")
                        continue

            except Exception as e:
                print(f"  ⚠️  获取API数据失败: {e}")
                continue

            finally:
                try:
                    page.listen.stop()
                except:
                    pass

            # 翻页需要重新访问
            time.sleep(2)

    print(f"\n{'='*50}")
    print(f"✅ 完成！共采集 {download_count} 个笔记")
    print(f"📁 数据保存在 xiaohongshu_data 文件夹")
    print(f"📝 元数据: {METADATA_FILE}")
    print(f"💬 评论数据: {COMMENT_DATA_FILE}")
    print(f"{'='*50}")

    page.quit()

    print("\n⚠️  重要提示：")
    print("1. 本程序仅用于学习研究目的")
    print("2. 请遵守小红书服务条款，控制采集频率")
    print("3. 尊重内容创作者版权")
    print("4. 不要用于商业用途或大规模数据采集")
