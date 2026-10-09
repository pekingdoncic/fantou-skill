#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源注册表

新增数据源只需：
  1. 在本目录写一个类，继承 DataSource
  2. 在下面 ACTIVE / PLANNED 里注册

ACTIVE  —— 已接入，自动参与抓取
PLANNED —— 已实测/已登记但不可用（需凭证、需按地区适配、或已被反爬拦截）
           不参与抓取，只出现在「数据源清单」里，让决策者看到真实状态
"""

from .cninfo import CninfoSource
from .eastmoney import EastmoneyNoticeSource, EastmoneyNewsSource
from .stubs import (
    QccSource, TianyanchaSource, EiaSource, TenderSource,
    WindSource, ItjuziSource, PatentSource, BaiduNewsSource,
)

# 已接入 —— 全部实测可用（2026-10-03）
ACTIVE = [
    CninfoSource(),            # 巨潮资讯：上市公司公告（A 级）
    EastmoneyNoticeSource(),   # 东方财富公告（A 级）
    EastmoneyNewsSource(),     # 东方财富资讯（B 级）★ 目前唯一覆盖非上市公司的源
]

# 已登记待接入
PLANNED = [
    QccSource(), TianyanchaSource(), EiaSource(), TenderSource(),
    WindSource(), ItjuziSource(), PatentSource(), BaiduNewsSource(),
]


def all_sources():
    return ACTIVE + PLANNED


def active_sources():
    return [s for s in ACTIVE if s.available()]


def describe_all():
    return [s.describe() for s in all_sources()]
