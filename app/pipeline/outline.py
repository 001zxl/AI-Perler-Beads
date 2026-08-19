# -*- coding: utf-8 -*-
"""轮廓算法：按图片类型自动加粗外轮廓（尤其黑边）
动漫/Logo: 强描边（黑边粗）
宠物: 中描边（保留特征不压黑）
真人: 软描边（避免脸脏）
风景: 轻描边（保留氛围）
原理: 检测主体外边界像素，向外扩展 N 格为黑色（或深色）
"""
import numpy as np

# 按类型的轮廓强度（扩展格数）
OUTLINE_THICKNESS = {
    "动漫": 2,    # 强黑边
    "Logo": 2,
    "宠物": 1,    # 中描边
    "真人": 1,    # 软描边
    "风景": 0,    # 轻描边
    "默认": 1,
}

# 轮廓色（默认黑，可用深棕替代避免过死）
def outline_color(img_type):
    if img_type in ("动漫", "Logo"):
        return (20, 20, 20)      # 纯黑
    if img_type == "宠物":
        return (45, 38, 30)      # 深棕（配合毛发不突兀）
    return (40, 40, 40)

def detect_background(grid_rgb, width, height):
    """检测背景色：取四角众数色"""
    from collections import Counter
    corners = []
    for (x, y) in [(0, 0), (width-1, 0), (0, height-1), (width-1, height-1)]:
        corners.append(grid_rgb[y * width + x])
    return Counter(corners).most_common(1)[0][0] if corners else (255, 255, 255)

def is_background(rgb, bg, tolerance=60):
    """判断是否背景色（与背景色接近）"""
    return sum(abs(a-b) for a, b in zip(rgb, bg)) < tolerance

def strengthen_outline(grid_rgb, width, height, img_type="默认"):
    """自动加粗外轮廓：
    遍历主体（非背景）格，若其 4 邻域有背景格 → 该格设为轮廓色（边缘）
    向外扩展 thickness 格（把紧邻的边缘外延也设为轮廓色）
    """
    thickness = OUTLINE_THICKNESS.get(img_type, OUTLINE_THICKNESS["默认"])
    if thickness <= 0:
        return grid_rgb
    bg = detect_background(grid_rgb, width, height)
    ocolor = outline_color(img_type)

    arr = np.array(grid_rgb, dtype=np.int32).reshape(height, width, 3)
    is_bg = np.array([[is_background(tuple(arr[y, x]), bg) for x in range(width)] for y in range(height)])

    # 找到主体边界（主体格紧邻背景）
    edge_mask = np.zeros((height, width), dtype=bool)
    for y in range(height):
        for x in range(width):
            if is_bg[y, x]:
                continue
            # 检查 4 邻域是否有背景
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = y+dy, x+dx
                if 0 <= ny < height and 0 <= nx < width and is_bg[ny, nx]:
                    edge_mask[y, x] = True
                    break

    # 轮廓扩展 thickness 格（边缘向主体内部扩展，形成粗边）
    out = arr.copy()
    # 先把边缘格设为轮廓色
    out[edge_mask] = ocolor
    # 再向内扩展 thickness-1 层（把紧邻边缘的主体格也涂轮廓色）
    for _ in range(thickness - 1):
        new_edge = np.zeros_like(edge_mask)
        for y in range(height):
            for x in range(width):
                if edge_mask[y, x]:
                    # 向内扩展（找不紧邻背景的主体邻格）
                    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                        ny, nx = y+dy, x+dx
                        if 0 <= ny < height and 0 <= nx < width and not is_bg[ny, nx] and not edge_mask[ny, nx]:
                            new_edge[ny, nx] = True
        out[new_edge] = ocolor
        edge_mask = edge_mask | new_edge

    return [tuple(p) for p in out.reshape(-1, 3)]
