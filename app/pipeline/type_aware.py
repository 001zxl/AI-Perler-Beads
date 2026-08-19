# -*- coding: utf-8 -*-
"""图片类型识别 + 差异化拼豆策略
类型: 宠物/动漫/真人/风景/Logo
按类型差异化: 重点保护区域 + 参数建议（色数/轮廓/风格）
"""
import os
import sys
import subprocess
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TYPE_STRATEGIES = {
    "宠物": {
        "key_points": ["眼睛", "耳朵", "鼻子", "嘴巴"],
        "max_colors_default": 12,
        "outline": "medium",
        "notes": "眼睛提亮+鼻口简化+毛色抽象成方向性斑纹",
        "suggested_styles": ["classic", "pixel_pet", "chibi_pastel"],
    },
    "动漫": {
        "key_points": ["眼睛", "发型", "服装标志色"],
        "max_colors_default": 16,
        "outline": "strong",
        "notes": "黑描边加强，少面部阴影，出16-bit/Q版/徽章风",
        "suggested_styles": ["retro8bit", "kawaii", "classic"],
    },
    "真人": {
        "key_points": ["眼睛", "鼻梁", "嘴巴", "手势"],
        "max_colors_default": 12,
        "outline": "soft",
        "notes": "默认半身/头像，肤色减色阶，先卡通化再拼豆，手势单独保护",
        "suggested_styles": ["classic", "watercolor", "dither"],
        "cartoonize_first": True,
    },
    "风景": {
        "key_points": ["天际线", "建筑轮廓", "主色氛围"],
        "max_colors_default": 16,
        "outline": "light",
        "notes": "海报感/剪影感/色块插画，不做高度还原",
        "suggested_styles": ["minimal", "inkwash", "stainedglass"],
    },
    "Logo": {
        "key_points": ["严格网格对齐", "文字像素化", "字体笔画保护"],
        "max_colors_default": 8,
        "outline": "strong",
        "notes": "字体必须重新像素化设计（不能直接缩小否则断笔），小字不做",
        "suggested_styles": ["classic", "mono"],
        "text_protect": True,
    },
}

DETECT_PROMPT = (
    "判断这张图片的类型，只输出一个 JSON 对象，不要其他文字: "
    "{\"type\": \"宠物|动漫|真人|风景|Logo\", \"subject\": \"主体描述(10字内)\", \"key_areas\": [\"眼睛\", \"鼻子\"]}。"
    "规则: 动物照片→宠物; 卡通/动画/漫画角色→动漫; 人物照片→真人; 风景/建筑/自然→风景; 标志/文字/徽章→Logo。"
)

def _codex_see(image_path, prompt, timeout=150):
    """codex CLI 看图（GPT 后端，替代 bl vision）"""
    cmd = ["codex", "exec", "--skip-git-repo-check", "--sandbox", "read-only",
           "--color", "never", "-i", image_path]
    try:
        r = subprocess.run(cmd, input=prompt + "\n", capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return False, r.stderr.strip()[-300:] or "codex 视觉失败"
        return True, r.stdout.strip()
    except Exception as e:
        return False, str(e)

def detect_type(image_path, model=None):
    """AI 识别图片类型（codex vision，GPT 后端）
    返回 (type, subject, key_areas)"""
    try:
        ok, content = _codex_see(image_path, DETECT_PROMPT)
        if not ok:
            return "宠物", "未知", []
        import re
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
            for t in ("动漫", "真人", "风景", "Logo", "宠物"):
                if t in content:
                    return t, "未知", []
            return "宠物", "未知", []
        d = json.loads(m.group(0))
        t = d.get("type", "宠物")
        if t not in TYPE_STRATEGIES:
            t = "宠物"
        return t, d.get("subject", ""), d.get("key_areas", [])
    except Exception:
        return "宠物", "未知", []

def get_strategy(img_type):
    """获取类型策略"""
    return TYPE_STRATEGIES.get(img_type, TYPE_STRATEGIES["宠物"])
