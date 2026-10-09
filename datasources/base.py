#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源基类

设计原则：
1. 每个数据源声明自己的 证据等级 / 成本 / 合规状态 —— 不声明的一律视为不可用
2. 统一输出「企业记录」格式，与 kb/companies.yaml 结构一致，可直接合并
3. 抓取失败不抛异常，返回空列表 + 原因（保证主流程不因外部源挂掉而中断）
"""


class CompanyRecord(dict):
    """统一的企业记录结构，字段与 kb/companies.yaml 对齐"""
    FIELDS = [
        "名称", "全称", "证券代码", "环节", "优先级", "所在地",
        "状态", "扩张信号", "信号类型", "证据等级", "置信度",
        "证据来源", "关键发现", "风险", "下一步", "触达路径",
    ]


class DataSource:
    """
    数据源基类。

    子类必须声明：
        name       数据源名称
        evidence   产出的证据等级（A/B/C/D）
        cost       成本说明
        legal      合规说明（能否商用、是否需授权）
        requires   需要的凭证（如 API Key）
    """

    name = "未命名数据源"
    evidence = "D"
    cost = "未知"
    legal = "未声明"
    requires = None

    def available(self):
        """当前环境是否可用（不联网，只看配置）"""
        return True

    def search(self, terms, days=90, limit=30, industry_words=None):
        """
        按关键词检索企业扩张信号。

        :param terms:          关键词列表，如 ["机器人", "减速器"]
        :param days:           回溯天数
        :param limit:          返回上限
        :param industry_words: 行业相关性词表，用于过滤跨行业噪音（可选）
        :return: (list[CompanyRecord], str) —— 记录列表 + 状态说明
        """
        raise NotImplementedError

    def describe(self):
        return {
            "名称": self.name,
            "证据等级": self.evidence,
            "成本": self.cost,
            "合规": self.legal,
            "需要凭证": self.requires,
            "可用": self.available(),
        }


def make_record(**kw):
    """构造一条规范化的企业记录"""
    rec = CompanyRecord()
    for f in CompanyRecord.FIELDS:
        rec[f] = kw.get(f, "")
    rec["证据来源"] = kw.get("证据来源", [])
    rec["触达路径"] = kw.get("触达路径", {})
    return rec
