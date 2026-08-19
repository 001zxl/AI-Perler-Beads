# -*- coding: utf-8 -*-
"""可拼性评分 + 图纸信息卡
评分维度: 颜色数/孤立点/连续区域/尺寸/预计耗时
信息卡: 尺寸/颗数/每色颗数/板数/建议豆径
"""
import math

# 拼豆板规格（2.6mm mini 豆常用 29x29 板；5mm 豆用 10x10 或 20x20）
BOARD_SPECS = {
    "2.6mm": {"cols": 29, "rows": 29, "name": "mini 拼豆板 29x29"},
    "5mm": {"cols": 20, "rows": 20, "name": "标准拼豆板 20x20"},
}

# 拼豆速度参考（颗/分钟，新手/熟练）
BEAD_SPEED = {"新手": 15, "熟练": 30}

def score_pattern(grid_rgb, width, height, max_colors):
    """可拼性评分 0-100
    维度: 色数(30%) + 孤立点(30%) + 连续区域(20%) + 尺寸(20%)
    """
    n = len(grid_rgb)
    from collections import Counter
    colors = Counter(grid_rgb)
    color_count = len(colors)

    # 色数分: 越少越高（但太少的相似度低，取 8-16 最优）
    if color_count <= 8:
        color_score = 90
    elif color_count <= 12:
        color_score = 85
    elif color_count <= 16:
        color_score = 75
    elif color_count <= 24:
        color_score = 60
    else:
        color_score = 40

    # 孤立点检测（被3个不同色包围）
    isolated = 0
    for y in range(height):
        for x in range(width):
            i = y * width + x
            c = grid_rgb[i]
            nb = set()
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = y+dy, x+dx
                if 0 <= ny < height and 0 <= nx < width:
                    nb.add(grid_rgb[ny*width+nx])
            if len(nb) >= 3 and all(n != c for n in nb):
                isolated += 1
    iso_ratio = isolated / n if n else 0
    iso_score = max(0, 100 - iso_ratio * 1500)  # 1% 孤立点 = 15 分扣

    # 连续区域（同色连通块数量）——越少越好（大色块）
    visited = set()
    regions = 0
    for i in range(n):
        if i in visited:
            continue
        color = grid_rgb[i]
        stack = [i]
        regions += 1
        while stack:
            ci = stack.pop()
            if ci in visited or grid_rgb[ci] != color:
                continue
            visited.add(ci)
            r, c = divmod(ci, width)
            for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
                nr, nc = r+dr, c+dc
                if 0 <= nr < height and 0 <= nc < width:
                    stack.append(nr*width+nc)
    region_ratio = regions / n if n else 1
    region_score = max(0, 100 - region_ratio * 800)  # 每个格 0.8 分扣

    # 尺寸分: 越大越好（但超过 60x60 拼起来累）
    total = width * height
    if total <= 900:      # <=30x30
        size_score = 60
    elif total <= 3600:   # <=60x60
        size_score = 85
    elif total <= 10000:  # <=100x100
        size_score = 70
    else:
        size_score = 50

    total_score = int(color_score * 0.3 + iso_score * 0.3 + region_score * 0.2 + size_score * 0.2)
    return {
        "score": int(total_score),
        "color_count": int(color_count),
        "isolated_pixels": int(isolated),
        "isolated_ratio": round(float(iso_ratio) * 100, 1),
        "regions": int(regions),
        "width": int(width), "height": int(height),
        "total_beads": int(total),
        "verdict": "非常好拼" if total_score >= 85 else ("好拼" if total_score >= 70 else ("中等" if total_score >= 55 else "难拼")),
    }

def pattern_info(grid_rgb, width, height, bead_size="2.6mm", difficulty="标准"):
    """图纸信息卡: 尺寸/颗数/每色颗数/板数/预计耗时/建议豆径"""
    from collections import Counter
    colors = Counter(grid_rgb)
    total = len(grid_rgb)

    board = BOARD_SPECS.get(bead_size, BOARD_SPECS["2.6mm"])
    # 板数估算
    boards_x = math.ceil(width / board["cols"])
    boards_y = math.ceil(height / board["rows"])
    boards = boards_x * boards_y

    speed = BEAD_SPEED.get(difficulty, 20)
    est_minutes = math.ceil(total / speed)

    color_rows = []
    for (rgb, count) in colors.most_common():
        color_rows.append({"rgb": [int(v) for v in rgb], "count": int(count)})

    return {
        "size": f"{width}x{height} 格",
        "bead_size": bead_size,
        "total_beads": total,
        "board_count": boards,
        "board_spec": board["name"],
        "est_minutes": est_minutes,
        "difficulty": difficulty,
        "color_breakdown": color_rows,
    }

