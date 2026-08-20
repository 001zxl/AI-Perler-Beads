# -*- coding: utf-8 -*-
"""面部关键点保护：眼睛/鼻子/嘴巴在量化后不被杂色或黑色吞掉
策略:
  1. AI 定位关键点区域（基于 type_aware 的 key_areas + bl vision 坐标）
  2. 眼睛保护: 区域内保留高光格（亮色格强制保留）+ 瞳孔格
  3. 鼻口保护: 小区域合并杂色，但保留粉鼻子和嘴线
"""
import os
import sys
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 眼睛高光: 亮色且接近白/浅色
def protect_eyes(grid_rgb, width, height, eye_regions=None):
    """眼睛保护: 区域内保留高光格（亮色格不参与噪点清理）
    eye_regions: [(x0, y0, x1, y1), ...] 网格坐标区域
    """
    if not eye_regions:
        return grid_rgb
    protected = set()
    for (x0, y0, x1, y1) in eye_regions:
        for y in range(max(0, y0), min(height, y1)):
            for x in range(max(0, x0), min(width, x1)):
                i = y * width + x
                r, g, b = grid_rgb[i]
                # 高光格: 很亮（接近白）
                if sum(grid_rgb[i]) > 600:
                    protected.add(i)
                # 瞳孔格: 很暗（接近黑）——保护不合并
                elif sum(grid_rgb[i]) < 120:
                    protected.add(i)
    # 返回保护格集合（供 remove_isolated_pixels 跳过）
    return protected

def detect_face_regions(image_path, grid_w, grid_h):
    """AI 定位脸部关键区域（眼睛/鼻子/嘴巴）在网格中的大致位置（codex/GPT 后端）"""
    prompt = (
        "这张图片将被转成拼豆图纸（网格约 " + str(grid_w) + "x" + str(grid_h) + "）。"
        "请定位面部关键区域在图片中的大致位置（百分比坐标 0-1，以图片左上角为原点）。"
        '只输出 JSON: {"eyes": [[x0,y0,x1,y1]], "nose": [[x0,y0,x1,y1]], "mouth": [[x0,y0,x1,y1]]}'
        "每个区域用左上角+右下角百分比表示。没有该特征就留空数组。"
    )
    try:
        from type_aware import _codex_see
        ok, content = _codex_see(image_path, prompt)
        if not ok:
            return {}
        import re
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            return {}
        d = json.loads(m.group(0))
        # 转成网格坐标
        result = {}
        for part in ("eyes", "nose", "mouth"):
            regions = d.get(part, [])
            grid_regions = []
            for (x0, y0, x1, y1) in regions:
                grid_regions.append((int(x0 * grid_w), int(y0 * grid_h),
                                     int(x1 * grid_w), int(y1 * grid_h)))
            result[part] = grid_regions
        return result
    except Exception:
        return {}

def apply_face_guard(grid_rgb, width, height, face_regions, mapper=None):
    """应用面部保护:
    - 眼睛区域: 返回保护格（跳过噪点清理）
    - 鼻口区域: 小杂色格合并到区域主色（但保留粉鼻子/嘴线）
    返回 (grid_rgb, protected_set)
    """
    protected = set()
    if not face_regions:
        return grid_rgb, protected
    # 眼睛保护
    eyes = face_regions.get("eyes", [])
    if eyes:
        protected = protect_eyes(grid_rgb, width, height, eyes)
    # 鼻口: 区域内清理小杂色（保留粉鼻子）
    nose_mouth = face_regions.get("nose", []) + face_regions.get("mouth", [])
    if nose_mouth:
        from quantize import simplify_small_regions
        # 对鼻口区域单独简化（min_area 更小，但保留粉鼻子）
        for (x0, y0, x1, y1) in nose_mouth:
            # 提取子区域
            sub_grid = []
            for y in range(max(0, y0), min(height, y1)):
                for x in range(max(0, x0), min(width, x1)):
                    sub_grid.append(grid_rgb[y * width + x])
            if not sub_grid:
                continue
            sw = x1 - x0
            sh = y1 - y0
            if sw <= 0 or sh <= 0:
                continue
            cleaned, _ = simplify_small_regions(sub_grid, sw, sh, min_area=2, protect_pink=True)
            # 写回
            idx = 0
            for y in range(max(0, y0), min(height, y1)):
                for x in range(max(0, x0), min(width, x1)):
                    grid_rgb[y * width + x] = cleaned[idx]
                    idx += 1
    return grid_rgb, protected

def detect_features_deterministic(grid_rgb, width, height, img_type="默认"):
    """确定性特征保护（无 AI 版）：不依赖 GPT 视觉，直接分析量化网格
    保护目标（眼睛/鼻口/球边界/爪子等小特征不被清理洗掉）:
      1. 深色小簇（眼睛/瞳孔/嘴线）: 亮度 < 110 且连通面积 1-10 格
      2. 粉鼻子: 高亮粉（红通道高、绿蓝低）小簇
      3. 高饱和小簇（彩色球/装饰/爪垫）: 饱和度 > 0.5 且面积 <= 12 格
    返回 protected 格子集合（flat index）
    """
    import numpy as np
    from collections import deque
    n = len(grid_rgb)
    if n == 0:
        return set()
    arr = np.array(grid_rgb, dtype=np.int32).reshape(height, width, 3)

    def _is_dark(rgb):
        return max(rgb) < 110

    def _is_pink_nose(rgb):
        r, g, b = rgb
        return r > 190 and r > g * 1.35 and r > b * 1.15 and (r + g + b) > 400

    def _is_sat(rgb):
        mx, mn = max(rgb), min(rgb)
        return (mx - mn) / 255.0 > 0.5 and mx > 60 and mn < 200

    # 标记三类候选特征格
    dark_mask = np.zeros((height, width), dtype=bool)
    pink_mask = np.zeros((height, width), dtype=bool)
    sat_mask = np.zeros((height, width), dtype=bool)
    for y in range(height):
        for x in range(width):
            rgb = tuple(arr[y, x])
            if _is_dark(rgb):
                dark_mask[y, x] = True
            if _is_pink_nose(rgb):
                pink_mask[y, x] = True
            if _is_sat(rgb):
                sat_mask[y, x] = True

    def _clusters(mask, max_area):
        """提取连通区域（4 邻域），返回面积 <= max_area 的区域列表"""
        visited = np.zeros_like(mask)
        out = []
        for y in range(height):
            for x in range(width):
                if not mask[y, x] or visited[y, x]:
                    continue
                q = deque([(y, x)])
                visited[y, x] = True
                region = []
                while q:
                    cy, cx = q.popleft()
                    region.append((cy, cx))
                    for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                        ny, nx = cy+dy, cx+dx
                        if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                            visited[ny, nx] = True
                            q.append((ny, nx))
                if len(region) <= max_area:
                    out.append(region)
        return out

    protected = set()
    # 1. 深色小簇（眼睛/瞳孔/嘴线）——宠物/真人/动漫 最需要
    if img_type in ("宠物", "真人", "动漫", "默认"):
        for region in _clusters(dark_mask, max_area=10):
            for (y, x) in region:
                protected.add(y * width + x)
        # 2. 粉鼻子（宠物重点）
        if img_type in ("宠物", "真人"):
            for region in _clusters(pink_mask, max_area=8):
                for (y, x) in region:
                    protected.add(y * width + x)
    # 3. 高饱和小簇（球/装饰/爪垫）——彩色特征保护
    for region in _clusters(sat_mask, max_area=12):
        for (y, x) in region:
            protected.add(y * width + x)
    return protected

