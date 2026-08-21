# -*- coding: utf-8 -*-
"""照片类关键点回填。
只从原图提取小面积暗部关键点，比如眼睛、鼻口、瞳孔。
不要把全图边缘都画回去，否则浅色宠物照片会变成脏线稿。
"""
from PIL import Image
import numpy as np


def restore_photo_details(grid_rgb, source_img, width, height, img_type="默认"):
    """返回细节回填后的 grid_rgb。
    只用于宠物/真人等照片类；动漫/Logo 不使用。
    """
    if img_type not in ("宠物", "真人", "默认"):
        return grid_rgb
    if not grid_rgb or width <= 0 or height <= 0:
        return grid_rgb

    small = source_img.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    gray = np.asarray(small.convert("L"), dtype=np.float32)
    arr = np.asarray(small, dtype=np.float32)
    dark_threshold = min(72.0, max(38.0, float(np.percentile(gray, 3.2))))
    dark_mask = gray <= dark_threshold

    # 去掉边缘背景上的暗噪点：真实五官通常不会贴着画面边缘。
    border = max(2, int(min(width, height) * 0.02))
    dark_mask[:border, :] = False
    dark_mask[-border:, :] = False
    dark_mask[:, :border] = False
    dark_mask[:, -border:] = False

    out = list(grid_rgb)

    def idx(y, x):
        return y * width + x

    def feature_color(rgb):
        r, g, b = rgb
        return (
            max(22, min(58, int(r * 0.42))),
            max(20, min(52, int(g * 0.38))),
            max(18, min(48, int(b * 0.36))),
        )

    visited = np.zeros_like(dark_mask, dtype=bool)
    max_feature_area = max(10, int(width * height * 0.006))
    min_feature_area = 2

    for sy in range(height):
        for sx in range(width):
            if not dark_mask[sy, sx] or visited[sy, sx]:
                continue
            stack = [(sx, sy)]
            visited[sy, sx] = True
            cells = []
            while stack:
                x, y = stack.pop()
                cells.append((x, y))
                for nx in (x - 1, x, x + 1):
                    for ny in (y - 1, y, y + 1):
                        if nx == x and ny == y:
                            continue
                        if 0 <= nx < width and 0 <= ny < height and dark_mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            stack.append((nx, ny))

            area = len(cells)
            if not (min_feature_area <= area <= max_feature_area):
                continue

            xs = [x for x, _ in cells]
            ys = [y for _, y in cells]
            box_w = max(xs) - min(xs) + 1
            box_h = max(ys) - min(ys) + 1
            if box_w > width * 0.18 or box_h > height * 0.16:
                continue

            # 棕色阴影块通常整体偏暖且面积拉长；眼睛/瞳孔更低亮且更紧凑。
            mean_lum = float(np.mean([gray[y, x] for x, y in cells]))
            mean_chroma = float(np.mean([max(arr[y, x]) - min(arr[y, x]) for x, y in cells]))
            if mean_lum > dark_threshold * 0.95 and mean_chroma > 65 and area > 8:
                continue

            for x, y in cells:
                i = idx(y, x)
                out[i] = feature_color(out[i])
                # 给关键点加极小的邻域，避免一颗点看起来像噪声。
                if area <= max_feature_area * 0.55:
                    for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                        if 0 <= nx < width and 0 <= ny < height:
                            ni = idx(ny, nx)
                            out[ni] = feature_color(out[ni])

    return out
