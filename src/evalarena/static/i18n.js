/* EvalArena i18n - Language Switcher */
(function() {
  const STORAGE_KEY = 'evalarena-lang';
  
  function getLang() {
    return localStorage.getItem(STORAGE_KEY) || 'zh';
  }
  
  function setLang(lang) {
    localStorage.setItem(STORAGE_KEY, lang);
    applyLang(lang);
    updateToggle(lang);
  }
  
  function applyLang(lang) {
    document.querySelectorAll('[data-' + lang + ']').forEach(el => {
      const text = el.getAttribute('data-' + lang);
      if (text) el.textContent = text;
    });
    document.querySelectorAll('[data-' + lang + '-placeholder]').forEach(el => {
      el.placeholder = el.getAttribute('data-' + lang + '-placeholder');
    });
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
  }
  
  function updateToggle(lang) {
    const btn = document.getElementById('lang-toggle');
    if (btn) {
      btn.textContent = lang === 'zh' ? '🌐 EN' : '🌐 中';
      btn.title = lang === 'zh' ? 'Switch to English' : '切换到中文';
    }
  }
  
  window.__evalarena = {
    getLang: getLang,
    setLang: setLang,
    toggle: function() { setLang(getLang() === 'zh' ? 'en' : 'zh'); }
  };
  
  // Auto-init on DOM ready
  document.addEventListener('DOMContentLoaded', function() {
    applyLang(getLang());
    updateToggle(getLang());
  });
})();
