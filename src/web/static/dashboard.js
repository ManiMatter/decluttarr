// Protect / unprotect button handlers — delegated from document so they
// keep working after htmx swaps the queue table partial.
document.addEventListener('click', function (e) {
    var btn = e.target.closest('.btn-protect');
    if (btn) {
        btn.disabled = true;
        btn.setAttribute('aria-busy', 'true');
        fetch(rootPath + '/api/protected/' + encodeURIComponent(btn.dataset.downloadId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: btn.dataset.title, arr_name: btn.dataset.arrName }),
        }).then(function () {
            htmx.trigger('#queue-container', 'refresh');
        }).finally(function () {
            btn.disabled = false;
            btn.removeAttribute('aria-busy');
        });
        return;
    }
    var ubtn = e.target.closest('.btn-unprotect');
    if (ubtn) {
        fetch(rootPath + '/api/protected/' + encodeURIComponent(ubtn.dataset.downloadId), {
            method: 'DELETE',
        }).then(function () { htmx.trigger('#queue-container', 'refresh'); });
    }
});

// Dashboard root component. Registered via Alpine.data() (not a global factory)
// so it works with the CSP build of Alpine, which has no eval-based evaluator.
// Templates therefore reference only bare property/method names — any derived
// value or event handler lives here in JS.
document.addEventListener('alpine:init', () => {
    Alpine.data('dashboard', () => ({
        triggering: false,
        message: '',
        evtSource: null,
        init() {
            this.evtSource = new EventSource(rootPath + '/api/events');
            this.evtSource.addEventListener('item_removed', () => {
                htmx.trigger('#queue-container', 'refresh');
                htmx.trigger('#activity-feed', 'refresh');
            });
            this.evtSource.addEventListener('item_flagged', () => {
                htmx.trigger('#queue-container', 'refresh');
            });
            this.evtSource.addEventListener('strike_applied', () => {
                htmx.trigger('#queue-container', 'refresh');
            });
            this.evtSource.addEventListener('cycle_end', () => {
                htmx.trigger('#queue-container', 'refresh');
                htmx.trigger('#activity-feed', 'refresh');
            });
            this.evtSource.onerror = () => {
                // EventSource auto-reconnects; no action needed
            };
        },
        destroy() {
            if (this.evtSource) this.evtSource.close();
        },
        async triggerCycle() {
            this.triggering = true;
            this.message = '';
            try {
                const res = await fetch(rootPath + '/api/trigger', { method: 'POST' });
                const data = await res.json();
                this.message = data.status === 'triggered' ? 'Cycle triggered!' : 'Could not trigger';
            } catch {
                this.message = 'Error triggering cycle';
            }
            this.triggering = false;
            setTimeout(() => this.message = '', 3000);
        },
        async toggleTestRun() {
            try {
                const res = await fetch(rootPath + '/api/config/test-run', { method: 'POST' });
                const data = await res.json();
                this.message = `Test Run: ${data.test_run ? 'ON' : 'OFF'}`;
                htmx.trigger('[hx-get="/partials/status-bar"]', 'refresh');
            } catch {
                this.message = 'Error toggling test run';
            }
            setTimeout(() => this.message = '', 3000);
        },
    }));
});
