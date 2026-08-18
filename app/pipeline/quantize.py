# -*- coding: utf-8 -*-
"""S2 网格量化：图片 → W×H 格，每格单一 RGB（含主体裁剪、自适应宽高比、色数上限合并）"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
import numpy as np
from collections import Counter

def _auto_crop(img, margin_ratio=0.02):
    """裁剪纯色/近白边缘，让主体居中占比更大"""
    arr = np.asarray(img.convert("RGB"))
    h, w, _ = arr.shape
    # 检测非背景区域（与四角颜色差异大的像素）
    corners = [arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]
    bg = np.mean(corners, axis=0)
    dist = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    mask = dist > 40  # 背景阈值
    if mask.sum() < 50:
        return img
    ys, xs = np.where(mask)
    y0, y1 = max(ys.min() - int(h * margin_ratio), 0), min(ys.max() + int(h * margin_ratio), h)
    x0, x1 = max(xs.min() - int(w * margin_ratio), 0), min(xs.max() + int(w * margin_ratio), w)
    if (y1 - y0) < 10 or (x1 - x0) < 10:
        return img
    return img.crop((x0, y0, x1, y1))

def global_quantize(grid_rgb, max_colors):
    """全局量化：把主导色提取后的多色格压缩到 max_colors（k-means/中位切分）
    解决：主导色每格独立采样 → 色数爆炸（如 219 色）的问题"""
    img = Image.new("RGB", (len(grid_rgb), 1))
    img.putdata(grid_rgb)
    q = img.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette()
    return [(palette[i*3], palette[i*3+1], palette[i*3+2]) for i in q.getdata()]

def _dominant_color(cell_rgb):
    """主导色提取：区域内出现频率最高的 RGB（避免均值池化的灰色毛边）
    使用 5-bit 量化投票，抗噪且快"""
    arr = np.asarray(cell_rgb, dtype=np.int32)
    # 5-bit 量化 (32 levels per channel) 后投票
    quantized = (arr // 8) * 8
    keys = quantized[:, 0] << 16 | quantized[:, 1] << 8 | quantized[:, 2]
    counts = Counter(keys)
    top_key = counts.most_common(1)[0][0]
    return (int(top_key >> 16 & 0xFF), int(top_key >> 8 & 0xFF), int(top_key & 0xFF))

def quantize_grid(img, width_cells, height_cells="auto", max_colors=16, use_dominant=True):
    """图片 → (grid_rgb: list[(r,g,b)] 按行优先, W, H)
    height_cells="auto" 时按原图宽高比自适应（保持拼豆成品比例不变形）
    use_dominant=True: 主导色提取（Zippland/perler-beads 方案，消除灰色毛边）
    use_dominant=False: 均值池化（旧方案，模糊）"""
    if height_cells == "auto" or height_cells is None:
        ratio = img.height / img.width
        height_cells = max(1, round(width_cells * ratio))
    img = _auto_crop(img)
    rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
    h, w = rgb.shape[:2]
    cell_h = h / height_cells
    cell_w = w / width_cells

    grid_rgb = []
    if use_dominant:
        # 主导色：每个网格单元内取频率最高色（每个单元采样一个 block）
        for gy in range(height_cells):
            y0 = int(gy * cell_h)
            y1 = max(y0 + 1, int((gy + 1) * cell_h))
            for gx in range(width_cells):
                x0 = int(gx * cell_w)
                x1 = max(x0 + 1, int((gx + 1) * cell_w))
                cell = rgb[y0:y1, x0:x1].reshape(-1, 3)
                grid_rgb.append(_dominant_color(cell))
    else:
        # 旧方案：LANCZOS 缩放到网格（均值池化，会模糊毛边）
        grid_img = img.convert("RGB").resize((width_cells, height_cells), Image.Resampling.LANCZOS)
        q = grid_img.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
        palette = q.getpalette()
        for idx in q.getdata():
            grid_rgb.append((palette[idx * 3], palette[idx * 3 + 1], palette[idx * 3 + 2]))
    return grid_rgb, width_cells, height_cells

def color_counts(grid_rgb):
    """每色数量统计: {rgb: count}"""
    return dict(Counter(grid_rgb))

def remove_isolated_pixels(grid_rgb, width, height):
    """孤立噪点清理（解决细节碎/毛发脏）：
    若某格被 3 个以上不同色包围（4邻域），用周围众数色替换。
    借鉴 proper-pixel-art 的网格采样修正思路。
    返回清理后的 grid
    """
    import numpy as np
    arr = np.array(grid_rgb, dtype=np.int32).reshape(height, width, 3)
    out = arr.copy()
    changed = 0
    for y in range(height):
        for x in range(width):
            # 收集 4 邻域
            nbs = []
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = y+dy, x+dx
                if 0 <= ny < height and 0 <= nx < width:
                    nbs.append(tuple(arr[ny, nx]))
            if not nbs:
                continue
            nb_set = set(nbs)
            # 被 3 个以上不同色包围 → 孤立噪点
            if len(nb_set) >= 3 and tuple(arr[y, x]) not in nb_set:
                # 用众数替换
                from collections import Counter
                most = Counter(nbs).most_common(1)[0][0]
                out[y, x] = most
                changed += 1
    return [tuple(p) for p in out.reshape(-1, 3)], changed

def simplify_small_regions(grid_rgb, width, height, min_area=3, protect_pink=True):
    """小区域简化（解决鼻口糊）：
    面积 < min_area 的同色连通小区域，若与周围色相近则合并到周围主色。
    protect_pink=True: 保护粉鼻子（高亮度低饱和粉）不被合并
    """
    from colormap import rgb_to_oklab, delta_e_oklab
    n = len(grid_rgb)
    oklabs = {c: rgb_to_oklab(c) for c in set(grid_rgb)}

    def idx(r, c): return r * width + c
    def neighbors(r, c):
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
            nr, nc = r+dr, c+dc
            if 0 <= nr < height and 0 <= nc < width:
                yield nr, nc

    def is_pink(rgb):
        r, g, b = rgb
        # 粉鼻子: 红色通道高、绿蓝低、整体较亮
        return r > 180 and r > g * 1.4 and r > b * 1.2 and (r+g+b) > 350

    visited = set()
    changed = 0
    for r in range(height):
        for c in range(width):
            i = idx(r, c)
            if i in visited:
                continue
            color = grid_rgb[i]
            # BFS 同色区域
            stack, region = [(r, c)], []
            while stack:
                cr, cc = stack.pop()
                ci = idx(cr, cc)
                if ci in visited or grid_rgb[ci] != color:
                    continue
                visited.add(ci)
                region.append((cr, cc))
                for nr, nc in neighbors(cr, cc):
                    if idx(nr, nc) not in visited:
                        stack.append((nr, nc))
            # 小区域处理
            if len(region) < min_area:
                # 若含粉鼻子则保护（不合并）
                if protect_pink and any(is_pink(grid_rgb[idx(rr, cc)]) for rr, cc in region):
                    continue
                # 找边界外相邻色
                border = []
                for (rr, cc) in region:
                    for nr, nc in neighbors(rr, cc):
                        nb = grid_rgb[idx(nr, nc)]
                        if nb != color:
                            border.append(nb)
                if not border:
                    continue
                from collections import Counter
                best = Counter(border).most_common(1)[0][0]
                if delta_e_oklab(oklabs[color], oklabs[best]) < 30:
                    for (rr, cc) in region:
                        grid_rgb[idx(rr, cc)] = best
                    changed += 1
    return grid_rgb, changed

def bfs_cleanup(grid_rgb, width, height, threshold=18):
    """BFS 连通区域杂色清理（借鉴 perler-beads）:
    孤立的小色块（面积 < min_area）若与邻域色距 < threshold，合并到相邻主色
    提升色块纯净度，消除噪点"""
    from colormap import rgb_to_oklab, delta_e_oklab
    n = len(grid_rgb)
    if n == 0:
        return grid_rgb
    oklabs = {c: rgb_to_oklab(c) for c in set(grid_rgb)}

    def idx(r, c):
        return r * width + c

    def neighbors(r, c):
        for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < height and 0 <= nc < width:
                yield nr, nc

    # 统计每个连通区域（同色）
    visited = set()
    regions = []
    for r in range(height):
        for c in range(width):
            i = idx(r, c)
            if i in visited:
                continue
            color = grid_rgb[i]
            # BFS 同色区域
            stack = [(r, c)]
            region = []
            while stack:
                cr, cc = stack.pop()
                ci = idx(cr, cc)
                if ci in visited or grid_rgb[ci] != color:
                    continue
                visited.add(ci)
                region.append((cr, cc))
                for nr, nc in neighbors(cr, cc):
                    if idx(nr, nc) not in visited:
                        stack.append((nr, nc))
            regions.append((color, region))

    # 合并小区域（面积 < 12）到最近色邻居
    for color, region in regions:
        if len(region) >= 12:
            continue
        # 找区域边界外的相邻格
        border_colors = []
        for (r, c) in region:
            for nr, nc in neighbors(r, c):
                if grid_rgb[idx(nr, nc)] != color:
                    border_colors.append(grid_rgb[idx(nr, nc)])
        if not border_colors:
            continue
        # 与相邻色距最近的颜色
        best = min(border_colors, key=lambda bc: delta_e_oklab(oklabs[color], oklabs[bc]))
        if delta_e_oklab(oklabs[color], oklabs[best]) < threshold:
            for (r, c) in region:
                grid_rgb[idx(r, c)] = best
    return grid_rgb

def merge_near_colors(grid_rgb, max_colors):
    """若色数仍超限（量化后不同格同色合并仍超），迭代合并 ΔE 最近色对"""
    from colormap import delta_e2000, rgb_to_lab
    while len(set(grid_rgb)) > max_colors:
        colors = list(set(grid_rgb))
        # 找 ΔE 最近的一对
        best_pair, best_de = None, float("inf")
        labs = {c: rgb_to_lab(c) for c in colors}
        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                de = delta_e2000(labs[colors[i]], labs[colors[j]])
                if de < best_de:
                    best_de, best_pair = de, (colors[i], colors[j])
        if best_pair is None:
            break
        keep, drop = best_pair
        grid_rgb = [keep if c == drop else c for c in grid_rgb]
    return grid_rgb