def info_card_text(info, brand="Mard"):
    """生成信息卡文本（供施工图底部/交付说明用）"""
    lines = [
        f"【图纸信息】",
        f"尺寸: {info['size']} | 豆径: {info['bead_size']}",
        f"总颗数: {info['total_beads']} 颗",
        f"需要拼豆板: {info['board_count']} 块 ({info['board_spec']})",
        f"预计耗时: 约 {info['est_minutes']} 分钟（{info['difficulty']}难度）",
        f"参考色卡: {brand}",
    ]
    return "\n".join(lines)

def diagnostic_report(grid_rgb, width, height, max_colors, face_regions=None):
    """图纸诊断报告（核心卖点）: 清晰度/孤立点/色数/五官保留/可拼性/返工点
    返回结构化诊断 + 可读文本
    """
    import numpy as np
    from collections import Counter
    n = len(grid_rgb)
    colors = Counter(grid_rgb)
    color_count = len(colors)

    # 1. 清晰度: 色块纯净度（孤立点比例）
    isolated = 0
    for y in range(height):
        for x in range(width):
            i = y * width + x
            c = grid_rgb[i]
            nb = set()
            for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
                ny, nx = y+dy, x+dx
                if 0 <= ny < height and 0 <= nx < width:
                    nb.add(grid_rgb[ny*width+nx])
            if len(nb) >= 3 and all(n != c for n in nb):
                isolated += 1
    iso_ratio = isolated / n if n else 0
    clarity = "清晰" if iso_ratio < 0.01 else ("基本清晰" if iso_ratio < 0.03 else "偏碎需清理")

    # 2. 色数评估
    if color_count <= 8:
        color_eval = "少(好拼)"
    elif color_count <= 12:
        color_eval = "适中(推荐)"
    elif color_count <= 18:
        color_eval = "多(精细)"
    else:
        color_eval = "过多(费材料)"

    # 3. 五官保留（若有面部区域）
    face_score = None
    if face_regions and face_regions.get("eyes"):
        # 检查眼睛区域是否有深色瞳孔格
        eye_dark = 0
        eye_total = 0
        for (x0, y0, x1, y1) in face_regions["eyes"]:
            for y in range(max(0,y0), min(height,y1)):
                for x in range(max(0,x0), min(width,x1)):
                    i = y*width+x
                    eye_total += 1
                    if sum(grid_rgb[i]) < 200:  # 深色=瞳孔/高光轮廓
                        eye_dark += 1
        if eye_total > 0:
            face_score = "保留" if eye_dark > 0 else "可能丢失"
        else:
            face_score = "区域未覆盖"

    # 4. 连续区域（大色块比例）
    visited = set()
    big_blocks = 0
    for i in range(n):
        if i in visited:
            continue
        color = grid_rgb[i]
        stack = [i]
        size = 0
        while stack:
            ci = stack.pop()
            if ci in visited or grid_rgb[ci] != color:
                continue
            visited.add(ci)
            size += 1
            r, c = divmod(ci, width)
            for dr, dc in ((1,0),(-1,0),(0,1),(0,-1)):
                nr, nc = r+dr, c+dc
                if 0 <= nr < height and 0 <= nc < width:
                    stack.append(nr*width+nc)
        if size >= 4:  # 大色块 >= 2x2
            big_blocks += 1
    big_ratio = big_blocks / n if n else 0

    # 5. 可拼性总分
    sc = score_pattern(grid_rgb, width, height, max_colors)

    # 6. 返工点（预计问题）
    rework = []
    if iso_ratio > 0.02:
        rework.append(f"孤立点 {isolated} 个可能显脏")
    if color_count > 18:
        rework.append(f"颜色 {color_count} 种偏多，找色费时")
    if face_score == "可能丢失":
        rework.append("眼睛/五官可能不清晰")
    if big_ratio < 0.05:
        rework.append("大色块少，拼起来碎")

    report = {
        "clarity": clarity,
        "isolated_pixels": isolated,
        "isolated_ratio": round(iso_ratio * 100, 1),
        "color_count": color_count,
        "color_eval": color_eval,
        "face_preserved": face_score,
        "big_blocks": big_blocks,
        "big_ratio": round(big_ratio * 100, 1),
        "scorability": sc,
        "rework_points": rework,
    }
    return report

def diagnostic_text(report):
    """诊断报告文本（交付/展示用）"""
    sc = report["scorability"]
    lines = [
        "【图纸诊断报告】",
        f"• 可拼性评分: {sc['score']}/100（{sc['verdict']}）",
        f"• 清晰度: {report['clarity']}（孤立点 {report['isolated_pixels']} 个 / {report['isolated_ratio']}%）",
        f"• 色数: {report['color_count']} 色（{report['color_eval']}）",
        f"• 五官保留: {report['face_preserved'] or 'N/A'}",
        f"• 大色块: {report['big_blocks']} 块（{report['big_ratio']}%）",
    ]
    if report["rework_points"]:
        lines.append(f"• 可能返工点: {'；'.join(report['rework_points'])}")
    else:
        lines.append("• 可能返工点: 无，图纸质量良好")
    return "\n".join(lines)
