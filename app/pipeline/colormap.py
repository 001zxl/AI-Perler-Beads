# -*- coding: utf-8 -*-
"""色卡映射引擎：任意 RGB → 品牌色卡最近色（ΔE2000 色差）+ 风格色板加权"""
import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def rgb_to_lab(rgb):
    """sRGB → CIELAB"""
    r, g, b = [x / 255.0 for x in rgb]
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722) / 1.0
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
    def f(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t + 16 / 116)
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))

def delta_e2000(lab1, lab2):
    """CIEDE2000 色差公式"""
    L1, a1, b1 = lab1
    L2, a2, b2 = lab2
    C1 = math.sqrt(a1**2 + b1**2)
    C2 = math.sqrt(a2**2 + b2**2)
    Cbar = (C1 + C2) / 2
    G = 0.5 * (1 - math.sqrt(Cbar**7 / (Cbar**7 + 25**7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = math.sqrt(a1p**2 + b1**2)
    C2p = math.sqrt(a2p**2 + b2**2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dhp = 0
    if C1p * C2p != 0:
        d = h2p - h1p
        dhp = d if abs(d) <= 180 else (d - 360 if d > 180 else d + 360)
    dHp = 2 * math.sqrt(C1p * C2p) * math.sin(math.radians(dhp) / 2)
    Lbarp = (L1 + L2) / 2
    Cbarp = (C1p + C2p) / 2
    hbarp = (h1p + h2p) / 2
    if C1p * C2p != 0:
        if abs(h1p - h2p) > 180:
            hbarp = (h1p + h2p + 360) / 2 if h1p + h2p < 360 else (h1p + h2p - 360) / 2
        else:
            hbarp = (h1p + h2p) / 2
    T = (1 - 0.17 * math.cos(math.radians(hbarp - 30))
         + 0.24 * math.cos(math.radians(2 * hbarp))
         + 0.32 * math.cos(math.radians(3 * hbarp + 6))
         - 0.20 * math.cos(math.radians(4 * hbarp - 63)))
    dtheta = 30 * math.exp(-((hbarp - 275) / 25) ** 2)
    RC = 2 * math.sqrt(Cbarp**7 / (Cbarp**7 + 25**7))
    SL = 1 + (0.015 * (Lbarp - 50) ** 2) / math.sqrt(20 + (Lbarp - 50) ** 2)
    SC = 1 + 0.045 * Cbarp
    SH = 1 + 0.015 * Cbarp * T
    RT = -math.sin(math.radians(2 * dtheta)) * RC
    dE = math.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2
                   + RT * (dCp / SC) * (dHp / SH))
    return dE

def rgb_to_oklab(rgb):
    """sRGB → Oklab（感知均匀色彩空间，Zippland/perler-beads 采用）"""
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(rgb[0] / 255), lin(rgb[1] / 255), lin(rgb[2] / 255)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = l ** (1/3), m ** (1/3), s ** (1/3)
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )

def delta_e_oklab(lab1, lab2):
    """Oklab 欧氏距离（×100 与阈值兼容）"""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(lab1, lab2))) * 100

