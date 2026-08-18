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
        "key_points": ["眼睛", "鼻梁", "嘴巴"],
        "max_colors_default": 12,
        "outline": "soft",
        "notes": "默认半身/头像，肤色减色阶，出卡通化版",
        "suggested_styles": ["classic", "watercolor", "dither"],
    },
    "风景": {
        "key_points": ["天际线", "建筑轮廓", "主色氛围"],
        "max_colors_default": 16,
        "outline": "light",
        "notes": "海报感/剪影感/色块插画，不做高度还原",
        "suggested_styles": ["minimal", "inkwash", "stainedglass"],
    },
    "Logo": {
        "key_points": ["严格网格对齐", "文字像素化"],
        "max_colors_default": 8,
        "outline": "strong",
        "notes": "字体重新像素化，小字不做，适合姓名牌/挂件",
        "suggested_styles": ["classic", "mono"],
    },
}

DETECT_PROMPT = (
    "判断这张图片的类型，只输出一个 JSON 对象，不要其他文字: "
    "{\"type\": \"宠物|动漫|真人|风景|Logo\", \"subject\": \"主体描述(10字内)\", \"key_areas\": [\"眼睛\", \"鼻子\"]}。"
    "规则: 动物照片→宠物; 卡通/动画/漫画角色→动漫; 人物照片→真人; 风景/建筑/自然→风景; 标志/文字/徽章→Logo。"
)

def detect_type(image_path, model="qwen3-vl-plus"):
    """AI 识别图片类型，返回 (type, subject, key_areas)"""
    try:
        r = subprocess.run(["bl", "vision", "describe", "--image", image_path,
                            "--prompt", DETECT_PROMPT, "--model", model, "--quiet"],
                           capture_output=True, text=True, timeout=90)
        out = r.stdout.strip()
        # bl vision --quiet 返回外层 JSON，真正的 JSON 在 content 字段（含转义）
        import re
        content = out
        try:
            outer = json.loads(out)
            content = outer["choices"][0]["message"]["content"]
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", content)
        if not m:
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
