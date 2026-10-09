#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源：巨潮资讯网（cninfo.com.cn）—— 上市公司公告

为什么选它：
  上市公司「投资建设 / 扩产 / 产能」类公告是**最硬的扩张信号**，
  且属于法定信息披露，证据等级 A（官方公告），可直接引用。

接口：POST https://www.cninfo.com.cn/new/hisAnnouncement/query
  · 公开接口，无需 API Key
  · 返回 JSON，含证券代码、公司名、公告标题、日期、PDF 链接
  · 实测可用（2026-09-29 验证）

合规：巨潮资讯是深交所指定的法定信息披露平台，公告为公开信息，
     用于内部研究合规；但**请勿高频请求**（本模块默认限速 1 次/秒）。
"""
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from .base import DataSource, make_record

API = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE = "http://static.cninfo.com.cn/"

# 扩张信号词 —— 分两档，信号强度不同
SIGNAL_STRONG = ["扩产", "扩建", "新增产能", "产能建设", "投资建设", "生产基地", "投产", "新建项目", "技改"]
SIGNAL_MEDIUM = ["投资设立", "区域总部", "产业基地", "战略合作", "增资"]

# 反向过滤：这些标题虽含信号词但通常是干扰项
NOISE = ["减持", "质押", "担保", "年报", "半年报", "季度报告", "股东大会", "回购", "澄清", "风险提示"]

_EM = re.compile(r"</?em>")


def _clean(s):
    return _EM.sub("", s or "").strip()


class CninfoSource(DataSource):
    name = "巨潮资讯（上市公司公告）"
    evidence = "A"
    cost = "免费"
    legal = "法定信息披露平台，公开信息；需遵守合理请求频率"
    requires = None

    def __init__(self, delay=0.6):
        self.delay = delay
        self._last = 0.0

    def _throttle(self):
        gap = time.time() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.time()

    def _query(self, column, searchkey, page_num=1, page_size=30):
        # 实测：pageSize 上限 30；seDate 过滤会漏数据，因此不传，改客户端过滤
        data = urllib.parse.urlencode({
            "pageNum": page_num,
            "pageSize": page_size,
            "column": column,          # szse=深市, sse=沪市
            "tabName": "fulltext",
            "searchkey": searchkey,
            "isHLtitle": "true",
        }).encode()
        req = urllib.request.Request(API, data=data, headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        })
        self._throttle()
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def search(self, terms, days=180, limit=30, pages=3, industry_words=None):
        """
        按「具体环节词」检索。实测：越具体的词越准。
        '机器人' 这类泛词会匹配到『信息技术』等噪音，不建议使用；
        '减速器''六维力传感器' 这类环节词命中精准。
        """
        if not terms:
            return [], "未提供关键词"

        cutoff = datetime.now() - timedelta(days=days)
        seen, records, errors = set(), [], []
        calls = scanned = 0

        for term in terms[:6]:
            for column in ("szse", "sse"):
                for page in range(1, pages + 1):
                    try:
                        d = self._query(column, term, page_num=page)
                        calls += 1
                    except Exception as e:
                        errors.append(f"{term}/{column}/p{page}: {type(e).__name__}")
                        break

                    anns = d.get("announcements") or []
                    if not anns:
                        break

                    for a in anns:
                        code = a.get("secCode") or ""
                        title = _clean(a.get("announcementTitle"))
                        if not code or not title or code in seen:
                            continue

                        ts = a.get("announcementTime")
                        if not ts:
                            continue
                        dt_obj = datetime.fromtimestamp(ts / 1000)
                        if dt_obj < cutoff:
                            continue
                        if any(n in title for n in NOISE):
                            continue

                        strong = [w for w in SIGNAL_STRONG if w in title]
                        medium = [w for w in SIGNAL_MEDIUM if w in title]
                        if not strong and not medium:
                            continue

                        # 标题必须真的含该环节词（防止泛词噪音）
                        if term not in title and not any(
                                p in title for p in re.split(r"[（）()/]", term) if len(p) >= 2):
                            continue

                        scanned += 1
                        seen.add(code)

                        dt = dt_obj.strftime("%Y-%m-%d")
                        url = PDF_BASE + (a.get("adjunctUrl") or "")
                        hit = strong or medium

                        records.append(make_record(
                            名称=a.get("secName") or code,
                            证券代码=code,
                            环节=_classify(title, terms),
                            所在地="待核",
                            状态="已核实",
                            扩张信号=title,
                            信号类型="已发生事项",
                            证据等级="A",
                            置信度="高" if strong else "中",
                            证据来源=[f"巨潮资讯公告 {dt} {url}"],
                            关键发现=f"上市公司公告披露扩张/布局动作（{dt}，信号强度{'强' if strong else '中'}，命中词：{'、'.join(hit)}）",
                            风险="公告多为集团层面，需确认落地地点是否在目标城市；投资额与产能须读公告原文",
                            下一步="① 打开公告原文确认地点、投资额、产能与时间 ② 判断是否可计入返投口径",
                            触达路径={},
                        ))
                    if len(records) >= limit * 3:
                        break
                if len(records) >= limit * 3:
                    break
            if len(records) >= limit * 3:
                break

        records = records[:limit]
        status = f"{calls} 次请求，扫描 {scanned} 条，采纳 {len(records)} 条（{days} 天内）"
        if errors:
            status += f"；{len(errors)} 次失败（{errors[0]}）"
        return records, status


def _classify(title, terms):
    """
    按标题关键词归类环节。
    返回的标签尽量与 config/industries.yaml 的补链优先级键名对齐，便于继承优先级；
    归不出来就标「待归类」——不硬编。
    """
    RULES = [
        (["六维力", "力传感器", "力矩传感器"], "六维力/力矩传感器"),
        (["力矩电机", "无框力矩", "伺服电机"], "无框力矩电机"),
        (["谐波减速器", "谐波"], "谐波减速器"),
        (["减速器", "齿轮箱"], "减速器"),
        (["灵巧手", "夹爪", "丝杠"], "灵巧手"),
        (["芯片", "算力", "SoC"], "具身智能芯片"),
        (["机器人", "人形", "本体"], "本体与集成"),
    ]
    for words, label in RULES:
        if any(w in title for w in words):
            return label
    return "待归类"
