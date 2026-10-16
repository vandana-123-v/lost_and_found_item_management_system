/* Progressive enhancement: every mutation also works as a CSRF-protected form. */
(() => {
  'use strict';
  const root = document.documentElement;
  try { root.dataset.theme = localStorage.getItem('hub-theme') || 'light'; } catch (_) {}
  document.querySelectorAll('.theme-toggle').forEach(button => button.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem('hub-theme', root.dataset.theme); } catch (_) {}
  }));
  const menu = document.querySelector('.mobile-menu');
  const sidebar = document.querySelector('#sidebar');
  const syncDrawer = () => {
    if (sidebar) sidebar.inert = matchMedia('(max-width: 950px)').matches && !sidebar.classList.contains('open');
  };
  syncDrawer();
  window.addEventListener('resize', syncDrawer);
  menu?.addEventListener('click', () => {
    const open = document.querySelector('#sidebar').classList.toggle('open');
    menu.setAttribute('aria-expanded', String(open));
    syncDrawer();
  });
  document.querySelector('.drawer-close')?.addEventListener('click', () => {
    sidebar.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); syncDrawer(); menu.focus();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') { document.querySelector('#sidebar')?.classList.remove('open'); menu?.setAttribute('aria-expanded', 'false'); syncDrawer(); }
  });
  document.querySelectorAll('.sidebar nav a').forEach(link => {
    const url = new URL(link.href);
    if (url.pathname === location.pathname && (!url.search || url.search === location.search)) {
      link.classList.add('active'); link.setAttribute('aria-current', 'page');
    }
  });
  document.querySelectorAll('.password-toggle').forEach(button => button.addEventListener('click', () => {
    const input = button.previousElementSibling;
    input.type = input.type === 'password' ? 'text' : 'password';
    button.textContent = input.type === 'password' ? 'Show' : 'Hide';
    button.setAttribute('aria-label', `${button.textContent} password`);
  }));
  const password = document.querySelector('#id_password1, #id_new_password1');
  password?.addEventListener('input', () => {
    const tests = [/.{8,}/, /[A-Z]/, /[a-z]/, /[0-9]/, /[^A-Za-z0-9\s]/];
    const score = tests.filter(rule => rule.test(password.value)).length;
    const strength = document.querySelector('.strength');
    if (strength) {
      strength.querySelector('meter').value = score;
      strength.querySelector('span').textContent = score === 5 ? 'Strong' : score >= 3 ? 'Getting stronger' : 'Needs improvement';
    }
  });
  const dialog = document.querySelector('#confirm-dialog');
  let pending = null;
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (form.dataset.confirmed === 'yes') return;
    event.preventDefault(); pending = form;
    dialog.querySelector('#confirm-message').textContent = form.dataset.confirm;
    dialog.showModal();
  }));
  dialog?.querySelector('[data-confirm-cancel]').addEventListener('click', () => { dialog.close(); pending = null; });
  dialog?.querySelector('[data-confirm-yes]').addEventListener('click', () => {
    dialog.close(); if (pending) { pending.dataset.confirmed = 'yes'; pending.requestSubmit(); pending = null; }
  });
  document.querySelectorAll('.dismiss').forEach(button => button.addEventListener('click', () => button.closest('.toast').remove()));
  const input = document.querySelector('.image-upload');
  const zone = document.querySelector('.drop-zone');
  const preview = document.querySelector('.image-previews');
  const previewFiles = () => {
    if (!input || !preview) return;
    preview.querySelectorAll('img').forEach(image => URL.revokeObjectURL(image.src));
    preview.replaceChildren();
    const files = Array.from(input.files);
    const valid = files.length <= 6 && files.every(file => ['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && file.size <= 5 * 1024 * 1024);
    input.setCustomValidity(valid ? '' : 'Choose up to six JPG, PNG, or WEBP images, at most 5 MB each.');
    if (!valid) { input.reportValidity(); return; }
    files.forEach(file => { const image = new Image(); image.src = URL.createObjectURL(file); image.alt = `Preview: ${file.name}`; preview.append(image); });
  };
  input?.addEventListener('change', previewFiles);
  if (zone && input) {
    ['dragenter', 'dragover'].forEach(type => zone.addEventListener(type, event => { event.preventDefault(); zone.classList.add('drag-over'); }));
    ['dragleave', 'drop'].forEach(type => zone.addEventListener(type, event => { event.preventDefault(); zone.classList.remove('drag-over'); }));
    zone.addEventListener('drop', event => { input.files = event.dataTransfer.files; previewFiles(); });
    zone.addEventListener('click', () => input.click());
    zone.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); input.click(); } });
  }
  document.querySelectorAll('.ajax-read').forEach(form => form.addEventListener('submit', async event => {
    event.preventDefault(); const button = form.querySelector('button'); button.disabled = true;
    try {
      const response = await fetch(form.action, {method: 'POST', body: new FormData(form), headers: {Accept: 'application/json'}, credentials: 'same-origin'});
      if (!response.ok) throw new Error('Request failed');
      const result = await response.json();
      document.querySelectorAll('.unread-count').forEach(node => { node.textContent = result.unread; });
      if (form.closest('.notification')) { form.closest('.notification').classList.remove('unread'); form.remove(); }
      else location.reload();
    } catch (_) { button.disabled = false; button.textContent = 'Retry'; }
  }));
  document.querySelectorAll('form:not(.ajax-read)').forEach(form => form.addEventListener('submit', event => {
    if (event.defaultPrevented || (form.dataset.confirm && form.dataset.confirmed !== 'yes')) return;
    const button = event.submitter;
    if (button && form.method.toLowerCase() === 'post') {
      // Delay disabling until the browser has serialized successful form controls.
      setTimeout(() => { button.disabled = true; button.textContent = 'Please wait…'; }, 0);
    }
  }));
  window.addEventListener('pageshow', () => document.querySelectorAll('button:disabled').forEach(button => { button.disabled = false; }));
  const data = document.querySelector('#chart-data');
  if (data) {
    const charts = JSON.parse(data.textContent);
    document.querySelectorAll('[data-chart]').forEach(container => {
      const key = container.dataset.chart; const rows = charts[key] || [];
      if (!rows.length) { const empty = document.createElement('p'); empty.className = 'chart-empty'; empty.textContent = 'No records in this period.'; container.append(empty); return; }
      const max = Math.max(...rows.map(row => row.total), 1);
      rows.forEach(row => {
        const label = key === 'monthly' ? `${row.month} · ${row.item_type}` : row.status || row.category__name;
        const wrap = document.createElement('div'); wrap.className = 'chart-row';
        const name = document.createElement('span'); name.textContent = label;
        const track = document.createElement('div'); track.className = 'chart-track';
        const bar = document.createElement('div'); bar.className = `chart-bar ${row.item_type === 'LOST' ? 'lost' : ''}`; bar.style.width = `${row.total / max * 100}%`;
        const total = document.createElement('strong'); total.textContent = row.total;
        track.append(bar); wrap.append(name, track, total); container.append(wrap);
      });
    });
  }
})();
