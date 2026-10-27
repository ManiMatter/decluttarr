// Activity log page component. Registered via Alpine.data() for the CSP build
// of Alpine (no eval evaluator), so templates reference only bare paths. Every
// per-row derived value (formatted time, badge classes, strike display) is
// precomputed here in decorate() rather than as an inline template expression.
document.addEventListener('alpine:init', () => {
    Alpine.data('activityLog', () => ({
        items: [],
        loading: true,
        page: 1,
        totalPages: 1,
        total: 0,
        filters: {
            search: '',
            action: '',
            arr: '',
            date_from: '',
            date_to: '',
        },
        init() {
            this.loadActivity();
        },
        // Inputs bind one-way with :value (the CSP build can't do x-model's
        // write-back on nested paths), so update the filter state here and
        // reload. data-filter names which filter the control drives.
        setFilter(e) {
            this.filters[e.target.dataset.filter] = e.target.value;
            this.page = 1;
            this.loadActivity();
        },
        // Getters replace the comparison/negation expressions the CSP build
        // cannot evaluate inline (e.g. x-show="!loading").
        get notLoading() { return !this.loading; },
        get noItems() { return this.items.length === 0; },
        get hasPages() { return this.totalPages > 1; },
        get onFirstPage() { return this.page <= 1; },
        get onLastPage() { return this.page >= this.totalPages; },
        decorate(item) {
            item.timeFormatted = this.formatTime(item.timestamp);
            item.rowClass =
                item.action === 'removed' ? 'action-removed'
                : item.action === 'recovered' ? 'action-recovered'
                : '';
            item.actionBadgeClass = 'action-badge-' + item.action;
            item.hasStrikes = item.strikes !== null;
            item.strikesDisplay = item.strikes + '/' + (item.max_strikes || '?');
            return item;
        },
        async loadActivity() {
            this.loading = true;
            const params = new URLSearchParams({ page: this.page, per_page: 50 });
            if (this.filters.search) params.set('search', this.filters.search);
            if (this.filters.action) params.set('action', this.filters.action);
            if (this.filters.arr) params.set('arr', this.filters.arr);
            if (this.filters.date_from) params.set('date_from', this.filters.date_from);
            if (this.filters.date_to) params.set('date_to', this.filters.date_to);

            try {
                const res = await fetch(`${rootPath}/api/activity?${params}`);
                const data = await res.json();
                this.items = data.items.map((item) => this.decorate(item));
                this.total = data.total;
                this.totalPages = data.total_pages;
            } catch {
                this.items = [];
            }
            this.loading = false;
        },
        formatTime(ts) {
            if (!ts) return '';
            const d = new Date(ts + 'Z');
            return d.toLocaleString();
        },
        prevPage() {
            if (this.page > 1) { this.page--; this.loadActivity(); }
        },
        nextPage() {
            if (this.page < this.totalPages) { this.page++; this.loadActivity(); }
        },
    }));
});
