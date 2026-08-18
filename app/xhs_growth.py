# -*- coding: utf-8 -*-
"""小红书起号内容生成器（口碑+粉丝→卖图纸转化）
功能:
  1. 教程类图文包: 5步教程图 + 教程文案（植入差异化卖点）
  2. 宠物定制包: 宠物照 → 图纸 → "我家主子拼豆"内容（主打定制转化）
  3. 标题公式库: 5 套公式按内容类型自动生成
  4. 封面角标: "带色号/附清单/19风格" 差异化角标
  5. 30天内容日历: 内容类型+标题+转化目标
"""
import os
import sys
import json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from pipeline.run import run_order

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GROWTH_DIR = os.path.join(BASE_DIR, "xhs_growth")
os.makedirs(GROWTH_DIR, exist_ok=True)

# ---- 差异化卖点弹药 ----
DIFFERENTIATORS = {
    "color_map": "色号对应你买得到的豆子",
    "shopping_list": "自带采购清单，按色号直接买豆",
    "qc": "每张图纸都验过，保证能拼出来",
    "styles": "一张照片 19 种风格任选",
    "coords": "坐标+色号，新手照着拼不迷路",
    "speed": "10 分钟出图，加急 1 小时交付",
}

# ---- 标题公式库 ----
TITLE_FORMULAS = {
    "showcase": [  # 图纸展示类
        "{char}拼豆图纸 来了！色号对得上材料那种",
        "{char}拼豆图纸，自带清单照着拼就行",
        "{char}粉丝集合！19种风格任选的拼豆图纸",
    ],
    "tutorial": [  # 教程类
        "手把手教你 10 分钟把照片变成拼豆图纸",
        "新手第一次拼豆，怎么选图纸不翻车？",
        "拼豆图纸怎么看？坐标+色号保姆级教程",
    ],
    "process": [  # 过程类
        "一张照片 → 能拼出来的图纸，太治愈了",
        "原图 vs 拼豆成品，还原度你给几分？",
        "AI 出的图纸，拼出来长这样（附过程）",
    ],
    "hot": [  # 热点类
        "最近超火的{char}，连夜做了拼豆图纸",
        "{char}拼豆图纸 来了！这次带色号",
        "紧跟热点：{char}拼豆图纸 已出",
    ],
    "interact": [  # 互动类
        "拼豆新手最怕图纸拼不出来？评论区聊聊",
        "你最想让我出哪个角色的图纸？投票选",
        "拼豆第一件作品拼什么好？给点建议",
    ],
}

# ---- 教程步骤（5步） ----
TUTORIAL_STEPS = [
    ("选一张清晰照片", "正脸/全身照效果最好，模糊的图拼出来也糊"),
    ("生成拼豆图纸", "AI 自动像素化，坐标+色号+采购清单一步到位"),
    ("按清单买豆子", "色号对应能买到的豆子，不猜色不买错"),
    ("照着坐标拼", "横纵坐标定位，新手也不会拼错位置"),
    ("熨烫定型", "烘焙布+熨斗，正反各 30 秒搞定"),
]

# ---- 教程文案 ----
TUTORIAL_CAPTION = """很多人问怎么把照片变成拼豆图纸，其实超简单：
{steps}

① 选一张清晰的照片（正脸/全身效果最好）
② 用工具生成图纸（自带坐标+色号+采购清单）
③ 按清单买豆子（色号对应能买到的豆子）
④ 照着坐标拼（新手不迷路）
⑤ 熨烫定型（正反各30秒）

我这边出图是 {speed}，带 {coords}，附 {shopping_list}
需要的宝子可以私我（来图定制：宠物/情侣/全家福都能做）

#拼豆 #拼豆图纸 #教程 #手工 #DIY #手作 #新手拼豆 #图纸定制"""

# ---- 宠物定制文案 ----
PET_CAPTION = """把{pet}做成拼豆是什么体验？太治愈了💛

{pet}的照片 → 拼豆图纸 → 照着拼
图纸自带坐标+色号+采购清单，色号对应能买到的豆子
新手也能拼出来✨

做了{N}种风格：{styles}
来图定制（宠物/情侣/全家福）可以私我

#拼豆 #拼豆图纸 #宠物 #{pet_tag} #手工 #DIY #手作 #来图定制 #图纸定制"""

def generate_title(content_type, char="", extra=""):
    """按内容类型生成标题候选"""
    formulas = TITLE_FORMULAS.get(content_type, TITLE_FORMULAS["showcase"])
    return [f.format(char=char) for f in formulas]

