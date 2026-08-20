# -*- coding: utf-8 -*-
"""S9 交付打包：每客户一文件夹，zip 交付包 + 归档"""
import os
import zipfile
import shutil
import json
from datetime import datetime

def make_order_dir(orders_root, order_id):
    d = os.path.join(orders_root, order_id)
    for sub in ["source", "intermediate", "delivery", "archive"]:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d

def save_meta(order_dir, meta_dict):
    with open(os.path.join(order_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta_dict, f, ensure_ascii=False, indent=2)

def zip_delivery(order_dir, delivery_dir, order_id):
    """把 delivery/ 打包成 {order_id}_交付包.zip，放 archive/"""
    zip_path = os.path.join(order_dir, "archive", f"{order_id}_交付包.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(delivery_dir):
            for fn in files:
                full = os.path.join(root, fn)
                arc = os.path.relpath(full, delivery_dir)
                zf.write(full, arc)
    return zip_path

def new_order_id():
    import random
    return datetime.now().strftime("order_%Y%m%d_%H%M%S") + f"_{random.randint(100,999)}"
