(() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  window.swpFetch = (url, options = {}) => {
    const headers = new Headers(options.headers || {});
    if (csrf && !headers.has('X-CSRFToken')) headers.set('X-CSRFToken', csrf);
    if (!headers.has('Accept')) headers.set('Accept', 'application/json');
    return fetch(url, {...options, headers, credentials: 'same-origin'});
  };
  document.querySelectorAll('form[data-ajax]').forEach((form) => form.addEventListener('submit', async (event) => {
    event.preventDefault(); const response = await window.swpFetch(form.action, {method: form.method || 'POST', body: new FormData(form)}); if (!response.ok) return;
    const result = await response.json(), button = form.querySelector('button');
    if (form.dataset.ajax === 'like') { button.classList.toggle('liked', result.liked); const count = button.querySelector('span'); if (count) count.textContent = result.count; }
    if (form.dataset.ajax === 'save') button.classList.toggle('saved', result.saved);
    if (form.dataset.ajax === 'bookmark') button.textContent = result.bookmarked ? 'Saved' : 'Save';
  }));
  document.querySelectorAll('form[data-comment-form]').forEach((form) => form.addEventListener('submit', async (event) => {
    event.preventDefault(); const response = await window.swpFetch(form.action, {method:'POST', body:new FormData(form)}); if (!response.ok) return;
    const comment = await response.json(), line = document.createElement('p'), strong = document.createElement('strong'); strong.textContent = `@${comment.username}`; line.append(strong, ` ${comment.body}`); form.before(line); form.reset();
  }));
  document.querySelectorAll('[data-scroll-comments]').forEach((button) => button.addEventListener('click', () => document.querySelector(`#comments-${button.dataset.scrollComments} input`)?.focus()));
  document.querySelectorAll('[data-share-url]').forEach((button) => button.addEventListener('click', async () => { const url = button.dataset.shareUrl; if (navigator.share) await navigator.share({title:'SWP learning post',url}); else await navigator.clipboard.writeText(url); button.textContent = 'Copied'; setTimeout(() => button.textContent = '↗', 1400); }));
  const updateUnread = async () => { try { const response = await fetch('/api/unread-count'); if (!response.ok) return; const {count} = await response.json(); document.querySelectorAll('.notification-dot').forEach((dot) => dot.hidden = !count); } catch (_) {} };
  if (document.body.querySelector('.topbar')) { updateUnread(); setInterval(updateUnread, 45000); }
})();