class OklabColorMapper:
    """Oklab 色卡映射器（视觉更准，替代 ΔE2000）"""
    def __init__(self, card_id="mard", palette_bias="standard"):
        card = config.get_colorcard(card_id)
        if not card:
            raise ValueError(f"未知色卡: {card_id}")
        self.card_id = card_id
        self.brand = card["brand"]
        self.colors = card["colors"]
        self._lab_cache = {code: rgb_to_oklab(c["rgb"]) for code, c in self.colors.items()}
        self.bias = _PALETTE_BIAS.get(palette_bias, {})
        self._grid_cache = {}

    BLACK_CODE = None  # 延迟查找
    DARK_THRESHOLD = 45  # 接近黑的阈值（亮度）

    def _find_black_code(self):
        if self.BLACK_CODE is not None and self.BLACK_CODE in self.colors:
            return self.BLACK_CODE
        # 找色卡中最黑的颜色
        best, best_v = None, 999
        for code, c in self.colors.items():
            v = sum(c["rgb"])
            if v < best_v:
                best_v, best = v, code
        self.BLACK_CODE = best
        return best

    def nearest(self, rgb, suppress_black=True):
        """最近色匹配。
        suppress_black=True: 抑制过度映射到纯黑（解决眼睛被压黑）。
        如果原色是深棕/深灰（非纯黑），优先映射到相近深色而非纯黑。"""
        lab = rgb_to_oklab(rgb)
        # 黑色抑制：若原色是"接近黑但不是纯黑"（如深棕 40,30,20），
        # 在候选集中排除纯黑，让它映射到深棕/深灰
        black_code = self._find_black_code()
        black_rgb = self.colors[black_code]["rgb"]
        is_near_black = sum(rgb) < 150  # 亮度很低
        is_pure_black = sum(rgb) < 40   # 接近纯黑

        best_code, best_dE = None, float("inf")
        for code, clab in self._lab_cache.items():
            if self.bias:
                crgb = self.colors[code]["rgb"]
                if not _passes_bias(crgb, self.bias):
                    continue
            # 黑色抑制核心：深棕/深灰（非纯黑）不映射到纯黑
            if suppress_black and is_near_black and not is_pure_black:
                if code == black_code:
                    continue
            dE = delta_e_oklab(lab, clab)
            if dE < best_dE:
                best_dE, best_code = dE, code
        if best_code is None:  # 全被抑制（极端情况）
            best_code = black_code
        c = self.colors[best_code]
        return best_code, c["name"], best_dE

    def lookup(self, rgb):
        """带缓存查询: rgb → (code, name, orig_rgb, de)"""
        if rgb not in self._grid_cache:
            code, name, de = self.nearest(rgb)
            self._grid_cache[rgb] = (code, name, self.colors[code]["rgb"], de)
        return self._grid_cache[rgb]

# 风格色板倾向 → 候选色加权（抑制不协调色）
_PALETTE_BIAS = {
    "standard": {},          # 无偏置
    "pastel": {              # 马卡龙：偏向浅色柔和色
        "brightness": (0.55, 0.9),
    },
    "vivid": {               # 8-bit：偏向高饱和
        "saturation_min": 0.5,
    },
    "minimal": {             # 极简：偏向低彩度/黑白
        "saturation_max": 0.35,
    },
    "neon": {                # 霓虹：偏向高亮高饱和
        "saturation_min": 0.7,
        "brightness": (0.6, 1.0),
    },
    "pop": {"saturation_min": 0.55},
    "crayon": {},
    "soft": {"saturation_max": 0.6},
    "festive": {
        "warm_red_green": True,
    },
    "mono": {"saturation_max": 0.15},
}

def _hsv(rgb):
    r, g, b = [x / 255.0 for x in rgb]
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    h = 0
    if d > 0:
        if mx == r:
            h = ((g - b) / d) % 6
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h *= 60
    s = 0 if mx == 0 else d / mx
    return h, s, mx

def _passes_bias(rgb, bias):
    h, s, v = _hsv(rgb)
    if "saturation_min" in bias and s < bias["saturation_min"]:
        return False
    if "saturation_max" in bias and s > bias["saturation_max"]:
        return False
    if "brightness" in bias:
        lo, hi = bias["brightness"]
        if not (lo <= v <= hi):
            return False
    return True

class ColorMapper:
    """色卡映射器：缓存 LAB，支持风格加权"""
    def __init__(self, card_id="mard", palette_bias="standard"):
        card = config.get_colorcard(card_id)
        if not card:
            raise ValueError(f"未知色卡: {card_id}")
        self.card_id = card_id
        self.brand = card["brand"]
        self.colors = card["colors"]  # {code: {name, rgb}}
        self._lab_cache = {code: rgb_to_lab(c["rgb"]) for code, c in self.colors.items()}
        self.bias = _PALETTE_BIAS.get(palette_bias, {})

    def nearest(self, rgb):
        """返回 (色号, 色名, ΔE)"""
        lab = rgb_to_lab(rgb)
        best_code, best_dE = None, float("inf")
        for code, clab in self._lab_cache.items():
            if self.bias:
                crgb = self.colors[code]["rgb"]
                if not _passes_bias(crgb, self.bias):
                    continue
            dE = delta_e2000(lab, clab)
            if dE < best_dE:
                best_dE, best_code = dE, code
        c = self.colors[best_code]
        return best_code, c["name"], best_dE

    def map_grid(self, grid_rgb_list):
        """批量映射: [(r,g,b),...] → [(code, name, rgb, dE),...]"""
        return [self.nearest(rgb) + (self.colors[self.nearest(rgb)[0]]["rgb"],) for rgb in grid_rgb_list]
