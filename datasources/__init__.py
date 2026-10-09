#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源适配层

用法：
    from datasources import registry, fetch_expansion_signals

    recs, status = fetch_expansion_signals(["机器人", "减速器"], days=180)
"""
from .base import DataSource, CompanyRecord, make_record
from .registry import all_sources, active_sources, describe_all


def fetch_expansion_signals(terms, days=180, limit=30, sources=None, industry_words=None):
    """
    从所有可用数据源抓取扩张信号，合并去重。

    :param sources: 指定数据源列表（不传则用全部已接入的源）。
                    用于按「检索深度」控制抓取范围。
    :return: (records, log) —— 记录列表 + 每个源的状态说明
    """
    records, log = [], []
    for src in (sources if sources is not None else active_sources()):
        try:
            recs, status = src.search(terms, days=days, limit=limit,
                                      industry_words=industry_words)
        except TypeError:
            # 兼容未声明 industry_words 的旧数据源
            try:
                recs, status = src.search(terms, days=days, limit=limit)
            except Exception as e:
                recs, status = [], f"{type(e).__name__}: {e}"
        except Exception as e:
            recs, status = [], f"{type(e).__name__}: {e}"
        log.append({"数据源": src.name, "证据等级": src.evidence,
                    "返回条数": len(recs), "状态": status})
        records.extend(recs)

    # 去重键：企业名 > 证券代码 > 信号标题（标题兜底，避免匿名记录被合并掉）
    best = {}
    for r in records:
        key = r.get("名称") or r.get("证券代码") or r.get("扩张信号")
        if not key:
            continue
        cur = best.get(key)
        if not cur or _rank(r.get("证据等级")) > _rank(cur.get("证据等级")):
            best[key] = r
    return list(best.values()), log


def sources_by_name(names):
    """按名称挑选数据源（用于按检索深度控制抓取范围）"""
    if not names:
        return active_sources()
    want = set(names)
    return [s for s in active_sources() if s.name in want]


def _rank(lvl):
    return {"A": 4, "B": 3, "C": 2, "D": 1}.get((lvl or "").upper(), 0)


__all__ = [
    "DataSource", "CompanyRecord", "make_record",
    "all_sources", "active_sources", "describe_all", "fetch_expansion_signals",
    "sources_by_name",
]
