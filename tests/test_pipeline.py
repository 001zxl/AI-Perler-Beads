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
    assert code == "A01", f"白色应映射 A01, got {code}"
    code, name, de = m.nearest((255, 0, 0))
    assert name == "红" or "红" in name, f"红色映射错误: {code} {name}"
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

if __name__ == "__main__":
    test_quantize_grid()
    test_colormap_nearest()
    test_mono_palette_bias()
    test_stats_csv()
    test_render_adaptive()
    print("\n🎉 全部单元测试通过")
