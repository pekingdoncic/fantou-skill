#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
东方财富数据源 —— 公告 + 资讯（两个独立接口）

=============================================================================
为什么加这个源
=============================================================================
巨潮资讯只覆盖上市公司公告。实测 8 个环节词、2 年内仅 6 条相关公告，
根因是**细分环节厂商大多是非上市公司**，而招商目标恰恰大量是这类企业。

东方财富的**资讯搜索**接口抓的是权威媒体报道（融资 / 扩产 / 量产 / 落地），
实测能覆盖非上市公司 —— 这是目前唯一能补上这个缺口的免费源。

=============================================================================
实测记录（2026-10-03，全部为真实请求）
=============================================================================
接口一：公告搜索
    POST/GET https://np-anotice-stock.eastmoney.com/api/security/ann
    踩坑：
      1. 检索参数是 `title`，**不是 `keyword`**（keyword 会被忽略，返回最新公告）
      2. `title` 走「**分词模糊匹配**」——搜「六维力传感器」会命中「赛**力**斯」，
         搜「无框力矩电机」会命中「德科立」里的「无」字。返回 100 条几乎全是噪音
      3. 返回标题里带 `<font color="#ea5504">` 高亮标签，必须清洗
    结论：**召回必须配严格二次校验**，否则噪音率 >95%
    实测：12 个环节词 → 召回 733 条 → 严格校验后仅 2 条真信号

接口二：资讯搜索
    GET https://search-api-web.eastmoney.com/search/jsonp
    返回干净 JSON，含 媒体名 / 日期 / 标题 / 链接
    实测：8 个检索式 → 召回 240 条 → 去噪后 51 条真实信号
    抓到的高价值样本（均为非上市公司）：
      · 鑫精诚传感器 完成数亿元 B 轮融资，深创投连续加注
      · 蓝点触控（六维力传感器龙头）数亿元 D 轮，广汽资本领投
      · 帕西尼感知科技 数亿元 B++ 轮，累计融资超 40 亿元
      · 中大力德 拟募资 5.3 亿加码具身智能关节模组
