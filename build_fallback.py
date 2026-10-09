#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成前端离线兜底数据 web/fallback.js

用途：后端没启动时，前端仍能完整浏览。改了 config/ 或 kb/ 之后跑一次即可。

    python3 build_fallback.py            # 离线模板数据（快，几秒）
    python3 build_fallback.py --live     # 额外抓一次真实在线数据并烘进去（约 40 秒）

--live 模式会把**真实抓取到的信号**烘进兜底数据，
这样即使后端没启动，打开页面也能看到真实数据（而不是只有模板）。

关键实现：在线数据**只抓一次**，然后深拷贝复用到所有「城市 × 基金」组合，
避免为 12 个组合重复请求外部数据源。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine  # noqa
import datasources  # noqa

INDUSTRY = "具身智能机器人"
DAYS = 730
LIMIT = 60


def main():
    live = "--live" in sys.argv
    base = os.path.dirname(os.path.abspath(__file__))
    opts = engine.list_options()

    out = {"options": opts, "cities": {}, "runs": {}, "generated": None,
           "mode": "在线抓取 + 内置库" if live else "离线模板模式（M1）"}

    # ---- 在线数据只抓一次，复用给所有组合 ----
    live_records = None
    if live:
        print("正在抓取在线数据（约 40 秒）…")
        cfg = engine.load_all_config()
        _, icfg = engine.match_industry(cfg["industries"], INDUSTRY)
        terms = engine._industry_terms(icfg)
        iwords = engine._industry_words(icfg)
        recs, log = datasources.fetch_expansion_signals(
            terms, days=DAYS, limit=LIMIT, industry_words=iwords)
        live_records = (recs, log)
        print(f"  抓取完成：{len(recs)} 条")
        for l in log:
            print(f"    [{l['证据等级']}] {l['数据源']} —— {l['状态']}")

    # ---- 城市 × 基金（含「不指定基金」这一档）----
    funds = [""] + list(opts["funds"])
    for city in opts["cities"]:
        for fund in funds:
            res = engine.run(city, INDUSTRY, fund or None, "deep",
                             live_days=DAYS, live_limit=LIMIT,
                             live_records=live_records)
            # 城市配置同时保留在 run 内与 cities 表里 —— run 内自包含，避免前端补丁出错
            out["cities"][city] = res["cityCfg"]
            res.pop("industryCfg", None)
            res.pop("fundCfg", None)
            out["runs"][f"{city}||{fund}"] = res

    out["generated"] = next(iter(out["runs"].values()))["meta"]["generated_at"]
    sources = datasources.describe_all()

    js = (
        "window.FALLBACK = "
        + json.dumps(out, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
        + "window.FALLBACK_SOURCES = "
        + json.dumps(sources, ensure_ascii=False, separators=(",", ":"))
        + ";\n"
    )
    fp = os.path.join(base, "web", "fallback.js")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(js)

    print(f"\n已生成 web/fallback.js（{out['mode']}）")
    print(f"  城市×基金组合：{len(out['runs'])}")
    print(f"  数据源：{len(sources)} 个")
    print(f"  大小：{len(js.encode('utf-8')) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
