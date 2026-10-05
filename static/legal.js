(function () {
  var root = document.documentElement;
  var buttons = document.querySelectorAll('.langs button');

  function setLang(l) {
    root.dataset.lang = l;
    buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.l === l)); });
    document.querySelectorAll('a.keep').forEach(function (a) {
      a.href = a.pathname + (l === 'en' ? '?lang=en' : '') + a.hash;
    });
  }

  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      setLang(b.dataset.l);
      history.replaceState(null, '', location.pathname + (b.dataset.l === 'en' ? '?lang=en' : '') + location.hash);
    });
  });

  setLang(root.dataset.lang === 'en' ? 'en' : 'de');
})();
