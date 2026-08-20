# -*- coding: utf-8 -*-
"""S2 前置预处理：低对比图明暗增强 + 背景弱化
解决: 奶油白猫 + 粉色背景 + 粉色球 → 浅色混成一片，只剩黑轮廓撑形状
策略(确定性，无 AI):
  1. 背景色检测（四角 + 边缘带众数）
  2. 背景弱化: 背景像素去饱和 + 压暗（粉背景变浅灰粉，主体奶油白更突出）
  3. 明暗对比增强: 亮度百分位拉伸（2%-98% → 0-255）+ 轻微饱和度提升
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

    # 2. 背景弱化：背景像素 去饱和 + 压暗
    #   亮度: 压到背景原亮度的 82%；饱和度: 减 45%（粉背景 → 浅灰粉）
    out = arr.copy()
    lum = arr.mean(axis=2)
    # 背景去饱和：朝灰度方向混合
    gray = lum[..., None] * np.ones((1, 1, 3), dtype=np.float32)
    desat = arr * 0.45 + gray * 0.55
    # 压暗背景（相对原背景色更暗，拉开与主体亮度差）
    darken = desat * 0.85
    out[bg_mask] = darken[bg_mask]

    # 3. 主体亮度微提（奶油白更亮，与背景形成明暗对比）
    subject_mask = ~bg_mask
    if subject_mask.sum() > 0:
        sub_lum = lum[subject_mask].mean()
        if sub_lum < 200:  # 主体不是极亮时才提
            out[subject_mask] = np.clip(out[subject_mask] * 1.06, 0, 255)

    # 4. 全局明暗对比拉伸（亮度 2%-98% 百分位 → 0-255）
    enhanced = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    enhanced = _contrast_stretch(enhanced)

    # 5. 轻微饱和度提升（粉色球/五官更鲜明，背景已被去饱和）
    from PIL import ImageEnhance
    enhanced = ImageEnhance.Color(enhanced).enhance(1.08 + 0.05 * strength)
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
