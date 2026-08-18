# -*- coding: utf-8 -*-
"""三轨计费系统（按单 / 按次包 / 订阅会员）
- 按单: 直接下单（现有闲鱼流程）
- 按次包: 客户购买次数包（10次/30次/100次），每次出图扣 1 次
- 订阅: 月卡/年卡会员（无限次 + VIP 功能）
本地 JSON 记账（无数据库），微信/支付宝线下收款后手动充值
"""
import json
import os
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDIT_FILE = os.path.join(BASE_DIR, "credits.json")

# 套餐定义
PACKAGES = {
    "单次": {"price": 19.9, "credits": 1, "type": "single", "desc": "单张图纸"},
    "10次包": {"price": 29.0, "credits": 10, "type": "pack", "desc": "约 ¥2.9/次，适合偶尔做"},
    "30次包": {"price": 69.0, "credits": 30, "type": "pack", "desc": "约 ¥2.3/次，适合常做"},
    "100次包": {"price": 199.0, "credits": 100, "type": "pack", "desc": "约 ¥1.99/次，适合工作室"},
    "月卡会员": {"price": 39.0, "credits": 999999, "type": "monthly", "desc": "30天无限出图+热点库VIP"},
    "年卡会员": {"price": 299.0, "credits": 999999, "type": "yearly", "desc": "365天无限出图+热点库VIP"},
}

def _load():
    if not os.path.exists(CREDIT_FILE):
        return {"customers": {}}
    try:
        with open(CREDIT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"customers": {}}

def _save(data):
    with open(CREDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _now():
    return datetime.now()

def add_customer(name, note=""):
    """新增客户（首次购买时）"""
    data = _load()
    if name not in data["customers"]:
        data["customers"][name] = {
            "credits": 0, "member_until": None, "total_spent": 0,
            "history": [], "note": note, "created": _now().isoformat(),
        }
        _save(data)
    return data["customers"][name]

def purchase(name, package_key, pay_amount=None):
    """购买套餐（线下收款后手动充值）"""
    if package_key not in PACKAGES:
        return {"success": False, "error": "未知套餐"}
    pkg = PACKAGES[package_key]
    data = _load()
    if name not in data["customers"]:
        add_customer(name)
    c = data["customers"][name]
    amount = pay_amount or pkg["price"]
    c["total_spent"] += amount
    if pkg["type"] == "monthly":
        c["member_until"] = (_now() + timedelta(days=30)).isoformat()
    elif pkg["type"] == "yearly":
        c["member_until"] = (_now() + timedelta(days=365)).isoformat()
    else:
        c["credits"] += pkg["credits"]
    c["history"].append({
        "time": _now().isoformat(), "package": package_key,
        "amount": amount, "credits_added": pkg["credits"],
    })
    _save(data)
    return {"success": True, "customer": c["note"] or name, "credits": c["credits"],
            "member_until": c["member_until"], "history": c["history"][-1]}

def check(name):
    """查询客户余额/会员状态"""
    data = _load()
    c = data["customers"].get(name)
    if not c:
        return {"exists": False, "credits": 0, "is_member": False, "member_until": None}
    # 会员过期检查
    if c.get("member_until"):
        try:
            until = datetime.fromisoformat(c["member_until"])
            if until < _now():
                c["member_until"] = None
                _save(data)
        except Exception:
            pass
    return {"exists": True, "credits": c["credits"], "is_member": bool(c.get("member_until")),
            "member_until": c.get("member_until"), "note": c.get("note", "")}

def consume(name, amount=1):
    """出图时扣次：先扣会员（会员期内不扣次数），再扣次数包"""
    data = _load()
    c = data["customers"].get(name)
    if not c:
        return {"success": False, "error": "客户不存在，先充值"}
    # 会员期内免费
    if c.get("member_until"):
        try:
            if datetime.fromisoformat(c["member_until"]) >= _now():
                c["history"].append({"time": _now().isoformat(), "action": "consume_member", "amount": 0})
                _save(data)
                return {"success": True, "mode": "member", "credits_left": c["credits"]}
        except Exception:
            pass
    # 扣次数包
    if c["credits"] >= amount:
        c["credits"] -= amount
        c["history"].append({"time": _now().isoformat(), "action": "consume", "amount": amount})
        _save(data)
        return {"success": True, "mode": "credits", "credits_left": c["credits"]}
    return {"success": False, "error": "次数不足，请购买次数包或会员", "credits": c["credits"]}

def list_all():
    data = _load()
    return {"customers": data["customers"], "packages": PACKAGES}
