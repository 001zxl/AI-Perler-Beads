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

def _chroma(rgb):
    return max(rgb) - min(rgb)

def _luminance(rgb):
    r, g, b = rgb
    return 0.299 * r + 0.587 * g + 0.114 * b

def _oklab_distance(a, b):
    from colormap import rgb_to_oklab, delta_e_oklab
    return delta_e_oklab(rgb_to_oklab(a), rgb_to_oklab(b))


def _oklab_of(rgb):
    """缓存版 Oklab 转换（全局减色高频调用）"""
    from colormap import rgb_to_oklab
    return rgb_to_oklab(rgb)

def global_quantize(grid_rgb, max_colors, similarity_threshold=2.0):
    """酷猫拼豆式全局减色（Zippland/perler-beads 算法）。
    原理：颜色本身已映射到色卡色号，此处按频率把"低频色并入高频相似色"——
    Oklab 距离 < 阈值的低频色整体替换为高频色。这是酷猫成品色块干净的核心：
    不加特征加权、不搞候选色，纯粹让大面积颜色吃掉相邻杂色。
    返回：合并后的 grid（色数 <= max_colors，且尽量贴近原色）。
    """
    if not grid_rgb or len(set(grid_rgb)) <= max_colors:
        return grid_rgb
    from colormap import rgb_to_oklab, delta_e_oklab
    # 兼容两种输入：RGB 元组 或 色号字符串（S2 映射后）
    is_code = isinstance(grid_rgb[0], str)
    if is_code:
        import config
        card = config.get_colorcard("mard")
        code2rgb = {code: tuple(c["rgb"]) for code, c in card["colors"].items()}
        rgb_grid = [code2rgb.get(c, (128, 128, 128)) for c in grid_rgb]
    else:
        rgb_grid = list(grid_rgb)

    counts = Counter(rgb_grid)
    order = [k for k, _ in counts.most_common()]  # 按频率降序
    replaced = set()
    out = list(rgb_grid)
    oklabs = {c: rgb_to_oklab(c) for c in set(rgb_grid)}
    for i, key in enumerate(order):
        if key in replaced:
            continue
        ok1 = oklabs[key]
        for j in range(i + 1, len(order)):
            low = order[j]
            if low in replaced:
                continue
            if delta_e_oklab(ok1, oklabs[low]) < similarity_threshold:
                replaced.add(low)
                out = [key if c == low else c for c in out]
        # 若合并后色数达标，提前结束
        if len(set(out)) <= max_colors:
            break

    if is_code:
        inv = {v: k for k, v in code2rgb.items()}
        return [inv.get(c, c) for c in out]
    return out

