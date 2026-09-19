// Deployment-owned configuration. Launch URL/context never supplies an API origin.
((root) => {
  const baseUrl = 'https://quiz-api.librechat.online';
  async function trustedFetch(url, options = {}) {
    const target = new URL(url);
    if (target.origin !== baseUrl || target.username || target.password || !target.pathname.startsWith('/miniapp/')) {
      throw new Error('Untrusted API destination');
    }
    // A 307/308 redirect must not forward a simple-body initData payload elsewhere.
    return root.fetch(target.href, { ...options, redirect: 'error' });
  }
  root.MiniappApi = Object.freeze({ baseUrl, fetch: trustedFetch });
})(globalThis);
