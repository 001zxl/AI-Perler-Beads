# -*- coding: utf-8 -*-
"""PDF 打印版导出：施工图 + 色卡颗数表 → PDF
用 PIL 直接保存 PDF（无需外部库），A4 打印友好
"""
import os
from PIL import Image, ImageDraw, ImageFont

def export_pdf(sheet_path, palette_path, info_text, out_path):
    """生成 PDF 打印版（A4 竖版）:
    第1页: 施工图（A4 适应）
    第2页: 色卡颗数表
    第3页: 图纸信息
    """
    pages = []
    # 第1页: 施工图（白边，A4 比例 210x297mm）
    sheet = Image.open(sheet_path).convert("RGB")
    a4 = (1240, 1754)  # A4 @150dpi
    page1 = Image.new("RGB", a4, "white")
    # 施工图适应 A4（留边距）
    margin = 60
    max_w = a4[0] - margin * 2
    max_h = a4[1] - margin * 2
    ratio = min(max_w / sheet.width, max_h / sheet.height)
    new_size = (int(sheet.width * ratio), int(sheet.height * ratio))
    sheet_r = sheet.resize(new_size, Image.LANCZOS)
    page1.paste(sheet_r, ((a4[0] - new_size[0]) // 2, (a4[1] - new_size[1]) // 2))
    pages.append(page1)

    # 第2页: 色卡颗数表（调大以便打印）
    if os.path.exists(palette_path):
        palette = Image.open(palette_path).convert("RGB")
        page2 = Image.new("RGB", a4, "white")
        p_ratio = min((a4[0] - 100) / palette.width, (a4[1] - 100) / palette.height)
        p_size = (int(palette.width * p_ratio), int(palette.height * p_ratio))
        palette_r = palette.resize(p_size, Image.LANCZOS)
        page2.paste(palette_r, ((a4[0] - p_size[0]) // 2, (a4[1] - p_size[1]) // 2))
        pages.append(page2)

    # 第3页: 图纸信息
    page3 = Image.new("RGB", a4, "white")
    draw = ImageDraw.Draw(page3)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 32)
    font_title = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 44)
    draw.text((60, 60), "图纸信息", font=font_title, fill="black")
    y = 160
    for line in info_text.split("\n"):
        draw.text((60, y), line, font=font, fill=(40, 40, 40))
        y += 50
    pages.append(page3)

    # 保存 PDF
    pages[0].save(out_path, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
    return out_path
