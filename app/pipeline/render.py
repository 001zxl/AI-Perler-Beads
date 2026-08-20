# -*- coding: utf-8 -*-
"""S4 施工图渲染：带坐标编号、格内色号、标题的高清施工主图"""
from PIL import Image, ImageDraw, ImageFont
import os

FONT_DIR = "/System/Library/Fonts"
_FONT_CACHE = {}

# 中文字体优先（否则中文标题显示方框）
_CN_FONT_CANDIDATES = [
    os.path.join("/System/Library/Fonts", "PingFang.ttc"),
    os.path.join("/System/Library/Fonts", "Hiragino Sans GB.ttc"),
    os.path.join("/System/Library/Fonts", "STHeiti Medium.ttc"),
    os.path.join("/System/Library/Fonts", "Supplemental", "Arial Unicode.ttf"),
    os.path.join("/System/Library/Fonts", "Supplemental", "Songti.ttc"),
]

def _get_font(size, bold=False):
    key = (size, bold)
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    # 中文字体优先
    for p in _CN_FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                _FONT_CACHE[key] = font
                return font
            except Exception:
                continue
    # 兜底 Arial/Helvetica
    candidates = [
        os.path.join(FONT_DIR, "Supplemental", "Arial Bold.ttf" if bold else "Arial.ttf"),
        os.path.join(FONT_DIR, "Helvetica.ttc"),
    ]
    font = None
    for p in candidates:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font

