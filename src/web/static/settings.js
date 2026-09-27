// Settings page component. Registered via Alpine.data() for the CSP build of
// Alpine (no eval evaluator). Initial state (current config + which keys are
// overridden) is rendered server-side into data-* attributes on a hidden
// #settings-init-data element, so there is no inline JSON or inline script.
//
// The CSP evaluator only resolves bare property/method paths — no operators,
// object literals, `in`, or calls with arguments. So instead of inline
// expressions like @change="saveGeneral('timer', config.general.timer, $event)"
// the template tags each control with data-key / data-job / data-attr, and the
// generic saveField / saveJobField handlers read that context off the element.
document.addEventListener('alpine:init', () => {
    Alpine.data('settingsPage', () => {
        const dataEl = document.getElementById('settings-init-data');
        const config = JSON.parse(dataEl.dataset.config);
        const overrides = JSON.parse(dataEl.dataset.overrides);
        // Nested mirror of the flat dotted override keys so the template can
        // test x-show="ov.general.timer" as a plain dot path. Every general key
        // is defaulted to false first: the CSP evaluator warns on any path that
        // resolves to undefined, so the badge leaves must always be defined.
        const buildOv = (cfg, ovr) => {
            const ov = { general: {} };
            for (const k in cfg.general) ov.general[k] = false;
            for (const key in ovr) {
                const parts = key.split('.');
                let cur = ov;
                for (let i = 0; i < parts.length - 1; i++) {
                    cur[parts[i]] = cur[parts[i]] || {};
                    cur = cur[parts[i]];
                }
                cur[parts[parts.length - 1]] = true;
            }
            return ov;
        };
        return {
            config,
            overrides,
            ov: buildOv(config, overrides),
            message: '',
            messageError: false,
            init() {
                // Flag optional fields + derive the enabled label per job, since
                // the template cannot compute `'x' in jobConfig` or `!enabled`.
                for (const name in this.config.jobs) {
                    const j = this.config.jobs[name];
                    j.hasMaxStrikes = 'max_strikes' in j;
                    j.hasMinSpeed = 'min_speed' in j;
                    this.applyEnabledLabel(j);
                }
                this.rebuildOv();
            },
            get messageStyle() {
                return this.messageError
                    ? 'color: var(--pico-del-color)'
                    : 'color: var(--pico-ins-color)';
            },
            applyEnabledLabel(job) {
                job.enabledLabel = job.enabled ? 'enabled' : 'disabled';
                job.enabledClass = job.enabled ? 'status-enabled' : 'status-disabled';
            },
            rebuildOv() {
                this.ov = buildOv(this.config, this.overrides);
            },
            fieldValue(el) {
                if (el.type === 'checkbox') return el.checked;
                if (el.type === 'number') return el.value === '' ? null : Number(el.value);
                return el.value;
            },
            // Write a value into a dotted path on an object. Used to keep the
            // config model in sync on save: inputs bind one-way with :value /
            // :checked (the CSP build can't do x-model's write-back on nested
            // paths), so the handlers own the write instead.
            setPath(obj, path, value) {
                const parts = path.split('.');
                let cur = obj;
                for (let i = 0; i < parts.length - 1; i++) cur = cur[parts[i]];
                cur[parts[parts.length - 1]] = value;
            },
            saveField(e) {
                const key = e.target.dataset.key;
                const value = this.fieldValue(e.target);
                this.setPath(this.config, key, value);
                this.saveOverride(key, value, e);
            },
            saveJobField(e) {
                const { job, attr } = e.target.dataset;
                const value = this.fieldValue(e.target);
                this.config.jobs[job][attr] = value;
                if (attr === 'enabled') this.applyEnabledLabel(this.config.jobs[job]);
                this.saveOverride(`jobs.${job}.${attr}`, value, e);
            },
            flashEl(event, cls) {
                if (!event) return;
                const el = event.target.closest('label') || event.target;
                el.classList.remove('flash-save', 'flash-error');
                void el.offsetWidth;
                el.classList.add(cls);
                el.addEventListener('animationend', () => el.classList.remove(cls), { once: true });
            },
            async saveOverride(key, value, event) {
                try {
                    const res = await fetch(rootPath + '/api/config', {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ updates: { [key]: value } }),
                    });
                    if (res.ok) {
                        this.overrides[key] = value;
                        this.rebuildOv();
                        this.flashEl(event, 'flash-save');
                    } else {
                        this.flashEl(event, 'flash-error');
                    }
                } catch {
                    this.flashEl(event, 'flash-error');
                }
            },
            async resetOverrides() {
                if (!confirm('Reset all runtime overrides to YAML defaults? This will reload settings from config file.')) return;
                try {
                    const res = await fetch(rootPath + '/api/config/reload', { method: 'POST' });
                    if (res.ok) {
                        this.overrides = {};
                        this.rebuildOv();
                        this.showMessage('Reset to defaults');
                        setTimeout(() => location.reload(), 500);
                    }
                } catch {
                    this.showMessage('Error resetting', true);
                }
            },
            showMessage(msg, error = false) {
                this.message = msg;
                this.messageError = error;
                setTimeout(() => this.message = '', 3000);
            },
        };
    });
});
