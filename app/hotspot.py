# -*- coding: utf-8 -*-
"""热点雷达：多平台热榜抓取 → AI 过滤动漫/影视/角色类 → 热点库
数据源:
  1. 微博热搜 (weibo.com/ajax/side/hotSearch, iPhone UA + Referer)
  2. B站热门 (api.bilibili.com/x/web-interface/popular, 含封面图)
  3. B站搜索 (x/web-interface/wbi/search/type, 找角色参考图)
  4. DailyHotApi 本地聚合 (可选兜底)
"""
import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOT_FILE = os.path.join(BASE_DIR, "hotspots.json")
REF_IMG_DIR = os.path.join(BASE_DIR, "samples", "hot_refs")
os.makedirs(REF_IMG_DIR, exist_ok=True)

UA_IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
UA_DESKTOP = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

def _fetch(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA_DESKTOP})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

SIXTYS_URL = "http://localhost:4398/v2"  # 60s 本地聚合热榜服务（抖音/微博/B站/知乎/头条）

def fetch_sixty(platform, limit=20):
    """从 60s 本地服务抓取热榜（真实热搜榜，非热门视频）
    platform: douyin/weibo/bili/zhihu/toutiao
    """
    try:
        raw = _fetch(f"{SIXTYS_URL}/{platform}", timeout=8)
        d = json.loads(raw)
        items = []
        for it in d.get("data", [])[:limit]:
            title = it.get("title", "")
            if title:
                items.append({
                    "word": title,
                    "heat": it.get("hot_value", it.get("hot", 0)),
                    "source": {"douyin": "抖音", "weibo": "微博", "bili": "B站",
                               "zhihu": "知乎", "toutiao": "头条"}.get(platform, platform),
                    "cover": it.get("cover", ""),
                    "url": it.get("link", ""),
                })
        return items
    except Exception:
        return []

def fetch_weibo(limit=50):
    """微博实时热搜（直连备用）"""
    try:
        raw = _fetch("https://weibo.com/ajax/side/hotSearch",
                     {"User-Agent": UA_IPHONE, "Referer": "https://weibo.com/"})
        d = json.loads(raw)
        items = []
        for it in d.get("data", {}).get("realtime", [])[:limit]:
            word = it.get("word", "")
            if word:
                items.append({
                    "word": word, "heat": it.get("num", 0),
                    "source": "微博", "label": it.get("label_name", ""),
                    "url": f"https://s.weibo.com/weibo?q={urllib.parse.quote(word)}",
                })
        return items
    except Exception as e:
        return [{"error": str(e)}]

# 小红书热榜（使用 60s 项目的签名 headers 方案，可能被限流则返回空）
XHS_URL = "https://edith.xiaohongshu.com/api/sns/v1/search/hot_list"
XHS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.7(0x18000733) NetType/WIFI Language/zh_CN",
    "referer": "https://app.xhs.cn/",
    "xy-direction": "22",
    "shield": "XYAAAAAQAAAAEAAABTAAAAUzUWEe4xG1IYD9/c+qCLOlKGmTtFa+lG434Oe+FTRagxxoaz6rUWSZ3+juJYz8RZqct+oNMyZQxLEBaBEL+H3i0RhOBVGrauzVSARchIWFYwbwkV",
    "xy-platform-info": "platform=iOS&version=8.7&build=8070515&deviceId=C323D3A5-6A27-4CE6-AA0E-51C9D4C26A24&bundle=com.xingin.discover",
    "xy-common-params": "app_id=ECFAAF02&build=8070515&channel=AppStore&deviceId=C323D3A5-6A27-4CE6-AA0E-51C9D4C26A24&device_fingerprint=20230920120211bd7b71a80778509cf4211099ea911000010d2f20f6050264&device_fingerprint1=20230920120211bd7b71a80778509cf4211099ea911000010d2f20f6050264&device_model=phone&fid=1695182528-0-0-63b29d709954a1bb8c8733eb2fb58f29&gid=7dc4f3d168c355f1a886c54a898c6ef21fe7b9a847359afc77fc24ad&identifier_flag=0&lang=zh-Hans&launch_id=716882697&platform=iOS&project_id=ECFAAF&sid=session.1695189743787849952190&t=1695190591&teenager=0&tz=Asia/Shanghai&uis=light&version=8.7",
}

