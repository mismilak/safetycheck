(function () {
  try {
    var t = localStorage.getItem('sc-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
    var m = document.querySelector('meta[name=theme-color]');
    if (m) m.content = t === 'light' ? '#f3f5fa' : '#0b1020';
  } catch (e) {}
})();
