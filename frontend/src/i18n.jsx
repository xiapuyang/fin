/* i18n loader — must be first babel script in index.html.
 * Reads supported_langs from /config/app.json so backend + frontend share one source.
 */
const I18N = (() => {
  let _lang = "en", _s = {}, _ready = false, _q = [];

  const pickLang = (supported) => {
    const set = new Set(supported);
    const stored = localStorage.getItem("fin_lang");
    if (stored && set.has(stored)) return stored;
    const nav = (navigator.language || "en").split("-")[0];
    return set.has(nav) ? nav : (supported[0] || "en");
  };

  const _finish = () => { _ready = true; _q.forEach(f => f()); _q = []; };

  fetch(`/config/app.json?_=${Date.now()}`)
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
    .then(cfg => {
      const { default_lang = "en", supported_langs = ["en"] } = cfg.i18n || {};
      _lang = pickLang(supported_langs) || default_lang;
      document.documentElement.lang = _lang;
      return fetch(`/config/i18n/${_lang}.json?_=${Date.now()}`);
    })
    .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
    .then(d => { _s = d; _finish(); })
    .catch(err => {
      console.error("[i18n] load failed — UI will render keys as fallback:", err);
      _finish();
    });

  return {
    getLang: () => _lang,
    isReady: () => _ready,
    onReady: (f) => _ready ? f() : _q.push(f),
    t:       (k) => _s[k] ?? k,
    tf:      (k, vars) => {
      let s = _s[k] ?? k;
      for (const [key, val] of Object.entries(vars)) s = s.replaceAll(`{${key}}`, val);
      return s;
    },
    tCat:    (n) => _s[`balance.cat.${n}`] ?? n,
    setLang: (l) => {
      if (l === _lang) return;
      localStorage.setItem("fin_lang", l);
      const ctrl = new AbortController();
      const timeoutId = setTimeout(() => ctrl.abort(), 3000);
      fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ language: l }),
        signal: ctrl.signal,
      }).catch(() => {}).finally(() => { clearTimeout(timeoutId); location.reload(); });
    },
  };
})();
