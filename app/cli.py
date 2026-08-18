# -*- coding: utf-8 -*-
"""拼豆工坊 CLI：一条命令生成交付包
示例:
  python3 -m app.cli --input photo.jpg --tier 主力款 --style chibi_pastel --qc
  python3 -m app.cli --input photo.jpg --tier 引流款 --style mono --colors 8
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
from pipeline.run import run_order

def main():
    import argparse
    ap = argparse.ArgumentParser(description="拼豆图纸生成 CLI")
    ap.add_argument("--input", required=True, help="原图路径")
    ap.add_argument("--tier", default="主力款", choices=list(config.TIERS.keys()), help="档位")
    ap.add_argument("--style", default="classic", choices=list(config.STYLES.keys()), help="风格")
    ap.add_argument("--width", type=int, default=None, help="网格宽格数(默认按档位)")
    ap.add_argument("--colors", type=int, default=None, help="最大色数")
    ap.add_argument("--colorcard", default="mard", choices=list(config.COLORCARDS.keys()), help="色卡")
    ap.add_argument("--bead", default="2.6mm", help="拼豆规格")
    ap.add_argument("--subject", default="宠物", help="主题(用于标题/文案)")
    ap.add_argument("--qc", action="store_true", help="启用 AI 质检")
    ap.add_argument("--skip-ai", action="store_true", help="跳过 AI 像素化(测试用)")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    res = run_order(args.input, tier_key=args.tier, style_id=args.style, width=args.width,
                    max_colors=args.colors, colorcard=args.colorcard, bead=args.bead,
                    subject=args.subject, do_qc=args.qc, skip_ai=args.skip_ai)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        if res["success"]:
            print(f"✅ 订单 {res['order_id']} 完成: {res['grid']} / {res['colors']}色 / {res['total']}颗")
            print(f"   交付包: {res['zip']}")
            print(f"   文件: {res['files']}")
            if res.get("qc"):
                print(f"   质检: {'✅通过' if res['qc']['passed'] else '❌未通过'} {res['qc']['detail'].get('reason','')}")
        else:
            print(f"❌ 失败 [{res.get('step')}]: {res.get('error')}")
            sys.exit(1)

if __name__ == "__main__":
    main()