"""
import json
import re
import time
import urllib.parse
import urllib.request
import ssl
from datetime import date, timedelta

from .base import DataSource, make_record

# ----------------------------------------------------------------- 网络
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 东方财富会在标题里插高亮标签，必须清掉
_HL_TAG = re.compile(r"</?font[^>]*>")
_HTML_TAG = re.compile(r"<[^>]+>")


def _clean(s):
    return _HL_TAG.sub("", _HTML_TAG.sub("", s or "")).strip()


# ------------------------------------------------------------ 信号词表
# 强信号：明确的产能/项目落地动作
SIGNAL_STRONG = [
    "扩产", "扩建", "新增产能", "产能建设", "投资建设", "生产基地", "投产",
    "新建项目", "技改", "生产项目", "产业基地", "超级工厂", "产线", "下线",
    "量产", "满产", "产能提升", "产能爬坡",
]
# 中信号：资本动作，可能是扩张前兆
SIGNAL_MEDIUM = [
    "融资", "募资", "定增", "增资", "募投", "投资", "设立", "子公司",
    "战略合作", "签约", "落地", "开工", "项目",
]
SIGNAL = SIGNAL_STRONG + SIGNAL_MEDIUM

# 噪音：财经媒体的股价类报道，与招商无关
NOISE = [
    "涨停", "跌停", "异动", "股价", "连板", "主力", "净买入", "龙虎榜",
    "概念股", "ETF", "指数", "早参", "收评", "午评", "盘中", "复盘",
    "风险提示", "问询", "澄清", "减持", "质押", "担保", "回购",
    "年度报告", "半年度报告", "季度报告", "股东大会", "独立董事",
    "会议决议", "保荐", "审计", "补充流动资金", "延期", "结项", "终止",
    # 跨行业噪音（东方财富是全文检索，会混进其它赛道的扩产新闻）
    "封装基板", "ABF", "CIS", "图像传感器", "光模块", "存储", "锂电",
    "负极", "正极", "光伏", "半导体设备", "面板", "PCB", "CPO",
    # 第二批跨行业噪音（2026-10 实测：三星电机/德昌电机/银轮股份漏进来了）
    # 注意：这三条的**标题是干净的**，脏的是公司名本身含行业词（「三星电机」的「电机」）。
    # 标题级词表拦不住，真正的解法是 _relevant() 先剔除公司名再判相关性。
    # 这里只补确实属于标题级的噪音词。
    "基板", "热管理", "尾气",
    # 股票推荐 / 行情类噪音（实测漏进「智能机器人高成长潜力股出炉」）
    "潜力股", "个股", "涨幅", "受益股", "龙头股", "涨停板",
    "开盘", "收盘", "三大指数", "机构调研", "北向资金",
    # 海外工厂（实测漏进「特斯拉得州机器人工厂主结构接近完工」）
    "得州", "德州",
]

# 明确的「已发生」动词（用于区分 已发生事项 / 早期意向）
DONE_WORDS = ["完成", "已", "投产", "下线", "落地", "签署", "中标", "获批", "通过", "实现"]
PLAN_WORDS = ["拟", "将", "计划", "目标", "意向", "筹备", "有望", "预计"]


# -------------------------------------------------------- 企业名抽取
# 公司名后缀 —— 按**长度降序**排列，避免「机器人」被截成「机器」、「传感器」被截成「传感」
_SUFFIX = (
    "机器人", "传感器", "减速器", "控制器", "执行器", "驱动器",
    "科技", "智能", "电机", "机电", "机器", "精密", "电子", "股份",
    "集团", "智控", "驱动", "光电", "重工", "装备", "自动化", "电气",
    "动力", "数控", "新材", "微电子", "半导体", "材料", "系统", "技术",
    "触控", "感知", "视觉", "软件", "网络", "通信",
)

# 这些词出现在「：」前或公司名里，说明抽到的不是公司名，而是标题短语
_NOT_COMPANY = [
    "拟", "将", "计划", "加码", "重点", "多家", "豪掷", "美股", "港股", "A股",
    "涨价", "竞速", "共振", "背后", "成交额", "前20", "前十", "龙头", "行业",
    "产业", "市场", "全球", "国内", "中国", "概念", "板块", "指数", "机构",
    "供应商", "分析师", "记者", "观察", "盘点", "解读", "深度", "专题",
    "再获", "完成", "获", "牵手", "联手", "合作", "斥资", "拟发", "拟定增",
    # 泛行业词：它们以公司名后缀结尾，但本身不是公司
    "具身智能", "人形", "赛道", "资本", "融资", "机器视觉", "人工智能",
    # 地名 / 海外大厂（2026-10 实测：抽出过「特斯拉得州机器人」这种标题片段）
    # 招商目标是可落地的产业链企业，海外巨头与地名短语都不是线索
    "得州", "德州", "美国", "日本", "韩国", "德国", "越南", "印度", "欧洲",
    "特斯拉", "英伟达", "谷歌", "苹果", "微软", "亚马逊", "OpenAI",
]
# 公司名后缀（用于判断「像不像公司名」）
_CORP_SUFFIX = ("股份", "集团", "控股", "有限公司")
# 不能单独当公司名的泛词（与行业词表联动，见 extract_company）
_GENERIC = {
    "六维力传感器", "力传感器", "力矩传感器", "视觉传感器", "图像传感器",
    "谐波减速器", "RV减速器", "精密减速器", "减速器", "减速机",
    "无框力矩电机", "力矩电机", "伺服电机", "空心杯电机", "电机",
    "灵巧手", "机器人", "人形机器人", "机械臂", "行星滚柱丝杠", "丝杠",
    "关节模组", "关节", "零部件", "执行器", "驱动器",
}


def _is_company(name):
    """判断抽出来的字符串是否像公司名 —— 宁可判否，不可误判"""
    if not name or not (2 <= len(name) <= 10):
        return False
    if name in _GENERIC:
        return False
    if any(w in name for w in _NOT_COMPANY):
        return False
    # 以公司后缀结尾，或 3-4 字纯中文简称（如「中大力德」「诺因智能」）
    if name.endswith(_CORP_SUFFIX):
        return True
    if any(name.endswith(s) for s in _SUFFIX):
        return True
    if 3 <= len(name) <= 4 and re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9]+", name):
        return True
    return False


def extract_company(title):
    """
    从新闻标题里抽取企业名 —— **保守策略，抽不准就不抽**。

    只认两种高可靠模式：
      规则 1  标题以「公司名：」开头（公告与多数企业新闻的写法）
      规则 2  标题以「公司名+后缀」开头（如「珞石机器人第10000台…」）

    抽不到的返回空字符串，记录会进入「原始信号流」原文展示 ——
    这样既不脑补企业名，也不丢信息（用户能在原始标题里自己看到）。
    """
    if not title:
        return ""

    # 规则 1：「XXX：正文」—— 冒号前的部分，取最后一段（避开「导语 公司名：」的写法）
    m = re.match(r"^(.{2,40}?)[：:]\s*\S", title)
    if m:
        head = m.group(1).strip()
        for seg in reversed(re.split(r"[\s　]+", head)):
            seg = seg.strip("，,、；;·|")
            if _is_company(seg):
                return seg

    # 规则 2：标题**开头**即公司名 + 后缀（开头锚定，避免句中误匹配）
    suffix_alt = "|".join(_SUFFIX)
    for m in re.finditer(r"^([\u4e00-\u9fa5A-Za-z0-9]{2,8}?(?:" + suffix_alt + r"))", title):
        if _is_company(m.group(1)):
            return m.group(1)

    return ""


# 行业相关性词表 —— 用于过滤「泛扩产新闻」
# 东方财富是全文模糊检索：搜「减速器 扩产」会返回「胶原蛋白扩产竞速」「光模块扩产」。
# 必须要求标题里出现**行业词**，否则噪音会淹没信号。
_DEFAULT_INDUSTRY_WORDS = [
    "机器人", "具身智能", "人形", "减速器", "减速机", "电机", "传感器", "灵巧手",
    "丝杠", "关节", "伺服", "谐波", "RV", "力矩", "力觉", "触觉", "执行器",
    "机械臂", "本体", "零部件", "智能制造", "自动化",
]


def _relevant(title, industry_words):
    """
    标题是否与本行业相关 —— 不相关的一律丢弃，宁可少不可错。

    ⚠️ 关键：必须先剔除公司名再判断。
    2026-10 实测漏过两家跨行业企业：
      · 三星电机   —— 韩国半导体基板厂，标题「三星电机越南公司将投资2.51万亿韩元建设工厂」
      · 德昌电机控股 —— 汽车微电机，标题「德昌电机控股：全资附属公司拟对无锡巨蟹…」
    这两条**标题本身是干净的**，脏的是公司名里含行业词「电机」。
    直接判相关性会被公司名蒙混过关；剔除公司名后它们不再命中任何行业词，正确丢弃。
    """
    words = industry_words or _DEFAULT_INDUSTRY_WORDS
    probe = title
    cn = extract_company(title)
    if cn and cn in probe:
        probe = probe.replace(cn, "", 1)
    return any(w in probe for w in words)


def classify_signal(title):
    """区分「已发生事项」与「早期意向」—— 这条区分是硬性要求，不可合并"""
    if any(w in title for w in PLAN_WORDS):
        return "早期意向"
    if any(w in title for w in DONE_WORDS):
        return "已发生事项"
    return "待确认"


# ============================================================ 源一：公告
class EastmoneyNoticeSource(DataSource):
    name = "东方财富（上市公司公告）"
    evidence = "A"
    cost = "免费"
    legal = "公开披露信息；遵守站点访问频率，已内置限速"
    requires = None

    API = "https://np-anotice-stock.eastmoney.com/api/security/ann"

    def _query(self, term, page=1, size=50):
        qs = urllib.parse.urlencode({
            "sr": -1, "page_size": size, "page_index": page,
            "ann_type": "A", "client_source": "web", "title": term,
        })
        req = urllib.request.Request(self.API + "?" + qs,
                                     headers=dict(_UA, Referer="https://data.eastmoney.com/"))
        with urllib.request.urlopen(req, timeout=15, context=_CTX) as r:
            d = json.loads(r.read().decode("utf-8", "ignore"))
        return d.get("data", {}).get("list", []) or []

    def search(self, terms, days=180, limit=30, industry_words=None):
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        out, reqs, scanned = [], 0, 0

        for term in terms[:10]:
            # 严格二次校验用的核心片段：整词，或去括号后的主词
            parts = [p for p in re.split(r"[/（(]", term) if p][:1] or [term]
            try:
                for page in (1, 2):
                    lst = self._query(term, page)
                    reqs += 1
                    if not lst:
                        break
                    for it in lst:
                        scanned += 1
                        title = _clean(it.get("title", ""))
                        d = (it.get("notice_date") or "")[:10]
                        if d < cutoff:
                            continue
                        # 严格校验：必须含核心片段 + 含信号词 + 不含噪音词
                        if not all(p in title for p in parts):
                            continue
                        if not any(k in title for k in SIGNAL):
                            continue
                        if any(n in title for n in NOISE):
                            continue
                        if not _relevant(title, industry_words):
                            continue
                        code = (it.get("codes") or [{}])[0]
                        art = it.get("art_code", "")
                        out.append(make_record(
                            名称=code.get("short_name", ""),
                            证券代码=code.get("stock_code", ""),
                            状态="已核实",
                            扩张信号=title,
                            信号类型=classify_signal(title),
                            证据等级="A",
                            置信度="中高",
                            证据来源=[f"上市公司公告，{d}，"
                                      f"https://data.eastmoney.com/notices/detail/{art}.html"],
                            关键发现=title,
                            风险="公告标题仅表明投资动作，是否涉及异地布局需读原文确认",
                            下一步="① 调取公告原文确认建设地点 ② 确认是否已有异地布局计划",
                        ))
                    time.sleep(0.5)
            except Exception:
                break
            time.sleep(0.4)

        # 去重
        uniq = {}
        for r in out:
            uniq[(r["名称"], r["扩张信号"])] = r
        recs = list(uniq.values())[:limit]
        return recs, f"{reqs} 次请求，扫描 {scanned} 条，严格校验后采纳 {len(recs)} 条（{days} 天内）"


# ============================================================ 源二：资讯
class EastmoneyNewsSource(DataSource):
    """
    东方财富资讯搜索 —— 本项目**唯一能覆盖非上市公司**的源。

    抓的是权威媒体报道（融资/扩产/量产/落地），
    媒体报道属 B 级证据：可引用但需标注来源。
    """
    name = "东方财富（媒体资讯）"
    evidence = "B"
    cost = "免费"
    legal = "公开新闻检索；遵守站点访问频率，已内置限速"
    requires = None

    API = "https://search-api-web.eastmoney.com/search/jsonp"

    def _query(self, kw, size=30):
        param = {
            "uid": "", "keyword": kw, "type": ["cmsArticleWebOld"],
            "client": "web", "clientType": "web", "clientVersion": "curr",
            "param": {"cmsArticleWebOld": {
                "searchScope": "default", "sort": "default",
                "pageIndex": 1, "pageSize": size, "preTag": "", "postTag": "",
            }},
        }
        url = (self.API + "?cb=cb&param="
               + urllib.parse.quote(json.dumps(param, ensure_ascii=False)))
        req = urllib.request.Request(url, headers=dict(_UA, Referer="https://so.eastmoney.com/"))
        with urllib.request.urlopen(req, timeout=15, context=_CTX) as r:
            t = r.read().decode("utf-8", "ignore")
        j = json.loads(t[t.index("(") + 1:t.rindex(")")])
        return j.get("result", {}).get("cmsArticleWebOld", []) or []

    def search(self, terms, days=180, limit=40, industry_words=None):
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        out, reqs, scanned = [], 0, 0

        # 检索式 = 环节词 × 动作词，用动作词把「新闻」收窄成「扩张信号」
        queries = []
        for t in terms[:8]:
            queries.append(f"{t} 扩产")
            queries.append(f"{t} 融资")
        queries = queries[:14]

        for q in queries:
            try:
                arts = self._query(q)
                reqs += 1
            except Exception:
                continue
            for a in arts:
                scanned += 1
                title = _clean(a.get("title", ""))
                d = (a.get("date") or "")[:10]
                if d < cutoff or len(title) < 8:
                    continue
                if not any(k in title for k in SIGNAL):
                    continue
                if any(n in title for n in NOISE):
                    continue
                if not _relevant(title, industry_words):
                    continue
                media = a.get("mediaName", "")
                name = extract_company(title)
                out.append(make_record(
                    名称=name,
                    状态="待核" if not name else "已核实",
                    扩张信号=title,
                    信号类型=classify_signal(title),
                    证据等级="B",
                    置信度="中",
                    证据来源=[f"{media}，{d}，{a.get('url', '')}"],
                    关键发现=title,
                    风险="媒体报道为二手信息，涉及金额与地点须回溯企业公告或官网核实",
                    下一步="① 回溯原始报道确认细节 ② 核对企业工商与股权信息",
                ))
            time.sleep(0.6)

        uniq = {}
        for r in out:
            uniq[r["扩张信号"]] = r
        recs = list(uniq.values())[:limit]
        return recs, f"{reqs} 次请求，扫描 {scanned} 条，去噪后采纳 {len(recs)} 条（{days} 天内）"
