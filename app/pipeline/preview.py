# -*- coding: utf-8 -*-
"""S6 成品效果预览：客户下单前看"拼好效果图"，降退款率"""
from PIL import Image, ImageDraw, ImageFilter

def render_preview(grid_rgb, width, height, scale=48):
    """将网格渲染成平滑的成品效果（拼豆圆润感 + 轻微熨烫融合）"""
    cell = scale
    W, H = width * cell, height * cell
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    for y in range(height):
        for x in range(width):
            rgb = grid_rgb[y * width + x]
            # 圆角豆粒
            draw.rounded_rectangle(
                [x * cell + 1, y * cell + 1, (x + 1) * cell - 1, (y + 1) * cell - 1],
                radius=cell // 3, fill=rgb)
    # 轻微模糊模拟熨烫融合（分辨率提高后模糊更轻，保留锐度）
    img = img.filter(ImageFilter.GaussianBlur(radius=1.0))
    # 提升对比度/色彩/锐度让观感更"成品"且清晰
    from PIL import ImageEnhance
    img = ImageEnhance.Color(img).enhance(1.12)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    img = ImageEnhance.Contrast(img).enhance(1.05)
    return img

def render_far_view(grid_rgb, width, height, distance_factor=0.15):
    """远看预览（模拟 1 米距离看成品）:
    将成品预览缩小到 15%，再放大回来——模拟远看效果，判断"像不像"
    """
    full = render_preview(grid_rgb, width, height, scale=36)
    small = full.resize((max(1, int(full.width * distance_factor)),
                         max(1, int(full.height * distance_factor))), Image.Resampling.LANCZOS)
    return small.resize(full.size, Image.Resampling.LANCZOS)
