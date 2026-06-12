# 小红书笔记爬虫

自动抓取小红书笔记的图片、文案和评论数据。

## 部署要求

### 1. 系统环境
- **操作系统**: Windows / macOS / Linux
- **Python版本**: Python 3.8+
- **浏览器**: Google Chrome（必须）

### 2. 安装依赖

```bash
pip install DrissionPage requests python-dotenv
```

或使用requirements.txt：
```bash
pip install -r requirements.txt
```

### 3. 配置Cookie

#### 方法一：自动获取（推荐）

运行Cookie获取工具：
```bash
python get_cookie.py
```

在打开的浏览器中登录小红书，登录成功后按回车键，Cookie会自动保存到 `key.env` 文件。

#### 方法二：手动配置

在项目根目录创建 `key.env` 文件：

```env
xhs_cookie=你的小红书Cookie
```

获取Cookie步骤：
1. 打开Chrome浏览器，登录小红书网页版
2. 按F12打开开发者工具
3. 切换到"Network"标签
4. 刷新页面，找到任意请求
5. 在请求头中复制完整的Cookie值
6. 粘贴到 `key.env` 文件中

### 4. 运行爬虫

```bash
python xiaohongshu_scraper.py
```

首次运行会打开浏览器，需要再次登录小红书，登录状态会保存，之后运行会自动使用已登录状态。

## 使用说明

在 `xiaohongshu_scraper.py` 顶部修改配置：

```python
SEARCH_KEYWORDS = ["鲁迅故里"]  # 搜索关键词
MAX_DOWNLOAD = 10              # 最多采集笔记数
MAX_PAGES = 2                  # 每个关键词翻几页
```

## 数据输出

- `xiaohongshu_data/` - 每个笔记的独立文件夹（包含图片、文案、评论）
- `xiaohongshu_metadata.json` - 所有笔记的元数据汇总
- `xiaohongshu_processed_ids.txt` - 已处理的笔记ID记录

## 注意事项

1. 仅用于学习研究，请遵守小红书服务条款
2. 控制采集频率，避免被限制访问
3. 尊重内容创作者版权
4. 不用于商业用途或大规模采集
