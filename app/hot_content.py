# -*- coding: utf-8 -*-
"""引流自动化：热点图纸 → 小红书/抖音素材包
每个热点生成: 对比图(原参考图 vs 图纸预览) + 标题 + 文案 + 标签
输出到 hot_content/<角色>/ 目录，供手动/半自动发布
"""
import os
import sys
import json
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hot_batch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(BASE_DIR, "hot_content")

TITLE_TEMPLATES = [
    "{char}拼豆图纸来了！10种风格任选，10分钟出图",
    "最近超火的{char}，做成拼豆也太可爱了吧",
    "把{char}拼出来是什么体验？附图纸",
    "{char}粉丝集合！你的桌面缺一个拼豆{char}",
]

CAPTION_TEMPLATE = """最近{char}真的好火🔥 连夜做了拼豆图纸！
{reason}

✨ 图纸包含：
• 施工主图（坐标+色号，照着拼就行）
• 色卡统计 + 采购清单（按色号买豆不踩坑）
• 成品效果预览（先看效果再下单）

🎨 {style_count}种风格可选：{styles}
⏱ 10分钟出图，24小时交付

📮 想要同款？评论区扣1 或 私信"图纸"
#拼豆 #拼豆图纸 #手工 #DIY #手作 #二次元 #动漫周边 #谷子 #{char}"""

# 小红书发布标签策略（热点词+泛流量词+转化词组合）
def build_tags(char, category="", keyword=""):
    base = ["拼豆", "拼豆图纸", "手工", "DIY", "手作", "二次元", "动漫周边", "谷子"]
    if category:
        base.append(category)
    if char:
        base.append(char)
    if keyword and keyword != char:
        base.append(keyword)
    # 热点词加话题热度标签
    hot_tags = [f"#{char}", f"#{char}拼豆", "#拼豆定制", "#像素艺术", "#图纸定制"]
    return base + hot_tags

# 发布时间建议（小红书流量高峰）
BEST_TIMES = [
    "工作日 12:00-13:00（午休刷手机高峰）",
    "工作日 18:00-20:00（下班通勤+晚饭）",
    "周末 10:00-12:00（睡醒刷手机）",
    "周末 20:00-22:00（晚间流量高峰）",
]

def build_post_plan(entry):
    """生成小红书发布计划（标题/正文/标签/图/最佳时间/转化钩子）"""
    char = entry.get("character") or entry.get("keyword") or "热点角色"
    cat = entry.get("category", "")
    style_names = "、".join(s.get("style") for s in entry.get("styles", [])[:3]) or "经典像素"
    caption = CAPTION_TEMPLATE.format(
        char=char, reason=entry.get("reason", "热门IP角色拼豆图纸"),
        style_count=len(entry.get("styles", [])), styles=style_names)
    tags = build_tags(char, cat, entry.get("keyword"))
    plan = {
        "character": char, "category": cat,
        "titles": [t.format(char=char) for t in TITLE_TEMPLATES],
        "caption": caption,
        "tags": tags,
        "best_times": BEST_TIMES,
        "conversion_hooks": [
            "评论区扣 1 领取图纸",
            "私信「图纸」获取同款定制",
            "主页有更多图纸，点进来看看",
            "支持来图定制，宠物/情侣/全家福都能做",
        ],
    }
    return plan

def write_post_plan(path, plan):
    """写发布计划到文件"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"角色: {plan['character']} | 分类: {plan['category']}\n\n")
        f.write("【标题候选】\n" + "\n".join(plan["titles"]) + "\n\n")
        f.write("【正文】\n" + plan["caption"] + "\n\n")
        f.write("【标签】\n" + " ".join(f"#{t}" for t in plan["tags"]) + "\n\n")
        f.write("【最佳发布时间】\n" + "\n".join(plan["best_times"]) + "\n\n")
        f.write("【转化钩子】\n" + "\n".join(plan["conversion_hooks"]) + "\n")
    return path

def build_content_pack(entry, ref_path=None, out_dir=None):
    """为画廊条目生成内容素材包
    entry: hot_gallery 中的条目 {character, keyword, styles:[{style, order_id,...}]}
    """
    char = entry.get("character") or entry.get("keyword") or "热点角色"
    out_dir = out_dir or os.path.join(CONTENT_DIR, char.replace("/", "_"))
    os.makedirs(out_dir, exist_ok=True)

    meta = {"character": char, "keyword": entry.get("keyword"), "created": datetime.now().isoformat(), "styles": []}

    # 1. 每个风格生成对比图（参考图 vs 图纸预览）
    for s in entry.get("styles", []):
        order_id = s.get("order_id")
        if not order_id:
            continue
        preview = os.path.join(BASE_DIR, "orders", order_id, "delivery", "4_成品预览.png")
        sheet = os.path.join(BASE_DIR, "orders", order_id, "delivery", "1_施工主图.png")
        zipf = os.path.join(BASE_DIR, "orders", order_id, "archive", f"{order_id}_交付包.zip")
        if os.path.exists(preview):
            shutil.copy(preview, os.path.join(out_dir, f"{s['style']}_成品预览.png"))
        if os.path.exists(sheet):
            shutil.copy(sheet, os.path.join(out_dir, f"{s['style']}_施工图.png"))
        if os.path.exists(zipf):
            shutil.copy(zipf, os.path.join(out_dir, f"{s['style']}_交付包.zip"))
        meta["styles"].append({"style": s["style"], "order_id": order_id})

    # 2. 小红书发布计划（标题+正文+标签+时间+钩子）
    plan = build_post_plan(entry)
    write_post_plan(os.path.join(out_dir, "小红书发布计划.txt"), plan)
    with open(os.path.join(out_dir, "标题.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(plan["titles"]))
    with open(os.path.join(out_dir, "文案.txt"), "w", encoding="utf-8") as f:
        f.write(plan["caption"])
    with open(os.path.join(out_dir, "标签.txt"), "w", encoding="utf-8") as f:
        f.write(" ".join(f"#{t}" for t in plan["tags"]))
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {"success": True, "dir": out_dir, "titles": plan["titles"], "caption": plan["caption"][:80] + "…", "plan": plan}

def build_all_content(limit=None):
    """为画廊所有条目生成内容包"""
    gallery = hot_batch.load_gallery()
    results = []
    for entry in (gallery.get("items", [])[:limit] if limit else gallery.get("items", [])):
        res = build_content_pack(entry)
        results.append({"character": entry.get("character"), **res})
    return results

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="为画廊所有条目生成")
    args = ap.parse_args()
    results = build_all_content()
    print(json.dumps(results, ensure_ascii=False, indent=2)[:1500])
