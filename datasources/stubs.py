#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
已登记但尚未接入的数据源

这里不是"占位符"，而是**明确记录每个源的成本、合规状态与接入条件**。
这样决策者可以直接看这张表决定买哪个、先做哪个。

需要凭证或按地区适配的源，默认 available() 返回 False，
不会参与自动抓取，只出现在「数据源清单」里。
"""
from .base import DataSource


class _NeedsKey(DataSource):
    available = lambda self: False


# ------------------------------------------------------------------ 商业API
class QccSource(_NeedsKey):
    name = "企查查开放平台"
    evidence = "C"
    cost = "工商信息 ¥1,000/5,000次（≈¥0.2/次）；合作风险排查 ¥1,200/200次（≈¥6/次）"
    legal = "需企业实名认证 + 应用场景审核；数据用于二次加工须核对服务条款"
    requires = "AppKey / SecretKey（企查查开放平台申请）"

    def search(self, terms, days=90, limit=30, industry_words=None):
        return [], "未配置 AppKey，跳过"


class TianyanchaSource(_NeedsKey):
    name = "天眼查开放平台"
    evidence = "C"
    cost = "按接口计费，与企查查同量级"
    legal = "同企查查，需实名与应用场景审核"
    requires = "API Key"

    def search(self, terms, days=90, limit=30, industry_words=None):
        return [], "未配置 API Key，跳过"


class WindSource(_NeedsKey):
    name = "Wind 金融终端 / iFinD"
    evidence = "C"
    cost = "通常机构已有授权；无独立 API 计费"
    legal = "受终端授权协议约束，数据不得外传"
    requires = "终端账号 / WindPy 或 iFinD 授权"

    def search(self, terms, days=90, limit=30, industry_words=None):
        return [], "未配置终端授权，跳过"


class ItjuziSource(_NeedsKey):
    name = "IT桔子 / 投中数据"
    evidence = "C"
    cost = "按年订阅（万元级）"
    legal = "订阅协议约束，禁止转售"
    requires = "订阅账号"

    def search(self, terms, days=90, limit=30, industry_words=None):
        return [], "未配置订阅账号，跳过"


# ------------------------------------------------------------ 官方公示源
class EiaSource(_NeedsKey):
    """
    环评公示 —— 对招商场景价值极高但常被忽略。

    为什么重要：企业新增产线**必须**做环境影响评价并公示，
    公示里会写清楚 建设地点 / 建设内容 / 产能 / 投资额。
    这是非上市公司的扩产信号最可靠来源。

    难点：没有全国统一 API，各地生态环境局网站结构不同，需按地区逐个适配。
    """
    name = "环评公示（各地生态环境局）"
    evidence = "A"
    cost = "免费"
    legal = "政府公开信息，可合法获取；需按站点遵守 robots 与访问频率"
    requires = "按地区编写适配器（无统一 API）"

    def search(self, terms, days=90, limit=30, industry_words=None):
        return [], "需按地区适配，暂未接入"


class TenderSource(_NeedsKey):
    """
    招投标公告 —— 扩产的**前置信号**。

    企业要扩产，通常先招标采购设备/工程。招标公告早于环评和投产，
    是链条上最早的信号。

    实测（2026-10-03）：
      · 中国招标投标公共服务平台 cebpubservice.com —— 站点可达，但搜索结果为
        前端 JS 渲染，直接请求只返回页面骨架；推测的 AJAX 接口返回 404，
        需抓包定位真实接口后适配
      · 全国公共资源交易平台 deal.ggzy.gov.cn —— HTTP 502
      · 中国政府采购网 —— 返回「频繁访问!」反爬拦截页
    结论：招投标源价值高但适配成本高，需按平台逐个抓包适配，暂不接入。
    """
    name = "招投标公告（政府采购网 / 公共资源交易中心）"
    evidence = "A"
    cost = "免费（部分平台提供开放数据接口）"
    legal = "政府公开信息；部分平台有反爬限制，不绕过"
    requires = "按平台抓包适配（实测 3 个平台均需额外适配）"

    def search(self, terms, days=90, limit=30, industry_words=None):
        return [], "实测站点可达但需抓包适配，暂未接入"


class BaiduNewsSource(_NeedsKey):
    """
    百度新闻搜索 —— **实测已被反爬拦截，不接入**。

    实测（2026-10-03）：连续 5 次请求全部返回「百度安全验证」页（1438 字节），
    成功率 0/5。即便偶尔成功，HTML 结构也会变动，维护成本高。

    保留在清单里是为了记录这个结论，避免以后重复踩坑。
    替代方案：东方财富资讯（已接入，B 级，稳定返回 JSON）。
    """
    name = "百度新闻搜索（已实测被拦截，不接入）"
    evidence = "B"
    cost = "免费"
    legal = "搜索引擎服务条款限制自动化访问；不绕过验证码"
    requires = "——（实测 0/5 成功率，已放弃）"

    def search(self, terms, days=90, limit=30, industry_words=None):
        return [], "实测触发「安全验证」，已放弃接入"


class PatentSource(_NeedsKey):
    name = "国家知识产权局（专利）"
    evidence = "A"
    cost = "免费（公开检索）"
    legal = "公开信息"
    requires = "按需适配检索接口"

    def search(self, terms, days=90, limit=30, industry_words=None):
        return [], "暂未接入"
