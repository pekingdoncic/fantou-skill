(function () {
  if (document.getElementById('__dcursor')) return;
  var st = document.createElement('style');
  st.textContent = '@keyframes __dcr{from{transform:scale(.25);opacity:1}to{transform:scale(1.7);opacity:0}}' +
    '@keyframes __dcp{0%{transform:scale(1)}45%{transform:scale(.86)}100%{transform:scale(1)}}';
  document.head.appendChild(st);

  var c = document.createElement('div');
  c.id = '__dcursor';
  c.style.cssText = 'position:fixed;left:-100px;top:-100px;width:26px;height:26px;z-index:2147483647;' +
    'pointer-events:none;transition:left .42s cubic-bezier(.22,.61,.36,1),top .42s cubic-bezier(.22,.61,.36,1);' +
    'filter:drop-shadow(0 2px 4px rgba(0,0,0,.35));';
  c.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26">' +
    '<path d="M4.5 2.5 L20 11.2 L12.6 12.6 L9.2 20.5 Z" fill="#ffffff" stroke="#1f2937" stroke-width="1.5" ' +
    'stroke-linejoin="round" stroke-linecap="round"/></svg>';
  document.body.appendChild(c);

  window.__curTo = function (x, y) { c.style.left = x + 'px'; c.style.top = y + 'px'; };
  window.__curEl = function (sel, dy) {
    var e = document.querySelector(sel);
    if (!e) return 0;
    var r = e.getBoundingClientRect();
    var y = r.top + (dy === undefined ? r.height / 2 : dy);
    window.__curTo(r.left + r.width / 2, y);
    return 1;
  };
  window.__curRipple = function () {
    var r = document.createElement('div');
    var x = parseFloat(c.style.left) || 0, y = parseFloat(c.style.top) || 0;
    r.style.cssText = 'position:fixed;z-index:2147483646;pointer-events:none;' +
      'left:' + x + 'px;top:' + y + 'px;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;' +
      'border:3px solid rgba(37,99,235,.85);animation:__dcr .6s ease-out forwards;';
    document.body.appendChild(r);
    setTimeout(function () { r.remove(); }, 620);
    c.style.animation = '__dcp .28s ease-out';
    setTimeout(function () { c.style.animation = ''; }, 300);
  };
  window.__curHide = function () { c.style.opacity = '0'; };
  window.__curShow = function () { c.style.opacity = '1'; };
  window.__curSmooth = function (on) {
    c.style.transition = on
      ? 'left .42s cubic-bezier(.22,.61,.36,1),top .42s cubic-bezier(.22,.61,.36,1)'
      : 'none';
  };
  window.__scrollTo = function (sel) {
    var e = document.querySelector(sel);
    if (e) e.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };
})();
