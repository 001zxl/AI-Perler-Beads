# -*- coding: utf-8 -*-
"""闲鱼发布物料生成器：
1. 把热点图纸打包成闲鱼商品（标题/描述/图片清单）→ 手动发布或 goofish-cli 发布
2. 生成 goofish-cli 发布命令模板（需 Python 3.11+ 环境 + 用户 cookie）
"""
import os
import sys
import json
import shutil
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hot_batch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XIANYU_DIR = os.path.join(BASE_DIR, "xianyu_posts")

# 闲鱼标题模板（5 段式：核心词+场景+规格+利益点+符号）
def build_title(character, tier="主力款", price=19.9):
    return f"AI拼豆图纸定制 {character} 含色号坐标采购清单 10分钟出图 {tier}"

def build_desc(entry):
    """商品描述（含卖点+规格+交付说明+话术）"""
    char = entry.get("character") or entry.get("keyword") or "角色"
    styles = entry.get("styles", [])
    style_names = "、".join(f"{s['style']}" for s in styles[:4]) or "经典像素"
    return f"""【{char}】拼豆图纸定制 🔥

🎯 最近超火的 {char} 拼豆图纸来了！
✨ 10 分钟出图，24 小时内交付

📐 图纸包含：
• 施工主图（坐标 + 色号标注，照着拼就行，新手友好）
• 色卡统计 + 采购清单（按色号直接买豆，不踩坑）
• 成品效果预览（先看效果再下单）
• 制作建议（从哪开始拼、熨烫方式）

🎨 风格可选：{style_names} 等 10 种风格
   - 经典像素 / Q版马卡龙 / 复古8-bit / 极简线条
   - 赛博霓虹 / 波普艺术 / 蜡笔涂鸦 / 水彩柔和 / 圣诞节日 / 黑白线稿

📦 交付方式：网盘链接 / 高清原图
🔄 免费微调 1 次，满意为止
⏱ 加急 1 小时出图（+10元）

👉 拍下后请发原图（越清晰越好）
📮 本店所有图纸均经过 AI 质检，保证可施工"""

def build_price_tiers():
    """三档价格锚定"""
    return [
        {"name": "引流款", "price": 4.2, "spec": "30×30 格基础版，含色号"},
        {"name": "主力款", "price": 19.9, "spec": "60×60 格，含色号+坐标+清单+预览"},
        {"name": "利润款", "price": 69.0, "spec": "3 尺寸包 + 2 风格 + 制作教程"},
    ]

def export_post(entry, out_dir=None):
    """导出闲鱼发布物料：标题.txt + 描述.txt + 商品图（预览/施工图）+ 三档价
    返回发布物料目录
    """
    char = entry.get("character") or entry.get("keyword") or "角色"
    out_dir = out_dir or os.path.join(XIANYU_DIR, char.replace("/", "_"))
    os.makedirs(out_dir, exist_ok=True)

    # 标题 + 描述
    title = build_title(char)
    desc = build_desc(entry)
    with open(os.path.join(out_dir, "闲鱼标题.txt"), "w", encoding="utf-8") as f:
        f.write(title)
    with open(os.path.join(out_dir, "闲鱼描述.txt"), "w", encoding="utf-8") as f:
        f.write(desc)

    # 商品图（主图=成品预览，附图=施工图）
    for s in entry.get("styles", []):
        oid = s.get("order_id")
        if not oid:
            continue
        preview = os.path.join(BASE_DIR, "orders", oid, "delivery", "4_成品预览.png")
        sheet = os.path.join(BASE_DIR, "orders", oid, "delivery", "1_施工主图.png")
        if os.path.exists(preview):
            shutil.copy(preview, os.path.join(out_dir, f"商品图_{s['style']}_成品预览.png"))
        if os.path.exists(sheet):
            shutil.copy(sheet, os.path.join(out_dir, f"附图_{s['style']}_施工图.png"))
        zipf = os.path.join(BASE_DIR, "orders", oid, "archive", f"{oid}_交付包.zip")
        if os.path.exists(zipf):
            shutil.copy(zipf, os.path.join(out_dir, f"交付包_{s['style']}.zip"))

    # 三档价
    with open(os.path.join(out_dir, "定价三档.txt"), "w", encoding="utf-8") as f:
        for t in build_price_tiers():
            f.write(f"{t['name']} ¥{t['price']} | {t['spec']}\n")

    # goofish-cli 发布命令（需 Python 3.11+ 与 cookie）
    cmd = f"""# goofish-cli 发布（需 Python 3.11+ 环境）
pip install goofish-cli
goofish auth login ~/Downloads/goofish-cookies.json   # 首次导入 cookie
goofish item publish \
  --title "{title}" \
  --desc "{char}拼豆图纸定制，含色号坐标采购清单" \
  --images "{out_dir}/商品图_classic_成品预览.png" \
  --price 19.9
"""
    with open(os.path.join(out_dir, "发布命令.txt"), "w", encoding="utf-8") as f:
        f.write(cmd)

    return {"success": True, "dir": out_dir, "title": title}

def export_all(limit=None):
    """为画廊所有条目导出闲鱼物料"""
    gallery = hot_batch.load_gallery()
    results = []
    for entry in (gallery.get("items", [])[:limit] if limit else gallery.get("items", [])):
        res = export_post(entry)
        results.append({"character": entry.get("character"), **res})
    return results

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    results = export_all()
    for r in results:
        print(f"✅ {r['character']}: {r['dir']}")
