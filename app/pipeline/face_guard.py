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

def detect_face_regions(image_path, grid_w, grid_h, model="qwen3-vl-plus"):
    """AI 定位脸部关键区域（眼睛/鼻子/嘴巴）在网格中的大致位置"""
    prompt = (
        "这张图片将被转成拼豆图纸（网格约 " + str(grid_w) + "x" + str(grid_h) + "）。"
        "请定位面部关键区域在图片中的大致位置（百分比坐标 0-1，以图片左上角为原点）。"
        '只输出 JSON: {"eyes": [[x0,y0,x1,y1]], "nose": [[x0,y0,x1,y1]], "mouth": [[x0,y0,x1,y1]]}'
        "每个区域用左上角+右下角百分比表示。没有该特征就留空数组。"
    )
    try:
        r = subprocess.run(["bl", "vision", "describe", "--image", image_path,
                            "--prompt", prompt, "--model", model, "--quiet"],
                           capture_output=True, text=True, timeout=90)
        out = r.stdout.strip()
        import re
        content = out
        try:
            outer = json.loads(out)
            content = outer["choices"][0]["message"]["content"]
        except Exception:
            pass
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
