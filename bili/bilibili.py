import os
import re
import time
import subprocess
import tempfile
import json
import requests
from urllib.parse import quote
from DrissionPage import ChromiumPage
from dotenv import load_dotenv

# ================== 用户配置区 ==================
SEARCH_KEYWORDS = ["鲁迅故里"]
SCROLL_TIMES = 2
MAX_DOWNLOAD = 5
MAX_PAGES = 3  # 每个关键词最多翻几页
# ================== 请求头 ==================
load_dotenv("key.env")
co=os.getenv("cookie")
FFMPEG_PATH = os.getenv("FFMPEG_PATH") or None
headers = {
    "cookie":co,
    "referer": "https://www.bilibili.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
}
# ================================================

os.makedirs("bilibili_videos", exist_ok=True)
PROCESSED_FILE = "bilibili_processed_bvids.txt"
METADATA_FILE = "raw_data.json"
COMMENT_DATA_FILE = "comment_data.json"

def load_processed():
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f)
    return set()

def save_processed(bvid):
    with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
        f.write(f"{bvid}\n")

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

def get_video_info(bvid):
    """从BV号获取视频详细信息(aid、发布时间、统计数据等)"""
    try:
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            video_data = data["data"]
            return {
                "aid": video_data["aid"],
                "pubdate": video_data.get("pubdate"),  # 发布时间戳
                "pubdate_str": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(video_data.get("pubdate", 0))),
                "stats": {
                    "view": video_data.get("stat", {}).get("view", 0),  # 播放量
                    "like": video_data.get("stat", {}).get("like", 0),  # 点赞数
                    "coin": video_data.get("stat", {}).get("coin", 0),  # 投币数
                    "favorite": video_data.get("stat", {}).get("favorite", 0),  # 收藏数
                    "share": video_data.get("stat", {}).get("share", 0)  # 分享数
                }
            }
    except Exception:
        pass
    return None

def fetch_comments(bvid, min_likes=10):
    """获取视频评论,只保留点赞数>=min_likes的评论,返回(评论列表, 评论统计)"""
    video_info = get_video_info(bvid)
    if not video_info:
        return [], {}

    aid = video_info["aid"]
    comments = []
    try:
        url = f"https://api.bilibili.com/x/v2/reply/main?type=1&oid={aid}&mode=3&plat=1"
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()

        if data.get("code") == 0 and data.get("data"):
            replies = data["data"].get("replies", [])
            total_likes = 0
            for reply in replies:
                likes = reply.get("like", 0)
                if likes >= min_likes:
                    comments.append({
                        "用户": reply["member"]["uname"],
                        "内容": reply["content"]["message"],
                        "点赞数": likes,
                        "时间": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(reply["ctime"]))
                    })
                    total_likes += likes

            # 返回评论统计信息
            comment_stats = {
                "count": len(comments),
                "total_likes": total_likes,
                "avg_likes": round(total_likes / len(comments), 2) if comments else 0
            }
            return comments, comment_stats
    except Exception:
        pass

    return [], {}

def create_cookie_file(cookie_str):
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
    tmp.write("# Netscape HTTP Cookie File\n")
    for cookie_pair in cookie_str.split(';'):
        cookie_pair = cookie_pair.strip()
        if not cookie_pair or '=' not in cookie_pair:
            continue
        name, value = cookie_pair.split('=', 1)
        tmp.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")
    tmp.close()
    return tmp.name

def download_video(bvid, clean_title, cookie_file):
    """尝试下载视频，成功返回 True，失败返回 False（不输出任何信息）"""
    base_cmd = [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", f"bilibili_videos/{clean_title}_{bvid}.%(ext)s",
        f"https://www.bilibili.com/video/{bvid}"
    ]
    if FFMPEG_PATH:
        base_cmd.insert(1, f"--ffmpeg-location={FFMPEG_PATH}")
    if cookie_file:
        base_cmd.insert(1, f"--cookies={cookie_file}")
    base_cmd.insert(1, f"--referer={headers.get('referer', 'https://www.bilibili.com/')}")
    base_cmd.insert(1, f"--user-agent={headers.get('user-agent', '')}")

    try:
        result = subprocess.run(base_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=300)
        return result.returncode == 0
    except Exception:
        return False

cookie_file = None
if headers.get("cookie") and headers["cookie"] != "你的B站cookie":
    cookie_file = create_cookie_file(headers["cookie"])
    print("已加载 Cookie 信息")
else:
    print("警告：未填写有效 cookie")

page = ChromiumPage()
processed = load_processed()
metadata_list = load_metadata()
comment_data_list = load_comment_data()
download_count = 0
print(f"已处理 {len(processed)} 个，本次最多下载 {MAX_DOWNLOAD} 个\n")