def render_construction_sheet(grid_rgb, width, height, color_map, title="拼豆施工图",
                              bead_size="2.6mm", cell_px=52, margin_px=60,
                              color_rows=None, suggestions=None, scorability=None,
                              subject="", img_type="默认"):
    """渲染施工主图（对标海绵宝宝/蟹老板/朱迪专业图纸，并超越）
    布局:
      ① 标题栏: 主题/成品尺寸/豆径/色数 四参数 + 浅灰底纹
      ② 主网格: 每5格坐标 + 居中色号(自动反色) + 双层网格线
      ③ 底部色卡用量区: 色块+色号+颜色名+颗数+占比 + 合计
      ④ 制作建议区: 分区顺序/易混淆色/备料
      ⑤ 可拼性评分角标
    """
    # 色卡用量数据（由 run.py 传入，格式 [(code,name,rgb,count,suggest),...]）
    color_rows = color_rows or []
    sugg = suggestions or {}
    sc = scorability or {}

    title_h = 90
    coord_w = 80   # 左侧列号区宽
    coord_h = 50   # 顶部行号区高
    # 底部信息区高度（色卡用量 + 制作建议）
    bottom_h = 120 + (40 * max(1, (len(color_rows) + 5) // 10)) + 90

    W = coord_w + width * cell_px + margin_px * 2
    H = title_h + coord_h + height * cell_px + margin_px + bottom_h
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # 网格起点
    gx0 = margin_px + coord_w
    gy0 = title_h + coord_h

    # 全局对比色
    grid_avg = sum(sum(rgb) for rgb in grid_rgb) / (len(grid_rgb) * 3)
    dark_sheet = grid_avg < 128
    coarse_color = (255, 255, 255) if dark_sheet else (20, 20, 20)
    coord_color = (255, 255, 255) if dark_sheet else (20, 20, 20)
    fine_color = (200, 200, 200) if not dark_sheet else (120, 120, 130)

    # ---- ① 标题栏（四参数 + 浅灰底纹，对标参考图）----
    title_font = _get_font(34, bold=True)
    sub_font = _get_font(20)
    if dark_sheet:
        draw.rectangle([0, 0, W, title_h], fill=(18, 18, 28))
        draw.text((margin_px, 22), title, fill="white", font=title_font)
        color_count = len(set(grid_rgb))
        params = f"主题:{subject or title}  成品尺寸:{width}×{height}格  拼豆规格:{bead_size}  颜色数量:{color_count}色"
        draw.text((margin_px, 60), params, fill=(200, 200, 210), font=sub_font)
    else:
        draw.rectangle([0, 0, W, title_h], fill=(245, 245, 245))
        draw.rectangle([0, title_h - 2, W, title_h], fill=(200, 200, 200))  # 底部分隔线
        draw.text((margin_px, 18), title, fill="black", font=title_font)
        color_count = len(set(grid_rgb))
        params = f"主题:{subject or title}  成品尺寸:{width}×{height}格  拼豆规格:{bead_size}  颜色数量:{color_count}色"
        draw.text((margin_px, 58), params, fill=(80, 80, 80), font=sub_font)

    # ---- ② 画格（居中色号 + 自动反色，对标参考图）----
    def _yiq(rgb):
        return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    def _contrast(rgb):
        return (255, 255, 255) if _yiq(rgb) < 160 else (30, 30, 30)

    for y in range(height):
        for x in range(width):
            rgb = grid_rgb[y * width + x]
            code, name, orig_rgb, _ = _lookup(color_map, rgb)
            px0, py0 = gx0 + x * cell_px, gy0 + y * cell_px
            # 用映射后的真实色号色填色（与采购清单一致，预览即实物色）
            fill_rgb = orig_rgb if orig_rgb is not None else rgb
            draw.rectangle([px0, py0, px0 + cell_px - 1, py0 + cell_px - 1], fill=tuple(fill_rgb))
            # 居中色号
            code_font = _get_font(max(10, cell_px // 4), bold=True)
            text_color = _contrast(fill_rgb)
            halo = (30, 30, 30) if text_color == (255, 255, 255) else (255, 255, 255)
            tw = draw.textlength(code, font=code_font)
            tx = px0 + (cell_px - tw) / 2
            ty = py0 + (cell_px - code_font.size) / 2
            for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                draw.text((tx+dx, ty+dy), code, fill=halo, font=code_font)
            draw.text((tx, ty), code, fill=text_color, font=code_font)

    # 双层网格线
    for y in range(height + 1):
        yy = gy0 + y * cell_px
        if y % 10 == 0:
            draw.line([gx0, yy, gx0 + width * cell_px, yy], fill=coarse_color, width=3)
        else:
            draw.line([gx0, yy, gx0 + width * cell_px, yy], fill=fine_color, width=1)
    for x in range(width + 1):
        xx = gx0 + x * cell_px
        if x % 10 == 0:
            draw.line([xx, gy0, xx, gy0 + height * cell_px], fill=coarse_color, width=3)
        else:
            draw.line([xx, gy0, xx, gy0 + height * cell_px], fill=fine_color, width=1)

    # 双线外框
    draw.rectangle([gx0 - 3, gy0 - 3, gx0 + width * cell_px + 2, gy0 + height * cell_px + 2],
                   outline=(150, 150, 150), width=2)
    draw.rectangle([gx0 - 6, gy0 - 6, gx0 + width * cell_px + 5, gy0 + height * cell_px + 5],
                   outline=coarse_color, width=3)

    # 坐标：每5格标号（对标参考图）
    num_font = _get_font(16)
    for x in range(width):
        if x % 5 == 0:
            txt = str(x + 1)
            tw = draw.textlength(txt, font=num_font)
            draw.text((gx0 + x * cell_px + (cell_px - tw) / 2, title_h + 12), txt, fill=coord_color, font=num_font)
    for y in range(height):
        if y % 5 == 0:
            txt = str(y + 1)
            tw = draw.textlength(txt, font=num_font)
            draw.text((margin_px + (coord_w - tw) / 2, gy0 + y * cell_px + (cell_px - num_font.size) / 2),
                      txt, fill=coord_color, font=num_font)

    # ---- ③ 底部色卡用量区（色块+色号+名+颗数+占比+合计，对标参考图）----
    grid_bottom = gy0 + height * cell_px
    info_top = grid_bottom + 20
    info_font = _get_font(18)
    info_font_b = _get_font(18, bold=True)
    per_row = 10
    info_rows = (len(color_rows) + per_row - 1) // per_row if color_rows else 0
    if color_rows:
        # 色卡区背景
        draw.rectangle([margin_px, info_top, W - margin_px, info_top + 100],
                       fill=(250, 250, 250), outline=(200, 200, 200))
        draw.text((margin_px + 10, info_top + 6), "色卡与用量统计", font=_get_font(20, bold=True), fill="black")
        total = sum(r["count"] for r in color_rows)
        # 色卡排布（每行最多 10 个）
        swatch_size = 26
        per_row = 10
        y_row = info_top + 34
        for idx, r in enumerate(color_rows):
            col = idx % per_row
            row = idx // per_row
            sx = margin_px + 10 + col * ((W - margin_px * 2 - 20) // per_row)
            sy = y_row + row * 34
            # 色块
            draw.rectangle([sx, sy, sx + swatch_size, sy + swatch_size], fill=tuple(r["rgb"]), outline="black")
            # 色号 + 名称 + 数量
            pct = r["count"] / total * 100 if total else 0
            txt = f"{r['code']} {r['name']} {r['count']}颗({pct:.0f}%)"
            draw.text((sx + swatch_size + 4, sy), txt, font=info_font, fill="black")
        # 合计栏
        total_y = y_row + (len(color_rows) + per_row - 1) // per_row * 34 + 6
        draw.rectangle([margin_px + 10, total_y, margin_px + 220, total_y + 34],
                       fill=(240, 240, 240), outline="black")
        draw.text((margin_px + 20, total_y + 6), f"合计: {total} 颗", font=info_font_b, fill="black")
        # 可拼性评分角标
        if sc:
            score_txt = f"可拼性 {sc.get('score', '?')}分 ({sc.get('verdict', '')})"
            tw = draw.textlength(score_txt, font=info_font_b)
            draw.text((W - margin_px - tw - 10, total_y + 6), score_txt, font=info_font_b, fill=(0, 120, 60))

    # ---- ④ 制作建议区 ----
    sugg_top = info_top + 100 + max(0, info_rows - 1) * 34
    if sugg:
        draw.rectangle([margin_px, sugg_top, W - margin_px, sugg_top + 80],
                       fill=(252, 250, 245), outline=(210, 200, 180))
        draw.text((margin_px + 10, sugg_top + 6), "制作建议", font=_get_font(20, bold=True), fill="black")
        y_s = sugg_top + 34
        for key, txt in [("sector", sugg.get("sector", "")), ("confusing", sugg.get("confusing", "")),
                         ("material", sugg.get("material", "")), ("tips", sugg.get("tips", ""))]:
            if txt:
                # 长文本截断到一行（按宽度）
                while draw.textlength(txt, font=info_font) > W - margin_px * 2 - 20 and len(txt) > 10:
                    txt = txt[:-1]
                draw.text((margin_px + 10, y_s), txt, font=info_font, fill=(60, 60, 60))
                y_s += 26

    return img

def _lookup(color_map, rgb):
    """查缓存：grid 里每个 rgb → (code, name, orig_rgb, de)"""
    if not hasattr(color_map, "_grid_cache"):
        color_map._grid_cache = {}
    if rgb not in color_map._grid_cache:
        code, name, de = color_map.nearest(rgb)
        color_map._grid_cache[rgb] = (code, name, color_map.colors[code]["rgb"], de)
    return color_map._grid_cache[rgb]
