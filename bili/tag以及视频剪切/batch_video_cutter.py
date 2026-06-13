"""
批量视频智能切割工具 - 自动更新JSON数据
"""
import whisper
import json
import subprocess
import time
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv("key.env")

class BatchVideoCutter:
    def __init__(self, api_key=None, json_file="raw_data.json", processed_file="processed_videos.txt"):
        print("初始化Whisper模型...")
        self.whisper_model = whisper.load_model("base")
        self.model_id = os.getenv("MODEL_ID", "glm-5")
        self.client = OpenAI(
            api_key=api_key or os.getenv("API_KEY"),
            base_url=os.getenv("BASE_URL")
        ) if api_key or os.getenv("API_KEY") else None
        self.last_request_time = 0
        self.min_interval = 60  # 60秒间隔，避免QPM限流
        self.json_file = json_file
        self.json_data = self._load_json()
        self.processed_file = processed_file
        self.processed_ids = self._load_processed_ids()

    def _load_json(self):
        """加载JSON数据"""
        with open(self.json_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self):
        """保存JSON数据"""
        with open(self.json_file, "w", encoding="utf-8") as f:
            json.dump(self.json_data, f, ensure_ascii=False, indent=2)

    def _load_processed_ids(self):
        """加载已处理视频ID列表"""
        if Path(self.processed_file).exists():
            with open(self.processed_file, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

    def _save_processed_id(self, video_id):
        """保存已处理视频ID"""
        self.processed_ids.add(video_id)
        with open(self.processed_file, "a", encoding="utf-8") as f:
            f.write(f"{video_id}\n")

    def _get_video_id(self, video_path):
        """根据文件路径获取视频ID"""
        video_path = str(Path(video_path).as_posix())
        for item in self.json_data:
            if item.get("file_path") == video_path:
                return item.get("id")
        return None

    def _update_json_for_video(self, video_path, segments_info, tags):
        """更新JSON中的视频记录"""
        video_path = str(Path(video_path).as_posix())

        for item in self.json_data:
            if item.get("file_path") == video_path:
                item["isSplit"] = True
                item["segments"] = segments_info
                item["tags"] = tags
                break

        self._save_json()

    def _update_json_tags_only(self, video_path, tags):
        """仅更新视频的标签（不切割的短视频）"""
        video_path = str(Path(video_path).as_posix())

        for item in self.json_data:
            if item.get("file_path") == video_path:
                item["tags"] = tags
                item["isTagged"] = True
                break

        self._save_json()

    def _is_video_processed(self, video_path):
        """检查视频是否已处理（长视频看isSplit，短视频看isTagged）"""
        video_path = str(Path(video_path).as_posix())
        for item in self.json_data:
            if item.get("file_path") == video_path:
                return item.get("isSplit", False) or item.get("isTagged", False)
        return False

    def get_video_duration(self, video_path):
        """获取视频时长"""
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(json.loads(result.stdout)["format"]["duration"])

    def has_audio_stream(self, video_path):
        """检查视频是否有音频流"""
        cmd = ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(video_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        return any(s.get("codec_type") == "audio" for s in data.get("streams", []))

    def scan_long_videos(self, folder, min_duration=300):
        """扫描长视频"""
        videos = []
        for f in Path(folder).glob("*.mp4"):
            duration = self.get_video_duration(f)
            if duration > min_duration:
                if self.has_audio_stream(f):
                    videos.append({"path": str(f), "name": f.name, "duration": duration})
                    print(f"[OK] {f.name}: {duration/60:.1f}分钟")
                else:
                    print(f"[SKIP] {f.name}: {duration/60:.1f}分钟 (无音频流)")
        return videos

    def transcribe_video(self, video_path):
        """语音识别"""
        print(f"\n[1/3] 语音识别: {Path(video_path).name}")
        result = self.whisper_model.transcribe(str(video_path), language="zh", verbose=False)
        return result["segments"]

    def analyze_with_glm(self, segments, tag_dimensions):
        """GLM-5一次性分析整个视频内容并生成标签"""
        print("[2/3] AI分析内容...")

        if not self.client:
            print("  未配置API，使用关键词规则")
            return self._keyword_analysis(segments)

        # 组织完整的转录文本
        full_text = "\n".join([f"[{s['start']:.1f}s] {s['text']}" for s in segments[:200]])  # 限制长度避免超token

        prompt = f"""分析这段视频的完整讲解内容，识别不同的主题段落并确定切分点，同时为每个片段生成标签。

要求：
1. 根据内容主题变化确定切分点（不是按时间机械切分）
2. 每个切分点包含：时间(秒)、主题标题(4-8字)、内容概括(20-40字)
3. 第一段从0秒开始
4. 判断内容是否与绍兴相关（满足以下任一条件则为true，否则为false）：
   - 地点：提到绍兴、鲁迅故里、百草园、三味书屋、鲁迅故居、沈园、东湖等绍兴景点
   - 人物：提到鲁迅、周作人、寿镜吾先生、闰土、长妈妈等绍兴相关人物
   - 美食：提到绍兴黄酒、臭豆腐、茴香豆、霉干菜、醉鸡等绍兴特色美食
   - 文化：提到绍兴方言、社戏、乌篷船等绍兴文化特色
5. 为每个片段生成标签（3个维度）：
   - 主题：从{tag_dimensions['主题']}中选择1-2个最符合的
   - 地点：根据内容推理具体地点（如"百草园"、"三味书屋"），没有明确地点则填"通用"
   - 季节：根据天气、植物、活动等线索推理（春天/夏天/秋天/冬天），无法判断填"不确定"

返回JSON格式：
{{
  "segments": [
    {{
      "time": 0,
      "title": "开场导览",
      "content": "欢迎来到鲁迅故里，介绍参观路线和注意事项",
      "tags": {{
        "主题": ["景点介绍"],
        "地点": ["鲁迅故里"],
        "季节": ["不确定"],
        "isRelatedToShaoxing": true
      }}
    }},
    {{
      "time": 120,
      "title": "百草园童年",
      "content": "讲述鲁迅童年在百草园捉蟋蟀、拔何首乌的趣事",
      "tags": {{
        "主题": ["文学作品", "景点介绍"],
        "地点": ["百草园"],
        "季节": ["夏天"],
        "isRelatedToShaoxing": true
      }}
    }}
  ]
}}

完整讲解内容：
{full_text}

只返回JSON，不要其他内容。"""

        try:
            print("  调用AI分析（整个视频一次性分析）...")
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )

            content = response.choices[0].message.content.strip()
            print(f"  AI返回: {content[:100]}")

            # 提取markdown代码块中的JSON
            if content.startswith("```"):
                lines = content.split("\n")
                json_lines = [l for l in lines[1:-1] if l.strip() and not l.strip().startswith("```")]
                content = "\n".join(json_lines)

            result = json.loads(content)
            cuts = []

            for seg in result["segments"]:
                cuts.append({
                    "time": seg["time"],
                    "title": seg["title"],
                    "reason": f"内容切换到{seg['title']}" if seg["time"] > 0 else "视频开始",
                    "content": f"这段视频主要讲了{seg['content']}",
                    "tags": seg.get("tags", {})
                })

            print(f"  ✓ AI分析完成，找到 {len(cuts)} 个片段（已包含标签）")
            return cuts

        except Exception as e:
            print(f"  AI分析失败: {e}")
            print("  切换到关键词规则分析")
            return self._keyword_analysis(segments)

    def _extract_segment_content(self, all_segments, start_time, end_time):
        """提取指定时间范围的讲解内容摘要"""
        content_parts = []
        for seg in all_segments:
            if end_time is None or (seg["start"] >= start_time and seg["start"] < end_time):
                content_parts.append(seg["text"])
            elif end_time and seg["start"] >= end_time:
                break

        full_text = "".join(content_parts)

        # 生成摘要：取前150字
        summary = full_text[:150] if len(full_text) > 150 else full_text

        return f"这段视频主要讲了{summary}..."

    def _group_segments(self, segments, interval=120):
        """将语音片段按时间间隔分组"""
        groups = []
        current_group = {"start": 0, "end": 0, "segments": []}

        for seg in segments:
            if seg["start"] - current_group["start"] > interval:
                if current_group["segments"]:
                    groups.append(current_group)
                current_group = {"start": seg["start"], "end": seg["end"], "segments": [seg]}
            else:
                current_group["segments"].append(seg)
                current_group["end"] = seg["end"]

        if current_group["segments"]:
            groups.append(current_group)

        return groups

    def _analyze_topic_and_summary(self, text, idx):
        """分析单段文本的主题和内容概括"""
        prompt = f"""分析这段鲁迅故里导览讲解的内容。

要求：
1. topic: 用4-8个字概括主题（如"百草园童年经历"、"三味书屋求学生活"）
2. summary: 用一句话概括这段讲了什么（20-40字，要具体说明内容，不要只说"介绍了xxx"）

示例：
{{"topic": "百草园童年趣事", "summary": "讲述了鲁迅小时候在百草园捉蟋蟀、拔何首乌、听长妈妈讲故事的童年经历"}}
{{"topic": "三味书屋求学", "summary": "讲述了鲁迅在三味书屋跟随寿镜吾先生读书，以及课间在后园玩耍的场景"}}

讲解内容：
{text[:600]}

只返回JSON，不要其他内容。"""

        # 重试机制：最多重试3次
        for retry in range(3):
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                print(f"  等待 {wait_time:.0f}秒（API间隔限制）...")
                time.sleep(wait_time)

            try:
                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                self.last_request_time = time.time()

                content = response.choices[0].message.content.strip()
                print(f"  GLM-5返回: {content[:100]}")

                # 提取markdown代码块中的JSON
                if content.startswith("```"):
                    lines = content.split("\n")
                    json_lines = [l for l in lines[1:-1] if l.strip()]
                    content = "\n".join(json_lines)

                result = json.loads(content)
                return result["topic"], result["summary"]

            except Exception as e:
                error_msg = str(e)
                print(f"  GLM-5分析失败 (尝试{retry+1}/3): {e}")

                # 如果是限流错误，等待更长时间
                if "429" in error_msg or "限流" in error_msg:
                    if retry < 2:  # 还有重试机会
                        wait_time = 120  # 等待2分钟
                        print(f"  遇到限流，等待{wait_time}秒后重试...")
                        time.sleep(wait_time)
                        self.last_request_time = time.time()
                        continue
                break

        # 所有重试都失败，返回默认值
        print(f"  使用默认值: 片段{idx+1}")
        return f"片段{idx+1}", text[:50]

    def _keyword_analysis(self, segments):
        """关键词规则分析"""
        print("使用关键词规则分析")
        cuts = []
        keywords = ["接下来", "现在", "那么", "然后", "另外", "还有", "说到", "提到"]

        for seg in segments:
            if any(kw in seg["text"] for kw in keywords):
                if not cuts or seg["start"] - cuts[-1]["time"] > 60:
                    cuts.append({
                        "time": seg["start"],
                        "title": f"主题{len(cuts)+1}",
                        "reason": "检测到内容主题切换",
                        "content": f"这段视频主要讲了{seg['text'][:50]}...",
                        "tags": {
                            "主题": ["景点介绍"],
                            "地点": ["通用"],
                            "季节": ["不确定"]
                        }
                    })
        return cuts

    def generate_tags_with_glm(self, text, tag_dimensions):
        """用GLM-5生成标签"""
        if not self.client:
            print("  未配置API，跳过标签生成")
            return {}

        prompt = f"""根据以下视频内容，判断是否与绍兴相关，并从3个维度生成标签。

内容：
{text[:800]}

要求：
1. 判断内容是否与绍兴相关（满足以下任一条件则为true，否则为false）：
   - 地点：提到绍兴、鲁迅故里、百草园、三味书屋、鲁迅故居、沈园、东湖等绍兴景点
   - 人物：提到鲁迅、周作人、寿镜吾先生、闰土、长妈妈等绍兴相关人物
   - 美食：提到绍兴黄酒、臭豆腐、茴香豆、霉干菜、醉鸡等绍兴特色美食
   - 文化：提到绍兴方言、社戏、乌篷船等绍兴文化特色
2. 标签维度：
   - 主题：从以下选项中选择1-2个最符合的：{tag_dimensions['主题']}
   - 地点：根据内容推理具体地点（如"百草园"、"三味书屋"、"鲁迅故居"等），如果内容中没有明确地点则填"通用"
   - 季节：根据内容中的天气、植物、活动等线索推理季节（春天/夏天/秋天/冬天），如果无法判断则填"不确定"

返回JSON格式：
{{
  "主题": ["文学作品"],
  "地点": ["百草园"],
  "季节": ["冬天"],
  "isRelatedToShaoxing": true
}}

只返回JSON，不要其他内容。"""

        try:
            elapsed = time.time() - self.last_request_time
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                print(f"  等待 {wait_time:.0f}秒（API间隔限制）...")
                time.sleep(wait_time)

            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            self.last_request_time = time.time()

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                json_lines = [l for l in lines[1:-1] if l.strip() and not l.strip().startswith("```")]
                content = "\n".join(json_lines)

            tags = json.loads(content)
            is_related = tags.get("isRelatedToShaoxing", False)
            print(f"  ✓ 标签生成完成: {tags}，绍兴相关: {is_related}")
            return tags

        except Exception as e:
            print(f"  标签生成失败: {e}")
            return {}

    def cut_video(self, video_path, cut_points, all_segments):
        """切割视频"""
        print("[3/3] 切割视频...")
        video_path = Path(video_path)
        output_dir = Path("bilibili_videos/segments") / video_path.stem
        output_dir.mkdir(parents=True, exist_ok=True)

        if not cut_points:
            print("  没有切分点，跳过")
            return []

        segments_info = []

        # 为每个切分点生成视频片段
        for i, cut in enumerate(cut_points):
            start = cut["time"]
            end = cut_points[i+1]["time"] if i+1 < len(cut_points) else None

            title = cut["title"]
            reason = cut["reason"]
            content = cut["content"]

            output = output_dir / f"part{i+1}_{title}.mp4"

            cmd = ["ffmpeg", "-i", str(video_path), "-ss", str(start)]
            if end:
                cmd.extend(["-to", str(end)])
            cmd.extend(["-c", "copy", "-y", str(output)])

            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            segments_info.append({
                "name": output.name,
                "path": str(output.as_posix()),
                "title": title,
                "reason": reason,
                "content": content,
                "tags": cut.get("tags", {})
            })

        return segments_info


    def process_video(self, video_info, tag_dimensions):
        """处理长视频（需要切割）"""
        video_path = video_info["path"]
        print(f"\n{'='*50}")
        print(f"处理: {video_info['name']} ({video_info['duration']/60:.1f}分钟)")
        print(f"{'='*50}")

        segments = self.transcribe_video(video_path)
        cuts = self.analyze_with_glm(segments, tag_dimensions)

        if not cuts:
            print("✗ 切分失败，跳过此视频")
            return []

        segments_info = self.cut_video(video_path, cuts, segments)

        print(f"[4/4] 更新JSON数据...")
        self._update_json_for_video(video_path, segments_info, {})

        video_id = self._get_video_id(video_path)
        if video_id:
            self._save_processed_id(video_id)

        print(f"完成！生成 {len(segments_info)} 个片段（已包含标签），JSON已更新\n")
        return segments_info

    def process_short_video(self, video_info, tag_dimensions):
        """处理短视频（不需要切割，只生成标签）"""
        video_path = video_info["path"]
        print(f"\n{'='*50}")
        print(f"处理短视频: {video_info['name']} ({video_info['duration']/60:.1f}分钟)")
        print(f"{'='*50}")

        segments = self.transcribe_video(video_path)
        full_text = "".join([s["text"] for s in segments])

        print(f"[2/2] 生成视频标签...")
        tags = self.generate_tags_with_glm(full_text, tag_dimensions)

        if not tags:
            print("✗ 标签生成失败，跳过此视频")
            return {}

        self._update_json_tags_only(video_path, tags)

        video_id = self._get_video_id(video_path)
        if video_id:
            self._save_processed_id(video_id)

        print(f"完成！标签已更新\n")
        return tags

def main():
    # 标签维度配置
    tag_dimensions = {
        "主题": ["文学作品", "景点介绍", "民俗风情", "游览攻略", "历史典故", "交通路线"],
        "地点": [],  # 根据文本推理
        "季节": []   # 根据文本推理，不确定则填"不确定"
    }

    cutter = BatchVideoCutter(json_file="raw_data.json")

    print("扫描视频文件夹...")
    all_videos = []
    for f in Path("bilibili_videos").glob("*.mp4"):
        duration = cutter.get_video_duration(f)
        if cutter.has_audio_stream(f):
            video_id = cutter._get_video_id(str(f))
            if video_id and video_id not in cutter.processed_ids:
                all_videos.append({"path": str(f), "name": f.name, "duration": duration, "id": video_id})
                print(f"[找到] {f.name}: {duration/60:.1f}分钟")
            elif video_id:
                print(f"[跳过] {f.name}: 已处理")

    long_videos = [v for v in all_videos if v["duration"] > 60]
    short_videos = [v for v in all_videos if v["duration"] <= 60]

    print(f"\n待处理长视频(>1分钟): {len(long_videos)} 个")
    print(f"待处理短视频(<=1分钟): {len(short_videos)} 个\n")

    # 处理长视频（切割+打标签）
    for idx, video in enumerate(long_videos, 1):
        print(f"长视频进度: {idx}/{len(long_videos)}")
        cutter.process_video(video, tag_dimensions)

    # 处理短视频（只打标签）
    for idx, video in enumerate(short_videos, 1):
        print(f"短视频进度: {idx}/{len(short_videos)}")
        cutter.process_short_video(video, tag_dimensions)

    print(f"\n{'='*50}")
    print(f"全部完成！")
    print(f"- 长视频处理: {len(long_videos)} 个")
    print(f"- 短视频处理: {len(short_videos)} 个")
    print(f"- 已更新: raw_data.json")

if __name__ == "__main__":
    main()