def fetch_xhs(limit=15):
    """小红书实时热搜（60s 方案，可能被限流）"""
    try:
        raw = _fetch(XHS_URL, XHS_HEADERS, timeout=12)
        d = json.loads(raw)
        if d.get("code") not in (0, None) or not d.get("data"):
            return []
        items = []
        for it in d.get("data", {}).get("items", [])[:limit]:
            title = it.get("title", "")
            if title:
                items.append({
                    "word": title, "heat": it.get("score", 0),
                    "source": "小红书",
                    "url": f"https://www.xiaohongshu.com/search_result?keyword={urllib.parse.quote(title)}&type=51",
                })
        return items
    except Exception:
        return []

def fetch_bili(limit=10):
    """B站热门（含分区和封面图）"""
    try:
        raw = _fetch("https://api.bilibili.com/x/web-interface/popular?ps=20&pn=1",
                     {"User-Agent": UA_DESKTOP, "Referer": "https://www.bilibili.com/"})
        d = json.loads(raw)
        items = []
        for it in d.get("data", {}).get("list", [])[:limit]:
            title = it.get("title", "")
            tname = it.get("tname", "")
            pic = it.get("pic", "")
            if title:
                items.append({
                    "word": title, "heat": it.get("stat", {}).get("view", 0),
                    "source": "B站", "category": tname,
                    "cover": pic, "url": f"https://www.bilibili.com/video/{it.get('bvid','')}",
                })
        return items
    except Exception as e:
        return [{"error": str(e)}]

def search_bili_ref(keyword, limit=5):
    """B站搜索找参考图（封面图 URL 列表），供热点角色出图用"""
    try:
        kw = urllib.parse.quote(keyword)
        raw = _fetch(f"https://api.bilibili.com/x/web-interface/wbi/search/type?search_type=video&keyword={kw}&page=1",
                     {"User-Agent": UA_DESKTOP, "Referer": "https://www.bilibili.com/"})
        d = json.loads(raw)
        results = []
        for it in d.get("data", {}).get("result", [])[:limit]:
            if it.get("pic"):
                results.append({
                    "title": it.get("title", "").replace('<em class="keyword">', "").replace("</em>", ""),
                    "pic": it.get("pic"),
                    "bvid": it.get("bvid", ""),
                    "author": it.get("author", ""),
                })
        return results
    except Exception as e:
        return []

# ---- AI 过滤：识别动漫/影视/角色类热点 ----
# 固定分类体系（借鉴抖音/微信热点分类，单选不重叠）
# 优先匹配"内容载体"（动漫番剧→动画；游戏→游戏；电视剧电影→影视），
# 再考虑"衍生场景"（表情包/手工/谷子等），最后才是通用 IP
FIXED_CATEGORIES = ["动画", "游戏", "影视", "娱乐", "宠物", "手工", "表情包", "美食", "生活", "其他"]

