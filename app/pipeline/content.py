# -*- coding: utf-8 -*-
"""S7 内容素材：成品预览 vs 原图对比图 + 小红书文案模板（订单即引流素材）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw
from render import _get_font

def make_comparison(original_path, preview_img, out_path, style_name="经典像素", tier_name="主力款"):
    """左右对比图：原图 | 拼豆成品预览，配标题"""
    src = Image.open(original_path).convert("RGB")
    # 统一高度
    target_h = 800
    ratio = target_h / src.height
    src = src.resize((int(src.width * ratio), target_h))
    ratio2 = target_h / preview_img.height
    prev = preview_img.resize((int(preview_img.width * ratio2), target_h))
    gap = 30
    W = src.width + prev.width + gap + 40
    H = target_h + 140
    canvas = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(canvas)
    canvas.paste(src, (20, 100))
    canvas.paste(prev, (20 + src.width + gap, 100))
    tf = _get_font(40, bold=True)
    sf = _get_font(26)
    draw.text((20, 20), f"原图 → AI 拼豆成品 ({style_name})", fill="black", font=tf)
    draw.text((20, 70), f"档位: {tier_name} | 10 分钟出图，欢迎定制", fill=(80, 80, 80), font=sf)
    draw.rectangle([0, 0, W - 1, H - 1], outline="black", width=2)
    canvas.save(out_path)
    return out_path

CAPTION_TEMPLATES = [
    "我好像发现了一个很赚钱的副业…… 把照片变成{style}拼豆图纸，10 分钟出图，成本不到 2 块钱",
    "把{subject}做成拼豆送给她，她哭了 😭 定制图纸+成品都接",
    "10 秒生成拼豆图纸，AI 真的太强了！{style}风格，含色号+坐标+采购清单",
    "收到客户返图，这也太好看了吧！{subject} → 拼豆成品，{style}风",
    "手残党也能做的拼豆，成本不到 2 块钱，图纸带色号照着拼就行",
]

def make_captions(style_name="经典像素", subject="宠物", tier_name="主力款"):
    """生成 3 条小红书文案"""
    lines = []
    for tpl in CAPTION_TEMPLATES[:3]:
        lines.append(tpl.format(style=style_name, subject=subject))
    return "\n\n---\n\n".join(lines)

def write_captions_file(path, style_name, subject, tier_name, order_id):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"订单: {order_id} | {style_name} | {subject}\n\n")
        f.write(make_captions(style_name, subject, tier_name))
    return path
