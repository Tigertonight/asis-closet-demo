(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const base = '/product-collection-admin/api';
  let authVersion = 0;
  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: 'same-origin', cache: 'no-store', ...options });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = Error(typeof data.detail === 'string' ? data.detail : response.status === 429 ? '尝试次数较多，请稍后再登录。' : '请求失败，请稍后重试。');
      error.status = response.status; throw error;
    }
    return data;
  }
  const records = window.ProductCollectionAdmin({ api, onAuthError: () => showLogin('登录已失效，请重新登录。') });
  function showLogin(message = '') {
    authVersion++; records.reset();
    $('dashboard').hidden = true; $('logout').hidden = true; $('loginPanel').hidden = false;
    $('authStatus').textContent = ''; $('loginError').textContent = message;
  }
  function showDashboard() {
    $('loginPanel').hidden = true; $('dashboard').hidden = false; $('logout').hidden = false;
    $('password').value = ''; $('loginError').textContent = ''; $('authStatus').textContent = '';
    void records.load();
  }
  $('loginForm').onsubmit = async event => {
    event.preventDefault(); if ($('loginButton').disabled) return;
    const version = ++authVersion; $('loginButton').disabled = true; $('loginButton').textContent = '正在登录…'; $('loginError').textContent = '';
    try {
      await api(base + '/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: $('password').value }) });
      if (version === authVersion) showDashboard();
    } catch (error) { if (version === authVersion) $('loginError').textContent = error.message; }
    finally { $('loginButton').disabled = false; $('loginButton').textContent = '登录'; }
  };
  $('logout').onclick = async () => {
    if ($('logout').disabled) return;
    $('logout').disabled = true;
    try { await api(base + '/logout', { method: 'POST' }); showLogin(); }
    catch { $('authStatus').textContent = '退出失败，请检查网络后重试。'; }
    finally { $('logout').disabled = false; }
  };
  async function restore() {
    const version = ++authVersion;
    try { await api(base + '/session'); if (version === authVersion) showDashboard(); }
    catch (error) { if (version === authVersion) showLogin(error.status === 401 ? '' : '暂时无法检查登录，请重试。'); }
  }
  addEventListener('pageshow', event => { if (event.persisted) { showLogin(); void restore(); } });
  void restore();
})();