FILTER_PROMPT = (
    "以下是一批网络热点词/标题（来自抖音/微博/B站/知乎/头条热搜榜）。"
    "请筛选出**适合做拼豆图纸的热点**（有明确形象/角色/IP 的内容）并分类。\n"
    "适合做拼豆: 动漫番剧角色、游戏角色、影视角色、宠物、可爱形象、表情包、手工DIY相关等。"
    "排除: 时政、财经、体育赛事、社会新闻、科技数码产品、纯八卦、名人逝世的悼念类、"
    "以及'攻略/教程/盘点/合集/如何评价'等无具体形象的内容。\n"
    "硬性要求 character: 必须提取**简短的角色名或IP名**（2-8字），如'芙宁娜'、'皮卡丘'、'吉伊卡哇'、'海贼王'。"
    "如果热点词是长标题（如'如何评价原神新角色薇斯纳立绘'），提取核心角色名'薇斯纳'；"
    "标题里有明确角色名就提取，没有具体形象就不要选。\n"
    "分类规则（单选，从固定列表选，不重叠）:\n"
    "- 动画: 番剧/动画电影/二次元作品角色\n"
    "- 游戏: 游戏角色/游戏IP/电竞形象\n"
    "- 影视: 电视剧/电影/综艺角色\n"
    "- 娱乐: 明星/网红/偶像/综艺\n"
    "- 宠物: 猫狗等萌宠形象\n"
    "- 手工: 手工DIY/拼豆/钩织/手作相关内容\n"
    "- 表情包: 表情包/梗图/网络形象\n"
    "- 美食/生活/其他: 其余适合做拼豆的内容\n"
    "只输出 JSON 数组，每个元素是 {\"word\": 原词, \"character\": 角色名(必须非空), \"category\": 分类, \"reason\": 简短理由}，"
    "最多选 10 个，没有就输出 []。"
)

