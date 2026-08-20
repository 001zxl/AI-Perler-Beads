# -*- coding: utf-8 -*-
"""S6 成品效果预览：客户下单前看"拼好效果图"，降退款率"""
from PIL import Image, ImageDraw, ImageFilter

def render_preview(grid_rgb, width, height, scale=56):
    """将网格渲染成清晰的成品效果（硬边颗粒 + 高锐度，不模糊）"""
    cell = scale
    W, H = width * cell, height * cell
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    for y in range(height):
        for x in range(width):
            rgb = grid_rgb[y * width + x]
            # 方形颗粒（硬边，清晰），微圆角
            draw.rounded_rectangle(
                [x * cell + 1, y * cell + 1, (x + 1) * cell - 1, (y + 1) * cell - 1],
                radius=cell // 8, fill=rgb)  # 圆角减小，边缘更利落
    # 极轻微柔化（保持清晰度）
    img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
    # 强力锐化 + 高对比，让颗粒边界清晰
    from PIL import ImageEnhance
    img = ImageEnhance.Color(img).enhance(1.15)
    img = ImageEnhance.Sharpness(img).enhance(3.0)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    return img

def render_far_view(grid_rgb, width, height, distance_factor=0.15):
    """远看预览（模拟 1 米距离看成品）:
    将成品预览缩小到 15%，再放大回来——模拟远看效果，判断"像不像"
    """
    full = render_preview(grid_rgb, width, height, scale=36)
    small = full.resize((max(1, int(full.width * distance_factor)),
                         max(1, int(full.height * distance_factor))), Image.Resampling.LANCZOS)
    return small.resize(full.size, Image.Resampling.LANCZOS)
