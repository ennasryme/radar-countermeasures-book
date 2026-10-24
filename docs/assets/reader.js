(() => {
  'use strict';
  const root = document.documentElement;
  const base = new URL(document.body.dataset.root, location.href);
  const page = document.body.dataset.page;
  const storage = {
    get(key) { try { return JSON.parse(localStorage.getItem('reading-room:' + key)); } catch { return null; } },
    set(key, value) { try { localStorage.setItem('reading-room:' + key, JSON.stringify(value)); } catch { /* Reading works without storage. */ } }
  };
  const themeButton = document.querySelector('.theme-toggle');
  function setTheme(theme) {
    root.dataset.theme = theme;
    themeButton.setAttribute('aria-label', theme === 'dark' ? 'Use light theme' : 'Use dark theme');
    storage.set('theme', theme);
  }
  setTheme(storage.get('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));
  themeButton.addEventListener('click', () => setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark'));

  let size = Number(storage.get('size')) || (innerWidth <= 760 ? 18 : 19);
  function setSize(value) {
    size = Math.max(16, Math.min(26, value));
    root.style.setProperty('--reader-size', size + 'px');
    document.querySelectorAll('[data-font]').forEach(button => {
      button.disabled = (size === 16 && button.dataset.font === '-1') || (size === 26 && button.dataset.font === '1');
    });
    storage.set('size', size);
  }
  setSize(size);
  document.querySelectorAll('[data-font]').forEach(button => button.addEventListener('click', () => setSize(size + Number(button.dataset.font))));

  const menu = document.querySelector('.menu-toggle');
  const sidebar = document.querySelector('.sidebar');
  function closeMenu() { sidebar.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); }
  menu.addEventListener('click', () => {
    const open = sidebar.classList.toggle('open');
    menu.setAttribute('aria-expanded', String(open));
  });
  sidebar.addEventListener('click', event => { if (event.target.closest('a')) closeMenu(); });
  document.addEventListener('click', event => { if (!sidebar.contains(event.target) && !menu.contains(event.target)) closeMenu(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });

  // Save a paragraph anchor instead of an image-dependent pixel offset.
  const article = document.querySelector('.book-text');
  const last = storage.get('last');
  const resume = document.querySelector('#start-reading');
  if (resume && last && typeof last.path === 'string' && /^xhtml\/[\w.-]+\.html$/.test(last.path)) {
    const target = new URL('content/' + last.path, base);
    if (typeof last.anchor === 'string') target.hash = last.anchor;
    resume.href = target.href;
    resume.replaceChildren(document.createTextNode('Continue reading '));
    const arrow = document.createElement('span'); arrow.textContent = '→'; arrow.setAttribute('aria-hidden', 'true'); resume.append(arrow);
    resume.title = last.title || 'Resume your last page';
  }
  if (article) {
    const anchors = [...article.querySelectorAll('h1,h2,h3,h4,h5,p')];
    anchors.forEach((element, index) => { if (!element.id) element.id = 'read-' + index; });
    let currentAnchor = location.hash.slice(1);
    const progress = document.querySelector('.reading-progress span');
    function remember() { storage.set('last', { path: page, anchor: currentAnchor, title: document.body.dataset.title }); }
    let scheduled = false;
    function update() {
      const height = document.documentElement.scrollHeight - innerHeight;
      progress.style.width = (height > 0 ? Math.min(100, Math.max(0, scrollY / height * 100)) : 100) + '%';
      let nearest = anchors[0];
      for (const element of anchors) {
        if (element.getBoundingClientRect().top <= 150) nearest = element;
        else break;
      }
      currentAnchor = nearest?.id || '';
      remember();
      scheduled = false;
    }
    const schedule = () => { if (!scheduled) { scheduled = true; requestAnimationFrame(update); } };
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    window.addEventListener('pagehide', remember);
    const restore = () => {
      if (location.hash.startsWith('#read-')) document.getElementById(location.hash.slice(1))?.scrollIntoView();
      schedule();
    };
    if (document.readyState === 'complete') restore();
    else window.addEventListener('load', restore, { once: true });
  }

  const dialog = document.querySelector('.search-dialog');
  const query = document.querySelector('#book-query');
  const results = document.querySelector('.search-results');
  const status = document.querySelector('.search-status');
  let indexPromise;
  let revision = 0;
  function openSearch() { if (!dialog.open) dialog.showModal(); query.focus(); }
  document.querySelector('[data-search]').addEventListener('click', openSearch);
  document.querySelector('.close-search').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } });
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); openSearch(); }
  });
  function highlight(text, term) {
    const fragment = document.createDocumentFragment();
    const position = text.toLowerCase().indexOf(term);
    if (position < 0) { fragment.append(text); return fragment; }
    fragment.append(text.slice(0, position));
    const mark = document.createElement('mark'); mark.textContent = text.slice(position, position + term.length);
    fragment.append(mark, text.slice(position + term.length));
    return fragment;
  }
  let debounce;
  query.addEventListener('input', () => {
    clearTimeout(debounce);
    const request = ++revision;
    debounce = setTimeout(async () => {
      const term = query.value.trim().toLowerCase();
      results.replaceChildren();
      if (term.length < 2) { status.textContent = 'Enter at least two characters to search.'; return; }
      status.textContent = 'Searching…';
      try {
        indexPromise ||= fetch(new URL('assets/search-index.json', base)).then(response => {
          if (!response.ok) throw new Error('Search unavailable');
          return response.json();
        }).catch(error => { indexPromise = null; throw error; });
        const index = await indexPromise;
        if (request !== revision) return;
        const matches = index.filter(section => (section.title + ' ' + section.text).toLowerCase().includes(term));
        status.textContent = matches.length ? `${matches.length} matching sections${matches.length > 40 ? ' · showing the first 40' : ''}` : 'No matches. Try a shorter phrase or another term.';
        for (const section of matches.slice(0, 40)) {
          const link = document.createElement('a'); link.className = 'search-result'; link.href = new URL(section.href, base).href;
          const chapter = document.createElement('small'); chapter.textContent = section.chapter;
          const title = document.createElement('strong'); title.append(highlight(section.title, term));
          const excerpt = document.createElement('p');
          const at = section.text.toLowerCase().indexOf(term);
          const start = Math.max(0, at - 65);
          const snippet = (start ? '…' : '') + section.text.slice(start, start + 200) + (start + 200 < section.text.length ? '…' : '');
          excerpt.append(highlight(snippet, term));
          link.append(chapter, title, excerpt); results.append(link);
        }
      } catch {
        if (request === revision) status.textContent = 'Search could not load. Please try again. You can still browse the chapters.';
      }
    }, 160);
  });
})();
