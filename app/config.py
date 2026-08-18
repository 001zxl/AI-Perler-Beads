# -*- coding: utf-8 -*-
"""拼豆工坊 - 配置加载（档位/风格/色卡 JSON 驱动）"""
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORDERS_DIR = os.path.join(os.path.dirname(BASE_DIR), "orders")

def load_json(name):
    with open(os.path.join(BASE_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)

def get_tiers():
    """档位: {name: {...}}"""
    return load_json("tiers.json")

def get_styles():
    """风格: {style_id: {...}}"""
    return load_json("styles.json")

def get_colorcards():
    """色卡: {card_id: {...}}"""
    cards = {}
    for fn in os.listdir(os.path.join(BASE_DIR, "colorcards")):
        if fn.endswith(".json"):
            card_id = fn[:-5]
            cards[card_id] = load_json(os.path.join("colorcards", fn))
    return cards

def get_colorcard(card_id):
    cards = get_colorcards()
    return cards.get(card_id)

# 全局缓存
TIERS = get_tiers()
STYLES = get_styles()
COLORCARDS = get_colorcards()
