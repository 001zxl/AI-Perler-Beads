# -*- coding: utf-8 -*-
"""S2 前置预处理：低对比图温和增强 + 背景轻弱化
解决: 奶油白猫 + 粉色背景 + 粉色球 → 浅色混成一片
策略(确定性，无 AI):
  1. 背景色检测（四角 + 边缘带众数）
  2. 背景弱化: 背景像素轻微去饱和并提亮（不要压暗，否则粉色会映射成灰/棕）
  3. 温和对比/锐度增强，禁止激进百分位拉伸
仅用于非 AI 还原模式的照片类（宠物/真人/默认），对 mono/neon 等特殊风格跳过
"""
import numpy as np
from PIL import Image

# 跳过预处理的风格（特殊色板/纯色底，不需要增强）
SKIP_STYLES = {"mono", "neon", "inkwash", "minimal", "stainedglass"}

def _edge_bg_color(arr, band=0.04):
    """边缘背景色估计：四角 + 四边中心带的中位数色"""
    h, w = arr.shape[:2]
    bh, bw = max(1, int(h * band)), max(1, int(w * band))
    corners = np.concatenate([
        arr[:bh, :bw].reshape(-1, 3), arr[:bh, -bw:].reshape(-1, 3),
        arr[-bh:, :bw].reshape(-1, 3), arr[-bh:, -bw:].reshape(-1, 3),
    ])
    return np.median(corners, axis=0)

def enhance_low_contrast(img, img_type="默认", style_id="classic", strength=1.0):
    """低对比增强 + 背景弱化（确定性）
    img: PIL RGB; 返回处理后的 PIL RGB
    """
    if style_id in SKIP_STYLES:
        return img
    if img_type in ("Logo", "风景"):
        return img  # Logo 需精确色；风景保留氛围
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    if h < 10 or w < 10:
        return img

    # 1. 背景色估计
    bg = _edge_bg_color(arr)
    # 背景像素: 与背景色距 < 45（感知近似用 RGB 距离即可）
    dist_bg = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    bg_mask = dist_bg < 45
    bg_ratio = bg_mask.mean()
    # 背景占比太低（主体充满画面）→ 只做对比增强
    if bg_ratio < 0.12:
        return _contrast_stretch(img)

    # 2. 背景弱化：背景像素轻微去饱和 + 提亮。
    # 不要压暗背景；压暗会把粉白照片推到棕/灰色卡，导致成品发脏。
    out = arr.copy()
    lum = arr.mean(axis=2)
    # 背景去饱和：朝灰度方向混合
    gray = lum[..., None] * np.ones((1, 1, 3), dtype=np.float32)
    desat = arr * 0.78 + gray * 0.22
    light_bg = desat * 0.86 + np.array([255, 245, 248], dtype=np.float32) * 0.14
    out[bg_mask] = np.clip(light_bg[bg_mask], 0, 255)

    # 3. 主体亮度微提（奶油白更亮，与背景形成一点明暗差）
    subject_mask = ~bg_mask
    if subject_mask.sum() > 0:
        sub_lum = lum[subject_mask].mean()
        if sub_lum < 200:  # 主体不是极亮时才提
            out[subject_mask] = np.clip(out[subject_mask] * 1.035, 0, 255)

    # 4. 温和增强。绝不做百分位拉伸，避免把浅粉/肤色扭到红棕灰。
    enhanced = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    from PIL import ImageEnhance
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.10 + 0.03 * strength)
    enhanced = ImageEnhance.Color(enhanced).enhance(1.04)
    enhanced = ImageEnhance.Sharpness(enhanced).enhance(1.20)
    return enhanced

def _contrast_stretch(img):
    """亮度百分位拉伸：2% -> 0, 98% -> 255（明暗对比增强，防过曝）"""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    lum = arr.mean(axis=2)
    lo, hi = np.percentile(lum, 2), np.percentile(lum, 98)
    if hi - lo < 10:
        return img
    scale = 255.0 / (hi - lo)
    # 对每通道做同样拉伸（保持色相）
    out = np.clip((arr - lo) * scale, 0, 255)
    return Image.fromarray(out.astype(np.uint8))
