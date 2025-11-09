// Simple auth guard and logout helper for Jobly pages (empresa side)
// - Verifies session via /api/me
// - Exposes window.currentUser
// - Provides window.handleLogout() to end session and redirect

(function () {
  async function checkAuth() {
    try {
      const res = await fetch('/api/me', { method: 'GET' });
      if (!res.ok) {
        // If not authenticated, go to login
        if (res.status === 401) {
          window.location.href = '/login';
          return null;
        }
        throw new Error('Auth check failed');
      }
      const data = await res.json();
      // Expected: { authenticated: true, user: { id, email, rol, nombre? } }
      if (data && data.user) {
        window.currentUser = data.user;
      }
      return data?.user ?? null;
    } catch (err) {
      console.error('Error during auth check:', err);
      // Fallback to login if something goes wrong
      try { window.location.href = '/login'; } catch (_) {}
      return null;
    }
  }

  async function doLogout() {
    try {
      await fetch('/api/logout', { method: 'POST' });
    } catch (_) {
      // ignore network errors; still clear local state
    }
    try {
      // Clear any legacy/local user hints
      localStorage.removeItem('jobly_user');
      localStorage.removeItem('authEmail');
      localStorage.removeItem('employerRegistration');
      localStorage.removeItem('ultimaVacanteId');
    } catch (_) {}
    window.location.href = '/login';
  }

  // Expose for buttons
  window.handleLogout = doLogout;

  // Wire up on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    // Attach to a button if present
    const btn = document.getElementById('logoutBtn');
    if (btn) btn.addEventListener('click', (e) => { e.preventDefault(); doLogout(); });

    // Run the auth guard for protected pages (most empresa pages)
    // If a page is truly public, it can opt-out by setting window.SKIP_AUTH_GUARD = true;
    if (!window.SKIP_AUTH_GUARD) {
      checkAuth();
    }
  });
})();
