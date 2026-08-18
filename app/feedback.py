# -*- coding: utf-8 -*-
"""反馈学习闭环：客户反馈记录 → 经验库 → 相似订单自动带出建议
- 每个订单可记录: 满意/不满意 + 原因分类 + 详情 + 调整动作 + 经验教训
- 经验按 风格/档位/主题/色卡 打标签，生成新订单时检索相似历史，输出建议
"""
import json
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK_FILE = os.path.join(BASE_DIR, "feedback.json")

REASONS = ["颜色不对", "风格不像", "图纸太小看不清", "细节丢失", "色号对不上材料", "其他"]

def _load():
    if not os.path.exists(FEEDBACK_FILE):
        return {"feedbacks": []}
    try:
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"feedbacks": []}

def _save(data):
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_feedback(order_id, satisfied, reason="", detail="", action="", lesson="", meta=None):
    """记录一条反馈。meta 应含 order 的 style/tier/subject/colorcard/grid 等"""
    data = _load()
    fb = {
        "id": f"fb_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "order_id": order_id,
        "created": datetime.now().isoformat(),
        "satisfied": bool(satisfied),
        "reason": reason if reason in REASONS else "其他",
        "detail": detail,
        "action": action,
        "lesson": lesson,
        "meta": meta or {},
    }
    data["feedbacks"].append(fb)
    _save(data)
    return fb

def list_feedbacks(limit=50):
    data = _load()
    return list(reversed(data["feedbacks"]))[:limit]

def stats():
    """统计: 不满意率、按原因分布、按风格分布"""
    data = _load()
    fbs = data["feedbacks"]
    total = len(fbs)
    if total == 0:
        return {"total": 0, "unsatisfied_rate": 0, "by_reason": {}, "by_style": {}}
    unsatisfied = [f for f in fbs if not f["satisfied"]]
    by_reason = {}
    by_style = {}
    for f in fbs:
        if not f["satisfied"]:
            r = f.get("reason", "其他")
            by_reason[r] = by_reason.get(r, 0) + 1
        st = (f.get("meta") or {}).get("style", "未知")
        by_style[st] = by_style.get(st, 0) + 1
    return {
        "total": total,
        "unsatisfied_rate": round(len(unsatisfied) / total * 100, 1),
        "unsatisfied_count": len(unsatisfied),
        "by_reason": by_reason,
        "by_style": by_style,
    }

def get_lessons_for(style=None, tier=None, subject=None, colorcard=None, min_hits=1):
    """检索相似历史经验：按 style 为主键，返回可参考的建议列表"""
    data = _load()
    hits = []
    for f in data["feedbacks"]:
        if f["satisfied"]:
            continue  # 只参考不满意的案例
        m = f.get("meta") or {}
        score = 0
        if style and m.get("style") == style:
            score += 3
        if tier and m.get("tier") == tier:
            score += 1
        if colorcard and m.get("colorcard") == colorcard:
            score += 1
        if subject and subject and m.get("subject") == subject:
            score += 2
        if score >= min_hits:
            hits.append({**f, "score": score})
    hits.sort(key=lambda x: -x["score"])
    return hits

# 风格健康度评级（按不满意率自动分级）
HEALTH_GOOD = 0.25      # 不满意率 < 25%: 正常推荐
HEALTH_CAUTION = 0.5    # 25%-50%: 需谨慎
HEALTH_BAD = 1.01       # >50%: 降级/建议下架

def style_health(min_samples=2):
    """按风格统计健康度: 返回 {style_id: {count, unsatisfied_rate, level, level_label, top_reason}}
    level: good / caution / bad
    - good: 样本足够且不满意率低 → 正常推荐
    - caution: 不满意率中等 → 标记"需谨慎"
    - bad: 不满意率高 → 标记"降级推荐"（前端置灰/靠后）
    - 样本不足(< min_samples): 标记 "insufficient"（不评级，避免误判）
    """
    data = _load()
    fbs = data["feedbacks"]
    by_style = {}
    for f in fbs:
        st = (f.get("meta") or {}).get("style", "未知")
        if st == "未知":
            continue
        s = by_style.setdefault(st, {"count": 0, "unsatisfied": 0, "reasons": {}})
        s["count"] += 1
        if not f["satisfied"]:
            s["unsatisfied"] += 1
            r = f.get("reason", "其他")
            s["reasons"][r] = s["reasons"].get(r, 0) + 1
    result = {}
    for st, s in by_style.items():
        rate = s["unsatisfied"] / s["count"] if s["count"] else 0
        if s["count"] < min_samples:
            level, label = "insufficient", "样本不足"
        elif rate < HEALTH_GOOD:
            level, label = "good", "正常推荐"
        elif rate < HEALTH_CAUTION:
            level, label = "caution", "需谨慎"
        else:
            level, label = "bad", "降级推荐"
        top_reason = max(s["reasons"], key=s["reasons"].get) if s["reasons"] else ""
        result[st] = {
            "count": s["count"],
            "unsatisfied_rate": round(rate * 100, 1),
            "level": level,
            "label": label,
            "top_reason": top_reason,
        }
    return result

def summarize_lessons(hits):
    """把命中经验聚合成可读建议"""
    if not hits:
        return None
    lessons = [h.get("lesson", "") for h in hits if h.get("lesson")]
    actions = [h.get("action", "") for h in hits if h.get("action")]
    reasons = {}
    for h in hits:
        r = h.get("reason", "其他")
        reasons[r] = reasons.get(r, 0) + 1
    top_reason = max(reasons, key=reasons.get) if reasons else ""
    return {
        "hit_count": len(hits),
        "top_reason": top_reason,
        "top_reason_count": reasons.get(top_reason, 0),
        "lessons": lessons[:3],
        "actions": actions[:3],
        "related_orders": [h.get("order_id") for h in hits[:3]],
    }
