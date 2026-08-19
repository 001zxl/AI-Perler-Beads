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
                              bead_size="2.6mm", cell_px=56, margin_px=70):
    """渲染施工主图
    grid_rgb: 行优先 RGB 列表; color_map: {rgb: (code, name, orig_rgb, de)}
    布局: 上方标题区 + 左侧列号 + 顶部行号 + 网格（每格底色+格内色号）
    """
    title_h = 110
    coord_w = 90   # 左侧列号区宽
    coord_h = 60   # 顶部行号区高
    W = coord_w + width * cell_px + margin_px * 2
    H = title_h + coord_h + height * cell_px + margin_px * 2
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # 网格起点
    gx0 = margin_px + coord_w
    gy0 = title_h + coord_h

    # 全局对比色：根据网格区平均亮度决定粗线/坐标颜色（深色图纸用白）
    grid_avg = sum(sum(rgb) for rgb in grid_rgb) / (len(grid_rgb) * 3)
    dark_sheet = grid_avg < 128
    coarse_color = (255, 255, 255) if dark_sheet else (20, 20, 20)
    coord_color = (255, 255, 255) if dark_sheet else (20, 20, 20)
    # 标题区背景：深色图纸配深色标题区
    if dark_sheet:
        draw.rectangle([0, 0, W, title_h + coord_h], fill=(18, 18, 28))
        title_font = _get_font(40, bold=True)
        sub_font = _get_font(22)
        draw.text((margin_px, 22), title, fill="white", font=title_font)
        draw.text((margin_px, 72), f"拼豆规格: {bead_size} | 网格: {width}×{height} | 色卡: {color_map.brand}",
                  fill=(200, 200, 210), font=sub_font)
    else:
        title_font = _get_font(40, bold=True)
        sub_font = _get_font(22)
        draw.text((margin_px, 22), title, fill="black", font=title_font)
        draw.text((margin_px, 72), f"拼豆规格: {bead_size} | 网格: {width}×{height} | 色卡: {color_map.brand}",
                  fill=(80, 80, 80), font=sub_font)

    # 画格（参照专业拼豆图纸规范：每格纯色 + 色号标注右下角小字）
    def _yiq(rgb):
        return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    def _contrast(rgb):
        # 白字阈值提高：确保深色/中暗格都用白字（视觉可读性优先）
        return (255, 255, 255) if _yiq(rgb) < 160 else (30, 30, 30)

    # 细网格线颜色（浅色图纸用浅灰，深色图纸用半透明白灰）
    fine_color = (200, 200, 200) if not dark_sheet else (120, 120, 130)

    for y in range(height):
        for x in range(width):
            rgb = grid_rgb[y * width + x]
            code, name, _, _ = _lookup(color_map, rgb)
            px0, py0 = gx0 + x * cell_px, gy0 + y * cell_px
            draw.rectangle([px0, py0, px0 + cell_px - 1, py0 + cell_px - 1], fill=rgb)
            # 格内色号（右下角小字对齐，参照拼豆绘规范；描边保证深色格可读）
            code_font = _get_font(max(11, cell_px // 4), bold=True)
            text_color = _contrast(rgb)
            halo = (30, 30, 30) if text_color == (255, 255, 255) else (255, 255, 255)
            tw = draw.textlength(code, font=code_font)
            tx = px0 + cell_px - tw - max(2, cell_px // 14)
            ty = py0 + cell_px - code_font.size - max(1, cell_px // 20)
            for dx, dy in ((-1,0),(1,0),(0,-1),(0,1)):
                draw.text((tx+dx, ty+dy), code, fill=halo, font=code_font)
            draw.text((tx, ty), code, fill=text_color, font=code_font)

    # 两层网格：每格浅色细线 + 每10格粗线（参照图规范）
    for y in range(height + 1):
        yy = gy0 + y * cell_px
        if y % 10 == 0:
            draw.line([gx0, yy, gx0 + width * cell_px, yy], fill=coarse_color, width=4)
        else:
            draw.line([gx0, yy, gx0 + width * cell_px, yy], fill=fine_color, width=1)
    for x in range(width + 1):
        xx = gx0 + x * cell_px
        if x % 10 == 0:
            draw.line([xx, gy0, xx, gy0 + height * cell_px], fill=coarse_color, width=4)
        else:
            draw.line([xx, gy0, xx, gy0 + height * cell_px], fill=fine_color, width=1)

    # 双线外框（参照图：内细外粗）
    draw.rectangle([gx0 - 3, gy0 - 3, gx0 + width * cell_px + 2, gy0 + height * cell_px + 2],
                   outline=(150, 150, 150), width=2)
    draw.rectangle([gx0 - 6, gy0 - 6, gx0 + width * cell_px + 5, gy0 + height * cell_px + 5],
                   outline=coarse_color, width=3)

    # 顶部行号（1..width，仅标注关键刻度避免拥挤）
    num_font = _get_font(18)
    for x in range(width):
        if x % 10 == 0 or x % 5 == 0:
            txt = str(x + 1)
            tw = draw.textlength(txt, font=num_font)
            draw.text((gx0 + x * cell_px + (cell_px - tw) / 2, title_h + 15), txt, fill=coord_color, font=num_font)
    # 左侧列号（1..height）
    for y in range(height):
        if y % 10 == 0 or y % 5 == 0:
            txt = str(y + 1)
            tw = draw.textlength(txt, font=num_font)
            draw.text((margin_px + (coord_w - tw) / 2, gy0 + y * cell_px + (cell_px - num_font.size) / 2),
                      txt, fill=coord_color, font=num_font)

    return img

def _lookup(color_map, rgb):
    """查缓存：grid 里每个 rgb → (code, name, orig_rgb, de)"""
    if not hasattr(color_map, "_grid_cache"):
        color_map._grid_cache = {}
    if rgb not in color_map._grid_cache:
        code, name, de = color_map.nearest(rgb)
        color_map._grid_cache[rgb] = (code, name, color_map.colors[code]["rgb"], de)
    return color_map._grid_cache[rgb]
