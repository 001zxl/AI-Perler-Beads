# -*- coding: utf-8 -*-
"""拼豆工坊单元测试：量化/色卡映射/统计 断言"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "pipeline"))

from PIL import Image
import numpy as np

def test_quantize_grid():
    from quantize import quantize_grid, color_counts
    img = Image.new("RGB", (200, 100), (255, 0, 0))
    g, w, h = quantize_grid(img, 30, "auto", 16)
    assert w == 30 and h == 15, f"宽高比错误: {w}x{h}"
    assert len(g) == 450, f"网格总数错误: {len(g)}"
    assert len(set(g)) == 1, "纯色图应只有 1 色"
    cc = color_counts(g)
    assert sum(cc.values()) == 450, "豆量总和必须等于格数"
    print("✅ test_quantize_grid")

def test_colormap_nearest():
    from colormap import ColorMapper
    m = ColorMapper("mard", "standard")
    code, name, de = m.nearest((255, 255, 255))
    # 291 色完整色卡下纯白映射到 T01（真实 Mard 白色号）
    assert code in ("T01", "A01", "A02"), f"白色映射异常: {code}"
    code, name, de = m.nearest((255, 0, 0))
    # 291 色卡红色色号 A14（真实 Mard 红），校验映射色是红色系
    from colormap import ColorMapper as CM
    _card = CM("mard", "standard")
    rgb = _card.colors[code]["rgb"]
    assert rgb[0] > 150 and rgb[1] < 100 and rgb[2] < 100, f"红色映射错误: {code} {rgb}"
    print("✅ test_colormap_nearest")

def test_mono_palette_bias():
    from colormap import ColorMapper
    m = ColorMapper("mard", "mono")
    code, name, de = m.nearest((255, 0, 0))  # 纯红在 mono 偏置下应映射到灰色系
    assert "红" not in name and "粉" not in name, f"mono 偏置失效: {code} {name}"
    print(f"✅ test_mono_palette_bias (纯红→{code} {name})")

def test_stats_csv():
    from quantize import quantize_grid
    from colormap import ColorMapper
    from stats import compute_stats, write_shopping_csv
    import tempfile, csv
    img = Image.new("RGB", (100, 100), (0, 0, 255))
    g, w, h = quantize_grid(img, 10, 10, 16)
    m = ColorMapper("mard", "standard")
    rows, total = compute_stats(g, m)
    assert total == 100, f"总豆数错误: {total}"
    assert sum(r["count"] for r in rows) == 100
    tmp = os.path.join(tempfile.gettempdir(), "test_shopping.csv")
    write_shopping_csv(rows, total, w, h, m.brand, tmp)
    with open(tmp, encoding="utf-8-sig") as f:
        rd = list(csv.reader(f))
    assert rd[0][0] == "色号", "CSV 表头错误"
    print("✅ test_stats_csv")

def test_render_adaptive():
    from quantize import quantize_grid
    from colormap import ColorMapper
    from render import render_construction_sheet
    # 深色图纸（霓虹）：验证不报错且能输出
    dark = Image.new("RGB", (100, 100), (10, 10, 30))
    g, w, h = quantize_grid(dark, 20, 20, 8)
    m = ColorMapper("mard", "neon")
    sheet = render_construction_sheet(g, w, h, m, title="深色测试")
    assert sheet.size[0] > 500
    print("✅ test_render_adaptive (深色图纸渲染)")

def test_pet_quality_floor():
    from type_aware import TYPE_STRATEGIES
    pet = TYPE_STRATEGIES["宠物"]
    assert pet["recommended_width"] >= 120, "宠物默认宽度不能退回低清规格"
    assert pet["min_width"] >= 100, "宠物最低宽度不能低于 100 格"
    assert pet["max_colors_default"] >= 36, "宠物默认色数不能退回低色数"
    assert pet["min_colors"] >= 32, "宠物最低色数不能低于 32"
    print("✅ test_pet_quality_floor")

def test_feature_aware_quantize_keeps_dark_detail():
    from quantize import global_quantize
    grid = (
        [(250, 205, 215)] * 420
        + [(248, 225, 205)] * 360
        + [(232, 180, 150)] * 180
        + [(22, 20, 19)] * 9
        + [(170, 72, 92)] * 18
    )
    reduced = global_quantize(grid, 5)
    assert any(max(c) < 45 for c in set(reduced)), "深色眼睛/鼻口特征不能被减色吞掉"
    assert len(set(reduced)) <= 5, "全局减色必须遵守色数上限"
    print("✅ test_feature_aware_quantize_keeps_dark_detail")

def test_photo_detail_ignores_large_shadow():
    from pipeline.photo_detail import restore_photo_details
    img = Image.new("RGB", (40, 40), (245, 205, 215))
    px = img.load()
    for x in range(4, 36):
        for y in range(31, 36):
            px[x, y] = (65, 38, 28)
    for x in range(12, 15):
        for y in range(13, 16):
            px[x, y] = (12, 10, 10)
    grid = [(245, 205, 215)] * (40 * 40)
    out = restore_photo_details(grid, img, 40, 40, img_type="宠物")
    changed = sum(1 for before, after in zip(grid, out) if before != after)
    assert 4 <= changed <= 80, f"只应回填小面积关键点，不能污染大面积阴影: changed={changed}"
    print("✅ test_photo_detail_ignores_large_shadow")

if __name__ == "__main__":
    test_quantize_grid()
    test_colormap_nearest()
    test_mono_palette_bias()
    test_stats_csv()
    test_render_adaptive()
    test_pet_quality_floor()
    test_feature_aware_quantize_keeps_dark_detail()
    test_photo_detail_ignores_large_shadow()
    print("\n🎉 全部单元测试通过")
