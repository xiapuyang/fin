/* i18n loader — must be first babel script in index.html */
const _FIN_LANG = (() => {
  const s = localStorage.getItem("fin_lang");
  if (s && ["en", "zh"].includes(s)) return s;
  const nav = (navigator.language || "en").split("-")[0];
  return ["en", "zh"].includes(nav) ? nav : "en";
})();
document.documentElement.lang = _FIN_LANG;

const I18N = (() => {
  let _s = {}, _ready = false, _q = [];

  fetch(`/config/i18n/${_FIN_LANG}.json`)
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(d => { _s = d; _ready = true; _q.forEach(f => f()); _q = []; })
    .catch(err => {
      console.error(`[i18n] failed to load /config/i18n/${_FIN_LANG}.json — UI will render keys as fallback:`, err);
      _ready = true; _q.forEach(f => f()); _q = [];
    });

  return {
    getLang: () => _FIN_LANG,
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
      if (l === _FIN_LANG) return;
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
