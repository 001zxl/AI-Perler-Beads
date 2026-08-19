# -*- coding: utf-8 -*-
"""制作建议生成器：分区施工顺序 + 易混淆色提醒 + 备料建议
对标蟹老板/朱迪参考图纸的专业制作建议，并升级：
- 分区顺序按图片类型模板化
- 易混淆色 = 色卡中 ΔE 相近的颜色对（自动检测）
- 备料冗余 +5%
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 按类型的分区施工顺序模板
SECTOR_ORDER = {
    "宠物": ["头部轮廓", "耳朵", "眼睛鼻子", "身体毛色", "四肢尾巴", "补细节"],
    "动漫": ["脸部轮廓", "眼睛", "发型", "服装主色", "配饰", "背景补全"],
    "真人": ["脸部轮廓", "眼睛嘴巴", "头发", "肤色填充", "衣服", "背景"],
    "风景": ["天际线/地平线", "主体轮廓", "主色块", "细节点缀", "前景"],
    "Logo": ["外框轮廓", "主体图形", "文字笔画", "内部填充", "检查对齐"],
    "默认": ["主体轮廓", "主要色块", "细节填充", "背景", "补全检查"],
}

def sector_order(img_type="默认"):
    """分区施工顺序建议"""
    steps = SECTOR_ORDER.get(img_type, SECTOR_ORDER["默认"])
    return "建议施工顺序: " + " → ".join(steps) + "（从大到小、先轮廓后细节）"

def confusing_colors(mapper, rows, threshold=10):
    """检测易混淆色对：色卡中 ΔE < threshold 的颜色对
    rows: stats 计算出的 [(code, name, rgb, count), ...]
    """
    if not rows or len(rows) < 2:
        return []
    pairs = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            c1, n1 = rows[i]["code"], rows[i]["name"]
            c2, n2 = rows[j]["code"], rows[j]["name"]
            try:
                alts = mapper.alternatives(c1, top_n=3)
                for a in alts:
                    if a["code"] == c2:
                        pairs.append((c1, n1, c2, n2, a["dE"]))
            except Exception:
                pass
    # 去重 + 排序
    seen = set()
    result = []
    for p in sorted(pairs, key=lambda x: x[4]):
        key = tuple(sorted([p[0], p[2]]))
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result[:4]

def confusing_text(pairs):
    """易混淆色提醒文本"""
    if not pairs:
        return "无特别易混淆色，按色号区分即可"
    parts = [f"{a}({an})与{b}({bn})颜色接近，注意区分" for a, an, b, bn, de in pairs]
    return "易混淆色提醒: " + "; ".join(parts)

def material_advice(total_beads, rows, reserve=0.05):
    """备料建议（按色号+5%冗余）"""
    lines = []
    for r in rows[:5]:
        suggest = r["suggest"]
        lines.append(f"{r['code']} {r['name']}: 用{r['count']}颗，建议备{suggest}颗(+5%)")
    if len(rows) > 5:
        lines.append(f"其余{len(rows)-5}色同理各多备5%")
    return "备料建议: " + "; ".join(lines)

def build_suggestions(img_type, mapper, rows, total_beads):
    """完整制作建议（结构化）"""
    return {
        "sector": sector_order(img_type),
        "confusing": confusing_text(confusing_colors(mapper, rows)),
        "material": material_advice(total_beads, rows),
        "tips": "拼完检查: 先用图纸对比一遍再熨烫；熨烫时烘焙布垫底，正反各30秒",
    }
