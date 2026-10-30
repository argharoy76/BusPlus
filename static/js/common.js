/*
 * Shared by every page. Loaded before any other script.
 *
 * CSRF protection: the server (Flask-WTF) refuses POST/PUT/DELETE requests that
 * don't carry this page's token. Instead of adding the token to every fetch()
 * call by hand, fetch() is wrapped once here to add the X-CSRFToken header to
 * every same-site request that changes something.
 */
(() => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    const token = meta ? meta.content : "";
    const SAFE_METHODS = ["GET", "HEAD", "OPTIONS"];
    const originalFetch = window.fetch.bind(window);

    window.fetch = (input, init = {}) => {
        const method = (init.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
        const url = new URL(input instanceof Request ? input.url : input, window.location.href);
        if (token && !SAFE_METHODS.includes(method) && url.origin === window.location.origin) {
            const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
            headers.set("X-CSRFToken", token);
            init = { ...init, headers, credentials: "same-origin" };
        }
        return originalFetch(input, init);
    };
})();