def _dominant_color(cell_rgb, protect_key=True):
    """特征保留主导色提取（Jett-Wu 思路）：
    区域内出现频率最高的 RGB，但保护小面积关键色（高饱和/深色/极端亮色）
    —— 防止眼睛高光、粉鼻子、Logo文字等小特征被大面积色挤掉
    """
    arr = np.asarray(cell_rgb, dtype=np.int32)
    # 5-bit 量化 (32 levels per channel) 后投票
    quantized = (arr // 8) * 8
    keys = quantized[:, 0] << 16 | quantized[:, 1] << 8 | quantized[:, 2]
    counts = Counter(keys)
    if not protect_key:
        top_key = counts.most_common(1)[0][0]
        return (int(top_key >> 16 & 0xFF), int(top_key >> 8 & 0xFF), int(top_key & 0xFF))
    total = max(1, sum(counts.values()))
    # 保护关键色：深色允许小占比（眼睛/嘴线）；高饱和必须有足够占比，避免截图/JPG噪声被放大。
    def _key_priority(rgb, share):
        r, g, b = rgb
        mx, mn = max(r, g, b), min(r, g, b)
        sat = (mx - mn) / 255.0 if mx > 0 else 0
        bright = mx / 255.0
        if bright < 0.25 and share >= 0.04:
            return 4  # 眼睛/嘴线
        if bright > 0.92 and share >= 0.10:
            return 3  # 高光
        if sat > 0.65 and share >= 0.18:
            return 2  # 球/鼻子等真实色块，必须占比够
        if sat > 0.45 and share >= 0.28:
            return 1
        return 0
    # 先找关键色（即使占比小也优先）
    key_candidates = []
    for k, count in counts.items():
        rgb = (k >> 16 & 0xFF, k >> 8 & 0xFF, k & 0xFF)
        priority = _key_priority(rgb, count / total)
        if priority:
            key_candidates.append((priority, count, k))
    if key_candidates:
        # 取关键色中占比最高的（保护眼睛/鼻子/文字）
        _, _, top_key = max(key_candidates)
    else:
        top_key = counts.most_common(1)[0][0]
    return (int(top_key >> 16 & 0xFF), int(top_key >> 8 & 0xFF), int(top_key & 0xFF))

def quantize_grid(img, width_cells, height_cells="auto", max_colors=16, use_dominant=True,
                   pure_frequency=False, auto_crop=True):
    """图片 → (grid_rgb: list[(r,g,b)] 按行优先, W, H)
    height_cells="auto" 时按实际宽高比自适应（先裁剪再算比例，避免主体拉伸）
    use_dominant=True: 主导色提取（Zippland/perler-beads 方案，消除灰色毛边）
    pure_frequency=True: 酷猫式纯频率采样（每格取像素频率最高色，不做任何特征加权保护）。
      实测特征保护会把小面积深色放大成黑块，纯频率采样五官更自然、色块更干净（酷猫原版做法）。
    auto_crop=False: 不裁剪边缘（酷猫原版做法，保留完整构图；照片类默认关闭裁剪）。
    use_dominant=False: 均值池化（旧方案，模糊）"""
    if auto_crop:
        img = _auto_crop(img)
    if height_cells == "auto" or height_cells is None:
        ratio = img.height / img.width
        height_cells = max(1, round(width_cells * ratio))
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
                if pure_frequency:
                    # 酷猫式：纯频率最高色，不做特征保护
                    grid_rgb.append(tuple(Counter(map(tuple, cell)).most_common(1)[0][0]))
                else:
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

def remove_isolated_pixels(grid_rgb, width, height, min_cluster=3, protected=None):
    """孤立噪点清理（用户要求：少于 2-3 颗的小色块自动合并）：
    1. 单格噪点: 被 3 个以上不同色包围的格 → 众数替换
    2. 小色块: 面积 < min_cluster(默认3) 的连通区域 → 合并到相邻主色
    protected: 需要保护的格子集合（眼睛/鼻口等），这些格不参与清理
    借鉴 proper-pixel-art 的网格采样修正思路。
    返回清理后的 grid
    """
    """孤立噪点清理（用户要求：少于 2-3 颗的小色块自动合并）：
    1. 单格噪点: 被 3 个以上不同色包围的格 → 众数替换
    2. 小色块: 面积 < min_cluster(默认3) 的连通区域 → 合并到相邻主色
    借鉴 proper-pixel-art 的网格采样修正思路。
    返回清理后的 grid
    """
    import numpy as np
    arr = np.array(grid_rgb, dtype=np.int32).reshape(height, width, 3)
    out = arr.copy()
    changed = 0
    protected = protected or set()
    # Pass 1: 单格噪点（被 3 个以上不同色包围；保护格跳过）
    for y in range(height):
        for x in range(width):
            i = y * width + x
            if i in protected:
                continue  # 保护格（眼睛/鼻口）不清理
            nbs = []
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = y+dy, x+dx
                if 0 <= ny < height and 0 <= nx < width:
                    nbs.append(tuple(arr[ny, nx]))
            if not nbs:
                continue
            nb_set = set(nbs)
            if len(nb_set) >= 3 and tuple(arr[y, x]) not in nb_set:
                from collections import Counter
                most = Counter(nbs).most_common(1)[0][0]
                out[y, x] = most
                changed += 1
    # Pass 2: 小色块（面积 < min_cluster 的连通区域）合并到相邻主色
    result = [tuple(p) for p in out.reshape(-1, 3)]
    # 复用 simplify_small_regions 逻辑（min_area=min_cluster，保护格跳过）
    try:
        from quantize import simplify_small_regions
        result, _ = simplify_small_regions(result, width, height, min_area=min_cluster,
                                           protect_pink=True, protected=protected)
    except Exception:
        pass
    return result, changed

def simplify_small_regions(grid_rgb, width, height, min_area=3, protect_pink=True, protected=None):
    """小区域简化（解决鼻口糊）：
    面积 < min_area 的同色连通小区域，若与周围色相近则合并到周围主色。
    protect_pink=True: 保护粉鼻子（高亮度低饱和粉）不被合并
    protected: 保护格集合（眼睛/鼻口等），区域含保护格则整区跳过合并
    """
    protected = protected or set()
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
                # 若含保护格（眼睛/鼻口）则整区保护（不合并）
                if any(idx(rr, cc) in protected for rr, cc in region):
                    continue
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

def bfs_cleanup(grid_rgb, width, height, threshold=18, protected=None):
    """BFS 连通区域杂色清理（借鉴 perler-beads）:
    孤立的小色块（面积 < min_area）若与邻域色距 < threshold，合并到相邻主色
    protected: 需要保护的格子集合（眼睛/鼻口等），这些格不参与合并
    """
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

    protected = protected or set()
    # 合并小区域（面积 < 12）到最近色邻居
    for color, region in regions:
        if len(region) >= 12:
            continue
        # 保护格所在区域整区跳过（眼睛/鼻口不参与合并）
        if any(idx(r, c) in protected for (r, c) in region):
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