for keyword in SEARCH_KEYWORDS:
    print(f"\n开始搜索: {keyword}")

    page_num = 0
    while download_count < MAX_DOWNLOAD:
        page_num += 1

        print(f"\n第 {page_num} 页")
        page.get(f"https://search.bilibili.com/all?keyword={quote(keyword)}&page={page_num}")
        time.sleep(3)

        for i in range(SCROLL_TIMES):
            page.scroll.to_bottom()
            print(f"滚动加载... ({i+1}/{SCROLL_TIMES})")
            time.sleep(2)

        video_cards = page.eles('css:.bili-video-card', timeout=5)
        if not video_cards:
            video_cards = page.eles('css:.video-item', timeout=5)

        # 如果没有找到视频卡片
        if not video_cards:
            if page_num == 1:
                # 第一页加载失败(浏览器问题),直接跳到第二页
                print(f"第一页加载失败,跳到第二页继续")
                continue
            else:
                # 第2页之后没有视频,说明已到最后一页
                print(f"已到达最后一页,共 {page_num - 1} 页")
                break

        print(f"找到 {len(video_cards)} 个视频卡片")

        for idx, card in enumerate(video_cards, 1):
            if download_count >= MAX_DOWNLOAD:
                break
            try:
                link_elem = card.ele('css:a', timeout=0.5)
                if not link_elem:
                    title_elem = card.ele('css:.bili-video-card__info--tit', timeout=0.5)
                    if title_elem:
                        link_elem = title_elem
                if not link_elem or not link_elem.link:
                    continue   # 静默跳过

                link = link_elem.link
                bvid_match = re.search(r'BV\w+', link)
                if not bvid_match:
                    continue
                bvid = bvid_match.group(0)
                if bvid in processed:
                    continue

                title_elem = card.ele('css:.bili-video-card__info--tit', timeout=0.5)
                title = title_elem.text.strip() if title_elem else bvid
                clean_title = re.sub(r'[\\/*?:"<>|]', '', title).strip()[:50]
                if not clean_title:
                    clean_title = bvid


                print(f"\n发现视频: {clean_title} (BV号: {bvid})")
                if download_video(bvid, clean_title, cookie_file):
                    print(f"  ✅ 下载完成")

                    # 视频文件路径
                    video_file = f"bilibili_videos/{clean_title}_{bvid}.mp4"

                    # 获取视频完整信息
                    video_info = get_video_info(bvid)

                    # 获取评论和评论统计
                    comments, comment_stats = fetch_comments(bvid, min_likes=5)

                    # 将评论添加到独立的评论数据列表
                    for idx, comment in enumerate(comments, 1):
                        comment_data_list.append({
                            "id": f"{bvid}_comment_{idx:03d}",
                            "video_id": f"bili_{bvid}",
                            "video_title": title,
                            "video_file_path": video_file,
                            "video_url": f"https://www.bilibili.com/video/{bvid}",
                            "source": "B站",
                            "user": comment["用户"],
                            "content": comment["内容"],
                            "likes": comment["点赞数"],
                            "time": comment["时间"],
                            "tags": {}
                        })

                    if comments:
                        print(f"  💬 获取到 {len(comments)} 条高赞评论（≥10赞）")
                    else:
                        print(f"  💬 未找到符合条件的评论")

                    save_processed(bvid)
                    processed.add(bvid)

                    # 添加元数据记录
                    metadata_entry = {
                        "id": f"bili_{bvid}",
                        "type": "video",
                        "title": title,
                        "source": "B站",
                        "file_path": video_file,
                        "url": f"https://www.bilibili.com/video/{bvid}",
                        "tags": {}
                    }

                    # 添加视频信息(发布时间、统计数据)
                    if video_info:
                        metadata_entry["pubdate"] = video_info.get("pubdate_str")
                        metadata_entry["video_stats"] = video_info.get("stats", {})

                    # 添加评论统计
                    if comment_stats:
                        metadata_entry["comment_stats"] = comment_stats

                    metadata_list.append(metadata_entry)

                    # 立即保存数据(增量保存)
                    save_metadata(metadata_list)
                    save_comment_data(comment_data_list)

                    download_count += 1
                # 下载失败时不做任何输出，直接跳过
            except Exception:
                continue   # 任何异常都静默跳过

print(f"\n✅ 完成！共下载 {download_count} 个视频，保存在 bilibili_videos 文件夹")

# 保存元数据到JSON文件
save_metadata(metadata_list)
print(f"📝 元数据已保存到 {METADATA_FILE}")

# 保存评论数据到JSON文件
save_comment_data(comment_data_list)
print(f"💬 评论数据已保存到 {COMMENT_DATA_FILE}")

page.close()
if cookie_file and os.path.exists(cookie_file):
    os.unlink(cookie_file)