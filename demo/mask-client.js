/* ============================================================
 * 对外演示遮蔽 —— 只用于录「给甲方看的版本」
 *
 * 原则：展示能力，但不交出配方。
 *   保留 → 产品形态、证据分级、口径门控、产业链框架、真实企业名单
 *   遮蔽 → 检索词、各源产出效率、配置文件路径、数据源全量清单、实测结论
 *
 * 这几处是这次调研最值钱的部分：等于把「去哪取数、成本多少、
 * 哪条路真的走得通」直接交出去。
 *
 * 用法：注入后在每次标签页渲染完成后调用 window.__maskClient()
 * ============================================================ */
(function () {
  function txt(el) { return (el.textContent || '').trim(); }

  /* 1) 检索词 —— 行业 know-how，换成组数
        ⚠️ 必须幂等：本函数会被反复调用（DOM 一变就重跑）。
           若不做判断，第二次执行时只剩 1 个 tag，会把「共 10 组」改成「共 1 组」。 */
  function maskTerms(root) {
    root.querySelectorAll('#out p').forEach(function (p) {
      if (txt(p).indexOf('检索词') === -1) return;
      if (/共\s*\d+\s*组/.test(txt(p))) return;   // 已经遮过了
      var tags = p.querySelectorAll('.tag');
      if (tags.length) {                       // 数据源页：tag 形式
        var n = tags.length;
        for (var i = 1; i < tags.length; i++) tags[i].remove();
        tags[0].textContent = '共 ' + n + ' 组 · 按产业链环节自动展开';
      } else {                                  // 运行报告页：纯文本，且在句尾
        p.innerHTML = p.innerHTML.replace(
          /检索词：[\s\S]*$/,
          '检索词：<b>共 10 组</b> · 按产业链环节自动展开'
        );
      }
    });
  }

  /* 2) 各源状态表 —— 产出效率等于取数地图，换成汇总口径 */
  function maskSourceTables(root) {
    root.querySelectorAll('#out table').forEach(function (tb) {
      var head = txt(tb.querySelector('tr') || tb);
      if (head.indexOf('数据源') === -1 || head.indexOf('返回') === -1) return;
      var total = 0, n = 0;
      tb.querySelectorAll('tr').forEach(function (r, i) {
        if (i === 0) return;
        n++;
        var c = r.cells;
        if (c && c[2]) total += parseInt(c[2].textContent, 10) || 0;
      });
      var p = document.createElement('p');
      p.className = 'src';
      p.style.margin = '8px 0 0';
      p.textContent = '已接入 ' + n + ' 个数据源 · 本次累计扫描 ' + total +
        ' 条原始记录 → 经严格校验后仅保留少量高置信信号（逐源明细不在演示中展开）';
      tb.parentNode.insertBefore(p, tb);
      tb.remove();
    });
  }

  /* 3) 配置文件路径 —— 不暴露工程结构
        左栏「政策配置: config/cities.yaml → 深圳」这类提示在每一帧都可见，
        是最持久的泄露点，所以用 TreeWalker 扫全页文本节点，而不是只找 pre/code。 */
  function maskConfigPaths() {
    var re = /[\w./-]*(?:config|kb)\/[\w.-]+/g;
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
    var nodes = [], n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach(function (node) {
      var v = node.nodeValue;
      if (!v || v.indexOf('/') === -1) return;
      var nv = v.replace(re, '（外置配置文件）');
      if (nv !== v) node.nodeValue = nv;
    });
  }

  /* 4) 数据源清单 —— 只留已接入的，候选源只报个数 */
  function maskSourceList(root) {
    root.querySelectorAll('#out table').forEach(function (tb) {
      if (txt(tb.querySelector('tr') || tb).indexOf('接入条件') === -1) return;
      var removed = 0;
      tb.querySelectorAll('tr').forEach(function (r, i) {
        if (i === 0) return;
        if (txt(r).indexOf('已接入') === -1) { r.remove(); removed++; }
      });
      if (removed) {
        var p = document.createElement('p');
        p.className = 'src';
        p.style.margin = '8px 0 0';
        p.textContent = '另有 ' + removed +
          ' 个候选数据源在评估中（含需凭证的商业数据库），按证据等级与成本分级接入。';
        tb.parentNode.insertBefore(p, tb.nextSibling);
      }
    });
  }

  /* 5) 实测结论 —— 这段是调研结论，换成通用表述 */
  function maskFindings(root) {
    root.querySelectorAll('#out .notice').forEach(function (n) {
      if (txt(n).indexOf('实测结论') === -1) return;
      n.innerHTML =
        '<b>数据源策略：</b>单一公告源覆盖不到细分环节厂商（其中大量为非上市公司），' +
        '因此采用「公告 + 媒体 + 商业数据库」多源交叉，并按证据等级 A/B/C/D 分级标注；' +
        'D 级与低置信度条目自动标记<b>禁止对外</b>。';
    });
  }

  var _running = false;
  window.__maskRuns = 0;
  function runAll() {
    if (_running) return;                 // 防重入：本函数会改 DOM
    _running = true;
    window.__maskRuns++;
    [maskTerms, maskSourceTables, maskConfigPaths, maskSourceList, maskFindings]
      .forEach(function (fn) { try { fn(document); } catch (e) {} });
    _running = false;
  }

  window.__maskClient = function () { runAll(); return 'masked'; };

  runAll();   // 注入即执行一次，覆盖首屏

  /* 为什么不用 MutationObserver 自动跟随（实测踩过，别再加回来）：
     抓取期间页面会持续更新 #status 与步骤指示器，观察器于是不断
     clearTimeout + 重新排一个 150ms 定时器，页面**始终存在 pending timer**。
     agent-browser 的 eval 会等待页面空闲，结果每次回读都被拖到超时 ——
     录制卡在「等待抓取」循环里 11 分钟没动静。
     实际需要的调用点只有三处，显式调用完全够：
       ① 注入时（本行）      ② 抓取完成后      ③ 每次切换标签页后
     历史上两次漏遮都不是「调用点漏了」，而是遮蔽函数自身的 bug
     （atob 中文乱码、路径只查 pre/code），修函数即可，不需要观察器。 */
})();
