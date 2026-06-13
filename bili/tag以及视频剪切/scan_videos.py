"""
视频时长检测工具
"""
import subprocess
import json
from pathlib import Path

def get_video_duration(video_path):
    """获取视频时长（秒）"""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(video_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    duration = float(data["format"]["duration"])
    return duration

def scan_videos(folder_path, min_duration=300):
    """扫描文件夹，找出长度>min_duration秒的视频"""
    folder = Path(folder_path)
    video_extensions = [".mp4", ".avi", ".mkv", ".mov", ".flv"]

    long_videos = []

    for video_file in folder.glob("*"):
        if video_file.suffix.lower() in video_extensions:
            try:
                duration = get_video_duration(video_file)
                minutes = duration / 60

                if duration > min_duration:
                    long_videos.append({
                        "path": str(video_file),
                        "name": video_file.name,
                        "duration_seconds": duration,
                        "duration_minutes": minutes
                    })
                    print(f"✓ {video_file.name}: {minutes:.1f}分钟")
                else:
                    print(f"- {video_file.name}: {minutes:.1f}分钟 (跳过)")
            except Exception as e:
                print(f"✗ {video_file.name}: 无法读取时长")

    return long_videos

if __name__ == "__main__":
    videos = scan_videos("bilibili_videos", min_duration=300)
    print(f"\n找到 {len(videos)} 个长度>5分钟的视频")

    with open("long_videos.json", "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