def ai_filter(items):
    """调用 bl text 让 AI 筛选动漫/影视/角色类热点"""
    import subprocess
    words = [it["word"] for it in items if "error" not in it]
    if not words:
        return []
    prompt = FILTER_PROMPT + "\n热点词:\n" + "\n".join(f"- {w}" for w in words[:40])
    try:
        r = subprocess.run(["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                           "--color", "never"],
                           input=prompt + "\n", capture_output=True, text=True, timeout=150)
        out = r.stdout.strip()
        # 解析 JSON
        import re
        m = re.search(r"\[[\s\S]*\]", out)
        if not m:
            return []
        data = json.loads(m.group(0))
        by_word = {it["word"]: it for it in items}
        results = []
        for d in data:
            w = d.get("word", "")
            if w in by_word:
                char = d.get("character", "").strip()
                # 没提取出角色名的说明无具体形象，跳过
                if not char or len(char) > 12:
                    continue
                cat = d.get("category", "其他")
                if cat not in FIXED_CATEGORIES:
                    cat = "其他"
                results.append({**by_word[w], "character": char,
                                "category": cat, "reason": d.get("reason", "")})
        return results
    except Exception:
        return []

CATEGORIES = FIXED_CATEGORIES

def category_summary(items):
    """热点分类统计"""
    from collections import Counter
    c = Counter(it.get("category", "其他") for it in items)
    return dict(c)

# 正向关键词：命中这些词的才可能适合拼豆（动漫/游戏/影视/宠物/手工等）
RELEVANT_KEYWORDS = [
    # 动画/番剧
    "动画", "番剧", "国创", "剧场版", "漫画", "动漫", "新番", "动画电影", "二次元",
    # 游戏
    "游戏", "原神", "崩坏", "星穹", "绝区零", "宝可梦", "皮卡丘", "塞尔达", "王者",
    "无畏契约", "英雄联盟", "LOL", "PVZ", "植物大战僵尸", "游戏角色", "手游",
    # 影视/剧
    "电影", "电视剧", "新片", "票房", "上映", "剧集", "影评", "角色",
    # 角色/明星/网红
    "奥特曼", "海贼王", "火影", "龙珠", "柯南", "蜡笔小新", "哆啦A梦", "吉伊卡哇",
    "chiikawa", "玲娜贝儿", "迪士尼", "乐高", "手办", "盲盒", "谷子", "cosplay", "COS",
    # 宠物
    "猫", "狗", "宠物", "萌宠", "橘猫", "小猫", "小狗", "布偶", "柯基", "柴犬",
    # 手工/DIY
    "手工", "拼豆", "DIY", "手作", "钩织", "编织", "积木", "十字绣",
    # 可爱/表情
    "表情包", "可爱", "萌", "吉祥物", "IP", "联名", "周边", "手办",
    # 节日/纪念
    "七夕", "圣诞", "万圣", "生日", "纪念日", "情人节",
]

def prefilter(items, max_count=25):
    """正向预筛：只保留明显可能适合拼豆的热点（命中关键词），减少 AI 负担"""
    kept = []
    for it in items:
        w = it.get("word", "")
        if any(k in w for k in RELEVANT_KEYWORDS):
            kept.append(it)
    # 按热度取前 max_count
    kept.sort(key=lambda x: -x.get("heat", 0))
    return kept[:max_count]

def collect_hotspots(use_ai_filter=True):
    """完整流程: 抓取 → 去重 → 预筛 → AI 过滤 → 存库 → 返回"""
    raw = collect_raw()
    dedup = dedupe(raw)
    candidates = prefilter(dedup)
    if use_ai_filter and candidates:
        filtered = ai_filter(candidates)
        if filtered:
            save_hotspots(filtered)
            return filtered
    # AI 失败时降级：按关键词启发式过滤
    fallback = heuristic_filter(dedup)
    save_hotspots(fallback)
    return fallback

ANIME_KEYWORDS = ["动画", "番剧", "国创", "剧场版", "漫画", "动漫", "角色", "手办",
                  "游戏", "原神", "崩坏", "星穹", "绝区零", "宝可梦", "皮卡丘",
                  "吉伊卡哇", "chiikawa", "chiikawa", "表情包", "IP", "联名",
                  "cos", "同人", "周边", "手作", "谷子", "玩偶", "吉祥物"]

def heuristic_filter(items):
    """关键词启发式过滤（AI 不可用时的降级，尽量提取角色名）"""
    out = []
    for it in items:
        w = it.get("word", "")
        if any(k.lower() in w.lower() for k in ANIME_KEYWORDS):
            cat = "游戏" if any(k in w for k in ["原神", "崩坏", "星穹", "绝区零", "游戏", "宝可梦", "手游", "PVZ", "植物大战僵尸"]) else \
                  ("动画" if any(k in w for k in ["动画", "番剧", "国创", "剧场版", "漫画", "动漫", "奥特曼", "海贼王"]) else "其他")
            # 从标题提取角色名：优先已知 IP，否则用原标题前 8 字
            char = ""
            for ip in ["奥特曼", "海贼王", "植物大战僵尸", "无畏契约", "原神", "宝可梦", "吉伊卡哇", "火影", "柯南"]:
                if ip in w:
                    char = ip
                    break
            if not char:
                char = w[:6]
            out.append({**it, "character": char, "category": cat, "reason": "关键词命中(降级)"})
    return out[:10]

# ---- 热点库存储 ----
def load_hotspots():
    if os.path.exists(HOT_FILE):
        try:
            with open(HOT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"updated": None, "items": []}

def save_hotspots(items, updated=None):
    data = {"updated": updated or datetime.now().isoformat(), "items": items}
    with open(HOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def collect_raw():
    """抓取所有源（60s 多平台热搜 + 直连兜底），合并"""
    items = []
    # 60s 本地服务：5 个平台真实热搜（优先）
    for plat in ("douyin", "weibo", "bili", "zhihu", "toutiao"):
        res = fetch_sixty(plat)
        if res:
            items.extend(res)
    # 直连兜底（60s 挂了时至少还有微博/B站）
    if not items:
        for fn in (fetch_weibo, fetch_bili):
            res = fn()
            for it in res:
                if "error" not in it:
                    items.append(it)
    return items

def dedupe(items):
    """按 word 去重（跨源同词保留热度高的）"""
    seen = {}
    for it in items:
        w = it.get("word", "")
        if not w:
            continue
        if w not in seen or it.get("heat", 0) > seen[w].get("heat", 0):
            seen[w] = it
    return sorted(seen.values(), key=lambda x: -x.get("heat", 0))