def make_cover_with_badge(base_img_path, out_path, title, badge_text="带色号"):
    """封面加差异化角标"""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.open(base_img_path).convert("RGB")
    # 保证 3:4 封面
    W, H = 1080, 1440
    canvas = Image.new("RGB", (W, H), "white")
    pv = img.copy()
    pv.thumbnail((900, 900), Image.LANCZOS)
    canvas.paste(pv, ((W - pv.width)//2, 180))
    draw = ImageDraw.Draw(canvas)
    # 标题区
    draw.rectangle([0, 0, W, 130], fill=(232, 93, 63))
    font_big = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 42)
    font_small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 26)
    draw.text((W//2, 65), title, font=font_big, fill="white", anchor="mm")
    # 差异化角标（右上角）
    draw.rectangle([W-280, 150, W-20, 200], fill=(255, 200, 0), outline="black")
    draw.text((W-150, 175), badge_text, font=font_small, fill="black", anchor="mm")
    canvas.save(out_path)
    return out_path

def generate_tutorial_pack(out_dir=None):
    """生成教程类图文包（5步图 + 文案 + 标签）"""
    from PIL import Image, ImageDraw, ImageFont
    out_dir = out_dir or os.path.join(GROWTH_DIR, "教程_照片变拼豆图纸")
    os.makedirs(out_dir, exist_ok=True)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 36)
    font_s = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 26)
    # 5 张步骤图
    for i, (step, desc) in enumerate(TUTORIAL_STEPS, 1):
        img = Image.new("RGB", (1080, 1080), (248, 245, 240))
        draw = ImageDraw.Draw(img)
        draw.rectangle([80, 100, 1000, 300], fill=(93, 173, 226))
        draw.text((540, 200), f"第{i}步：{step}", font=font, fill="white", anchor="mm")
        draw.rectangle([80, 350, 1000, 700], fill="white", outline=(200, 200, 200))
        draw.text((540, 500), "【示意图】", font=font_s, fill=(150, 150, 150), anchor="mm")
        draw.text((540, 800), desc, font=font_s, fill=(90, 90, 90), anchor="mm")
        img.save(os.path.join(out_dir, f"步骤{i}.png"))
    # 封面（成品示例）
    make_cover_with_badge(os.path.join(BASE_DIR, "samples", "char_ref.png"),
                          os.path.join(out_dir, "0_封面.png"),
                          "把照片变成拼豆图纸", "带色号+清单")
    # 文案
    steps_txt = "\n".join(f"{i}. {s}" for i, (s, _) in enumerate(TUTORIAL_STEPS, 1))
    caption = TUTORIAL_CAPTION.format(
        steps=steps_txt,
        speed=DIFFERENTIATORS["speed"],
        coords=DIFFERENTIATORS["coords"],
        shopping_list=DIFFERENTIATORS["shopping_list"])
    with open(os.path.join(out_dir, "文案.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    with open(os.path.join(out_dir, "标签.txt"), "w", encoding="utf-8") as f:
        f.write("#拼豆 #拼豆图纸 #教程 #手工 #DIY #手作 #新手拼豆 #图纸定制")
    return {"success": True, "dir": out_dir, "titles": generate_title("tutorial")}

def generate_pet_pack(pet_image, pet_name="我家主子", styles=("classic", "chibi_pastel"), out_dir=None):
    """宠物定制包：宠物照 → 图纸 → 内容"""
    out_dir = out_dir or os.path.join(GROWTH_DIR, f"宠物_{pet_name}")
    os.makedirs(out_dir, exist_ok=True)
    # 1. 生成图纸（主力款）
    res = run_order(pet_image, tier_key="主力款", style_id=styles[0],
                    subject=pet_name, do_qc=True)
    if not res.get("success"):
        return {"success": False, "error": res.get("error", "出图失败")}
    # 2. 封面（带差异化角标）
    preview = os.path.join(res["order_dir"], "delivery", "4_成品预览.png")
    make_cover_with_badge(preview, os.path.join(out_dir, "0_封面.png"),
                          f"{pet_name} 拼豆图纸", "来图定制")
    # 3. 复制交付文件
    import shutil
    for f in os.listdir(os.path.join(res["order_dir"], "delivery")):
        shutil.copy(os.path.join(res["order_dir"], "delivery", f), out_dir)
    # 4. 文案
    pet_tag = pet_name if len(pet_name) <= 6 else "宠物"
    caption = PET_CAPTION.format(pet=pet_name, N=len(styles),
                                 styles="、".join(styles), pet_tag=pet_tag)
    with open(os.path.join(out_dir, "文案.txt"), "w", encoding="utf-8") as f:
        f.write(caption)
    return {"success": True, "dir": out_dir, "order_id": res["order_id"],
            "titles": generate_title("showcase", pet_name)}

def generate_calendar(start_date=None, weeks=4):
    """30 天内容日历"""
    start = start_date or datetime.now()
    cal = []
    plan = [
        (7, "tutorial"), (7, "showcase"), (5, "process"), (5, "hot"), (6, "interact"),
    ]
    cycle = []
    for n, t in plan:
        cycle.extend([t] * n)
    for i in range(weeks * 7):
        day = start + timedelta(days=i)
        ctype = cycle[i % len(cycle)]
        titles = generate_title(ctype)
        cal.append({
            "date": day.strftime("%Y-%m-%d"),
            "weekday": "周" + "一二三四五六日"[day.weekday()],
            "type": ctype,
            "title_candidate": titles[0],
            "goal": "立人设" if i < 14 else ("接询单" if i < 21 else "转化"),
        })
    return cal

def export_calendar_csv(path=None):
    cal = generate_calendar()
    path = path or os.path.join(BASE_DIR, "docs", "30天内容日历.csv")
    import csv
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["date", "weekday", "type", "title_candidate", "goal"])
        w.writeheader()
        for row in cal:
            w.writerow(row)
    return path

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", default="tutorial", choices=["tutorial", "pet", "calendar"])
    ap.add_argument("--image", default="", help="宠物照路径")
    ap.add_argument("--name", default="我家主子", help="宠物名")
    args = ap.parse_args()
    if args.type == "tutorial":
        r = generate_tutorial_pack()
        print("教程包:", r.get("success"), r.get("dir"))
        print("标题:", r.get("titles"))
    elif args.type == "pet":
        if not args.image:
            print("需要 --image 宠物照路径")
        else:
            r = generate_pet_pack(args.image, args.name)
            print("宠物包:", r.get("success"), r.get("dir", r.get("error", "")))
            print("标题:", r.get("titles"))
    elif args.type == "calendar":
        p = export_calendar_csv()
        print("日历导出:", p)
