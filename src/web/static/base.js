// Read the proxy root path from a meta tag set in the template, then prepend it
// to every htmx request path so the UI works behind a reverse proxy with a path
// prefix. Keep this file CSP-clean: no eval, no inline data — the rendered value
// is held in the meta[name="root-path"] content attribute.
const rootPath = document.querySelector('meta[name="root-path"]')?.content || '';

document.addEventListener('htmx:configRequest', function (evt) {
    if (rootPath) {
        evt.detail.path = rootPath + evt.detail.path;
    }
});
