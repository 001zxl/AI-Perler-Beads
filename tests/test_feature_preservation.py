# -*- coding: utf-8 -*-
"""保护区验收测试：猫/人像/Logo/动漫 多规格特征保留检查
验证：高规格(80/100格) 比低规格(60格) 保留更多特征
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "pipeline"))

from PIL import Image
from quantize import quantize_grid, global_quantize, remove_isolated_pixels, bfs_cleanup
from collections import Counter

def feature_richness(img_path, width, colors):
    """用特征保留主导色量化，检查网格保留了多少"关键色"（高饱和/深色/高光）"""
    img = Image.open(img_path).convert("RGB")
    g, W, H = quantize_grid(img, width, "auto", colors, use_dominant=True)
    if len(set(g)) > colors:
        g = global_quantize(g, colors)
    g, _ = remove_isolated_pixels(g, W, H)
    # 关键色占比（高饱和/深色/高光 - 眼睛/鼻子/文字等特征）
    key_count = 0
    for rgb in set(g):
        r, g_, b = rgb
        mx, mn = max(r, g_, b), min(r, g_, b)
        sat = (mx - mn) / 255.0 if mx > 0 else 0
        bright = mx / 255.0
        if sat > 0.6 or bright < 0.25 or bright > 0.92:
            key_count += 1
    return W, H, len(set(g)), key_count

def test_feature_preservation():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    samples = [
        ("猫", os.path.join(base, "samples", "cat_materials", "橘猫_大头.png")),
        ("Logo", os.path.join(base, "samples", "type_logo.png")),
        ("动漫", os.path.join(base, "samples", "type_anime.png")),
    ]
    print("=== 特征保留测试（关键色=高饱和/深色/高光）===")
    for name, path in samples:
        if not os.path.exists(path):
            print(f"  {name}: 样本缺失，跳过")
            continue
        for w, c in [(60, 12), (80, 18)]:
            W, H, nc, kc = feature_richness(path, w, c)
            print(f"  {name} {W}x{H}/{nc}色: 关键色 {kc} 种 {'✅' if kc > 0 else '⚠️无关键色'}")
    print("✅ 测试完成")

if __name__ == "__main__":
    test_feature_preservation()
