# -*- coding: utf-8 -*-
"""S8 AI 质检：视觉模型检查施工图（网格完整/每格单色/色号标注/风格一致），不合格返回原因"""
import subprocess
import json

QC_PROMPT = (
    "这是一张AI生成的拼豆像素底图（将用于制作拼豆施工图纸）。"
    "请严格检查以下四项，逐项回答 通过/不通过 并给出理由，最后一行输出 JSON: "
    "{\"pixel_ok\": true/false, \"mono_ok\": true/false, \"detail_ok\": true/false, \"style_ok\": true/false, \"pass\": true/false, \"reason\": \"简述\"}。"
    "检查项: 1)pixel_ok 是否已经是像素化/块状化的拼豆风格（而非平滑照片或插画）; "
    "2)mono_ok 每个像素块是否为单一纯色、无渐变晕染; "
    "3)detail_ok 主体（脸/五官等关键细节）是否完整可辨、未被像素化破坏; "
    "4)style_ok 是否符合要求的风格（如深色霓虹/马卡龙/8bit等）。"
)

def qc_image(image_path, style_desc="", model="qwen3-vl-plus"):
    """质检 AI 像素底图（AI 可能翻车的地方）：像素化/单色/细节/风格
    注意：施工图的网格/色号/清单由代码确定性生成，无需视觉验证。
    返回 (pass, detail_dict)"""
    prompt = QC_PROMPT
    if style_desc:
        prompt = f"风格要求: {style_desc}。" + prompt
    cmd = ["bl", "vision", "describe", "--image", image_path, "--prompt", prompt, "--model", model, "--quiet"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return False, {"error": r.stderr.strip() or "质检调用失败", "raw": r.stdout[:200]}
        out = r.stdout.strip()
        content = out
        # bl --quiet 返回外层 JSON: choices[0].message.content 是文本
        try:
            outer = json.loads(out)
            content = outer["choices"][0]["message"]["content"]
        except Exception:
            pass
        # 从 content 提取内层 JSON（可能被 markdown 围栏包裹）
        import re
        # 取最后一个含 "pass" 的 JSON 对象
        m = None
        for cand in re.findall(r"\{[^{}]*\}", content, re.S):
            if '"pass"' in cand:
                m = cand
        if m is None:
            # 放宽：任意大括号块
            cands = re.findall(r"\{[^{}]*\}", content, re.S)
            m = cands[-1] if cands else None
        if m:
            try:
                data = json.loads(m)
                if "pass" in data:
                    return bool(data.get("pass")), data
            except Exception:
                pass
        return False, {"raw": content[:300], "error": "未解析出质检结果"}
    except subprocess.TimeoutExpired:
        return False, {"error": "质检超时"}
    except Exception as e:
        return False, {"error": str(e)}
