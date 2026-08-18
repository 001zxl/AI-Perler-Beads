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
