/* ============================================
   ChankArts Music Academy — Learning Portal
   Student / Parent / Faculty experience
   ============================================ */

const Portal = (function () {
    'use strict';

    // API origin: window.CHANKARTS_API_BASE overrides everything (set it in
    // index.html when the API lives on a different origin), then local
    // development default, then same-origin production (proxied /api/*).
    const BASE = (window.CHANKARTS_API_BASE !== undefined
        ? window.CHANKARTS_API_BASE
        : (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
            ? 'http://localhost:8000'
            : '')) + '/api/v1';

    const state = {
        section: 'dashboard',
        me: null,
        role: null,
        dashboard: null,
        enrollments: [],
        activeStudentId: null,
        sessions: [],
        assignments: [],
        materials: [],
        reports: [],
        syllabi: [],
        progress: null,
        exams: [],
        milestones: [],
        invoices: [],
        payments: [],
        packages: [],
        paymentConfig: null,
        resources: [],
        notifications: [],
        children: [],
        loading: false,
        error: null,
        calMonth: null,      // Date for the first of the visible month
        classView: 'month',
        calSelected: null,   // ISO date of the day tapped on the calendar
        billingTab: 'statement',
        assignmentTab: 'current',
        materialFilter: 'all',
        resourceTab: 'books',
        notifOpen: false,
        sidebarOpen: false,
    };

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------
    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function token() {
        return localStorage.getItem('academy_token');
    }

    function storedUser() {
        try { return JSON.parse(localStorage.getItem('academy_user') || '{}'); } catch (e) { return {}; }
    }

    async function api(path, options = {}) {
        const headers = Object.assign(
            { 'Content-Type': 'application/json' },
            token() ? { Authorization: 'Bearer ' + token() } : {},
            options.headers || {}
        );
        if (options.body instanceof FormData) {
            delete headers['Content-Type'];
        }
        const response = await fetch(BASE + path, Object.assign({}, options, { headers }));
        if (response.status === 401) {
            localStorage.removeItem('academy_token');
            localStorage.removeItem('academy_user');
            window.location.href = window.AppPath('/academy/login');
            throw new Error('Session expired');
        }
        if (!response.ok) {
            let detail = 'Request failed';
            try {
                const body = await response.json();
                detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || detail);
            } catch (e) { /* ignore */ }
            if (detail === 'PIN_CHANGE_REQUIRED') {
                try {
                    const u = JSON.parse(localStorage.getItem('academy_user') || '{}');
                    u.must_change_pin = true;
                    localStorage.setItem('academy_user', JSON.stringify(u));
                } catch (e) { /* ignore */ }
                window.location.reload();
            }
            const err = new Error(detail);
            err.status = response.status;
            throw err;
        }
        if (response.status === 204) return null;
        return response.json();
    }

    function fmtPaise(paise) {
        if (paise == null) return '—';
        const rupees = paise / 100;
        return '₹' + rupees.toLocaleString('en-IN', { maximumFractionDigits: rupees % 1 ? 2 : 0 });
    }

    function parseDate(value) {
        if (!value) return null;
        const parts = String(value).slice(0, 10).split('-');
        return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    }

    const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const MON = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

    function fmtDay(value) {
        const d = parseDate(value);
        if (!d) return '—';
        return DOW[d.getDay()] + ', ' + d.getDate() + ' ' + MON[d.getMonth()].slice(0, 3);
    }

    function fmtLong(value) {
        const d = typeof value === 'string' ? parseDate(value) : value;
        if (!d) return '—';
        return DOW[d.getDay()] + ', ' + d.getDate() + ' ' + MON[d.getMonth()] + ' ' + d.getFullYear();
    }

    function monthLabel(ym) {
        if (!ym) return '';
        const bits = ym.split('-');
        return MON[Number(bits[1]) - 1] + ' ' + bits[0];
    }

    function initials(name) {
        if (!name) return 'CA';
        return name.trim().split(/\s+/).slice(0, 2).map(function (p) { return p[0]; }).join('').toUpperCase();
    }

    function badge(status) {
        const label = {
            scheduled: 'Scheduled', completed: 'Completed', rescheduled: 'Rescheduled',
            absent: 'Absent',
            rescheduling_required: 'Reschedule Pending',
            cancelled: 'Cancelled', paid: 'Paid', pending: 'Pending', partially_paid: 'Partially Paid',
            void: 'Void', assigned: 'Assigned', submitted: 'Submitted', reviewed: 'Reviewed',
            revision_requested: 'Revision Requested', draft: 'Draft', approved: 'Approved',
            rejected: 'Rejected', needs_information: 'Needs Info', overdue: 'Overdue',
            failed: 'Failed', in_progress: 'In Progress', not_started: 'Not Started',
        }[status] || status;
        return '<span class="badge badge--' + esc(status) + '"><span class="badge__dot"></span>' + esc(label) + '</span>';
    }

    function toast(message, kind) {
        const old = document.querySelector('.toast-p');
        if (old) old.remove();
        const el = document.createElement('div');
        el.className = 'toast-p' + (kind === 'error' ? ' toast-p--error' : '');
        el.textContent = message;
        document.body.appendChild(el);
        setTimeout(function () { el.remove(); }, 3600);
    }

    function emptyState(icon, text) {
        return '<div class="empty-p"><div class="empty-p__icon">' + icon + '</div>' + esc(text) + '</div>';
    }

    function loadingState(text) {
        return '<div class="loading-p"><span class="spinner"></span>' + esc(text || 'Loading…') + '</div>';
    }

    async function downloadFile(storedName, filename) {
        try {
            const response = await fetch(BASE + '/learning/files/' + encodeURIComponent(storedName), {
                headers: { Authorization: 'Bearer ' + token() },
            });
            if (!response.ok) throw new Error('Download failed');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename || storedName;
            document.body.appendChild(a);
            a.click();
            a.remove();
            setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
        } catch (err) {
            toast(err.message, 'error');
        }
    }

    // ------------------------------------------------------------------
    // Navigation model
    // ------------------------------------------------------------------
    const NAV_STUDENT = [
        { section: 'dashboard', label: 'Dashboard', icon: '⌂' },
        { section: 'classes', label: 'My Classes', icon: '🗓' },
        { section: 'billing', label: 'Payments & Billing', icon: '₹' },
        { section: 'assignments', label: 'Assignments', icon: '✎' },
        { section: 'materials', label: 'Study Material', icon: '◫' },
        { section: 'reports', label: 'Monthly Reports', icon: '☰' },
        { section: 'syllabus', label: 'Syllabus & Progress', icon: '✓' },
        { section: 'exams', label: 'Exams & Milestones', icon: '♛' },
        { section: 'achievements', label: 'Achievements', icon: '🏆' },
        { section: 'resources', label: 'Resources', icon: '◈' },
        { section: 'remarks', label: 'Remarks', icon: '💬' },
        { divider: true },
        { section: 'profile', label: 'My Profile', icon: '◐' },
        { section: 'help', label: 'Help & Support', icon: '?' },
    ];

    const NAV_FACULTY = [
        { section: 'dashboard', label: 'Dashboard', icon: '⌂' },
        { section: 'classes', label: 'Class Schedule', icon: '🗓' },
        { section: 'assignments', label: 'Assignments', icon: '✎' },
        { section: 'materials', label: 'Study Material', icon: '◫' },
        { section: 'reports', label: 'Monthly Reports', icon: '☰' },
        { section: 'syllabus', label: 'Syllabus & Progress', icon: '✓' },
        { section: 'exams', label: 'Exams & Milestones', icon: '♛' },
        { section: 'resources', label: 'Resources', icon: '◈' },
        { divider: true },
        { section: 'profile', label: 'My Profile', icon: '◐' },
        { section: 'help', label: 'Help & Support', icon: '?' },
    ];

    function navItems() {
        return state.role === 'instructor' ? NAV_FACULTY : NAV_STUDENT;
    }

    function isFaculty() {
        return state.role === 'instructor';
    }

    function sectionFromPath() {
        const canonical = window.AppCanonical(window.location.pathname);
        const match = canonical.match(/^\/academy\/portal\/?([^/?]*)/);
        const section = match && match[1] ? match[1] : 'dashboard';
        return navItems().some(function (n) { return n.section === section; }) ? section : 'dashboard';
    }

    function go(section) {
        const path = '/academy/portal/' + section;
        if (window.AppCanonical(window.location.pathname) !== path) {
            window.history.pushState({}, '', window.AppPath(path));
        }
        state.section = section;
        state.sidebarOpen = false;
        render();
    }

    // ------------------------------------------------------------------
    // Shell
    // ------------------------------------------------------------------
    function renderSidebar() {
        const items = navItems().map(function (item) {
            if (item.divider) return '<div class="portal-nav__label">Account</div>';
            let badgeHtml = '';
            if (item.section === 'assignments' && state.dashboard && state.dashboard.pending_assignments) {
                badgeHtml = '<span class="portal-nav__badge">' + state.dashboard.pending_assignments + '</span>';
            }
            return '' +
                '<button class="portal-nav__link' + (state.section === item.section ? ' portal-nav__link--active' : '') + '" ' +
                'data-portal-nav="' + item.section + '">' +
                '<span class="portal-nav__icon">' + item.icon + '</span>' +
                '<span>' + item.label + '</span>' + badgeHtml +
                '</button>';
        }).join('');

        return '' +
            '<aside class="portal-sidebar' + (state.sidebarOpen ? ' portal-sidebar--open' : '') + '" id="portalSidebar">' +
            '<div class="portal-sidebar__brand">' +
            '<img src="assets/ChankArts Music Academy.png" alt="">' +
            '<span class="portal-sidebar__brand-text">' +
            '<span class="portal-sidebar__brand-name">CHANKARTS</span>' +
            '<span class="portal-sidebar__brand-tag">Music Academy</span>' +
            '</span></div>' +
            '<nav class="portal-nav">' + items + '</nav>' +
            '<div class="portal-nav">' +
            '<button class="portal-nav__link" data-portal-logout>' +
            '<span class="portal-nav__icon">⏻</span><span>Logout</span></button>' +
            '</div>' +
            '</aside>';
    }

    function renderTopbar() {
        const me = state.me || {};
        let name = storedUser().name || '';
        let sub = '';
        if (state.role === 'student' && me.student) {
            name = me.student.full_name;
            sub = me.student.cma_registration_id || '';
        } else if (state.role === 'instructor' && me.instructor) {
            name = me.instructor.name || name;
            sub = 'Faculty';
        } else if (state.role === 'parent') {
            name = name || 'Guardian';
            sub = 'Parent account';
        }
        const unread = state.notifications.filter(function (n) { return !n.read; }).length;
        const crumb = (navItems().find(function (n) { return n.section === state.section; }) || {}).label || 'Dashboard';

        const notifPanel = state.notifOpen
            ? '<div class="notif-p" id="notifPanel">' +
              (state.notifications.length
                  ? state.notifications.slice(0, 12).map(function (n) {
                        return '<div class="notif-p__item">' + esc(n.title) +
                            (n.body ? '<br><small style="color:var(--text-2)">' + esc(n.body) + '</small>' : '') +
                            '<time>' + esc(n.created_at ? new Date(n.created_at).toLocaleString('en-IN') : '') + '</time></div>';
                    }).join('')
                  : '<div class="notif-p__item">No notifications yet</div>') +
              '</div>'
            : '';

        return '' +
            '<header class="portal-topbar">' +
            '<div class="portal-topbar__left">' +
            '<button class="portal-menu-btn" data-portal-menu aria-label="Menu">☰</button>' +
            '<a class="portal-topbar__logo" href="/academy/portal" data-portal-home>' +
            '<img src="assets/ChankArts Music Academy.png" alt="">' +
            '<span class="portal-topbar__wordmark">ChankArts</span></a>' +
            '<span class="portal-topbar__crumb">' + esc(crumb) + '</span>' +
            '</div>' +
            '<div class="portal-topbar__right" style="position:relative">' +
            '<button class="portal-bell" data-portal-notif aria-label="Notifications">🔔' +
            (unread ? '<span class="portal-bell__dot"></span>' : '') + '</button>' +
            notifPanel +
            '<div class="portal-user">' +
            '<span class="portal-avatar">' + esc(initials(name)) + '</span>' +
            '<span class="portal-user__meta">' +
            '<span class="portal-user__name">' + esc(name) + '</span>' +
            '<span class="portal-user__id">' + esc(sub) + '</span>' +
            '</span></div>' +
            '</div>' +
            '</header>';
    }

    // ------------------------------------------------------------------
    // Section: Dashboard
    // ------------------------------------------------------------------
    async function loadDashboard() {
        if (isFaculty()) {
            const results = await Promise.all([
                api('/sessions?limit=200'),
                api('/sessions/stats/monthly'),
                api('/learning/assignments?status=submitted'),
                api('/portal/enrollments'),
            ]);
            state.sessions = results[0];
            state.facultyStats = results[1];
            state.pendingReviews = results[2];
            state.enrollments = results[3];
            return;
        }
        state.dashboard = await api('/portal/dashboard' + (state.activeStudentId ? '?student_id=' + state.activeStudentId : ''));
        // Sessions feed the dashboard calendar's day marks (current ±1 month)
        const achSid = state.activeStudentId ||
            (state.role === 'student' && state.me && state.me.student ? state.me.student.id : null);
        const extra = await Promise.all([
            api('/sessions?date_from=' + ymOf(new Date(), -1) + '&date_to=' + ymOf(new Date(), 1) + '&limit=300'),
            achSid
                ? api('/portal/achievements?student_id=' + achSid)
                : Promise.resolve(state.achievements || []),
        ]);
        state.sessions = extra[0];
        state.achievements = extra[1];
    }

    function renderFacultyDashboard() {
        const upcoming = state.sessions
            .filter(function (s) { return s.status === 'scheduled' && s.scheduled_date >= todayIso(); })
            .sort(function (a, b) { return (a.scheduled_date + a.scheduled_start) < (b.scheduled_date + b.scheduled_start) ? -1 : 1; })
            .slice(0, 6);
        const stats = state.facultyStats || {};
        const students = state.enrollments.length;
        const pending = (state.pendingReviews || []).length;
        const name = (state.me.instructor && state.me.instructor.name) || 'Faculty';

        return '' +
            '<div class="welcome">' +
            '<div class="welcome__left">' +
            '<span class="welcome__photo">' + esc(initials(name)) + '</span>' +
            '<div>' +
            '<h1 class="welcome__title">Welcome, ' + esc(name) + '! 🎵</h1>' +
            '<p class="welcome__meta"><strong>' + esc(String(students)) + ' active students</strong> · ' + esc(monthLabel(todayYm())) + '</p>' +
            '<p class="welcome__quote">“Teaching is the art of helping others hear what is already inside them.”</p>' +
            '</div></div>' +
            '<div class="welcome__progress">' +
            '<div class="welcome__progress-label"><span>' + esc(monthLabel(todayYm())) + ' Progress</span>' +
            '<strong>' + (stats.completed || 0) + ' completed</strong></div>' +
            '<p class="welcome__progress-sub">' + (stats.completed || 0) + ' of ' +
            ((stats.completed || 0) + (stats.scheduled || 0)) + ' classes this month</p>' +
            '<div class="progress"><div class="progress__bar" style="width:' + progressPct(stats.completed, stats.completed + stats.scheduled) + '%"></div></div>' +
            '</div></div>' +

            '<div class="grid grid--stats" style="margin-top:16px">' +
            statCard('ok', '✓', stats.completed || 0, 'Classes Completed') +
            statCard('wait', '🗓', stats.scheduled || 0, 'Classes Scheduled') +
            statCard('alert', '⟳', stats.rescheduling_required || 0, 'Reschedule Pending') +
            statCard('fee', '✎', pending, 'Submissions to Review') +
            '</div>' +

            '<div class="grid grid--main" style="margin-top:16px">' +
            '<div class="card">' +
            '<div class="card__head"><h3 class="card__title">Upcoming Classes</h3>' +
            '<button class="card__link" data-portal-nav="classes">View All →</button></div>' +
            (upcoming.length
                ? '<div class="list">' + upcoming.map(sessionRow).join('') + '</div>'
                : emptyState('🗓', 'No upcoming classes scheduled yet.')) +
            '</div>' +
            '<div class="card">' + renderCalendar() + '</div>' +
            '</div>' +

            '<div class="card">' +
            '<div class="card__head"><h3 class="card__title">My Students</h3></div>' +
            (state.enrollments.length
                ? '<div class="list">' + state.enrollments.map(function (e) {
                    return '<div class="list__row">' +
                        '<span class="portal-avatar">' + esc(initials(e.student_name)) + '</span>' +
                        '<div class="list__body"><div class="list__title">' + esc(e.student_name) + '</div>' +
                        '<div class="list__sub">' + esc(e.programme_name) + ' · ' + esc(e.cma_registration_id || '') + '</div></div>' +
                        '<div class="list__actions">' + badge(e.status) + '</div></div>';
                }).join('') + '</div>'
                : emptyState('🎓', 'No students assigned yet.')) +
            '</div>';
    }

    function statCard(kind, icon, value, label) {
        return '<div class="stat stat--' + kind + '">' +
            '<span class="stat__icon">' + icon + '</span>' +
            '<div><div class="stat__value">' + esc(String(value)) + '</div>' +
            '<div class="stat__label">' + esc(label) + '</div></div></div>';
    }

    function progressPct(done, total) {
        if (!total) return 0;
        return Math.min(100, Math.round((done / total) * 100));
    }

    function todayIso() {
        const d = new Date();
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    }

    function todayYm() {
        return todayIso().slice(0, 7);
    }

    const RESCHEDULE_POLICY_TEXT = 'Rescheduling requests must be made at least 24 hours before the class ' +
        'start time. Inside 24 hours, please contact the academy directly.';

    function hoursUntilSession(s) {
        // class start in the academy timezone (Asia/Kolkata, fixed +05:30)
        const startMs = Date.parse(s.scheduled_date + 'T' + s.scheduled_start + ':00+05:30');
        return (startMs - Date.now()) / 3600000;
    }

    function sessionRow(s) {
        return '<div class="list__row">' +
            '<div class="list__date">' + esc(fmtDay(s.scheduled_date)) + '</div>' +
            '<div class="list__body">' +
            '<div class="list__title">' + esc(s.scheduled_start) + ' – ' + esc(s.scheduled_end) + '</div>' +
            '<div class="list__sub">' + esc(s.programme || (s.is_online ? 'Online class' : 'Academy class')) +
            (s.location ? ' · ' + esc(s.location) : '') + '</div></div>' +
            '<div class="list__actions">' + badge(s.status) + '</div></div>';
    }

    function achievementsStrip() {
        const list = (state.achievements || []).slice(0, 3);
        if (!list.length) return '';
        return '<div class="card"><div class="card__head"><h3 class="card__title">Achievements</h3>' +
            '<button class="btn-p btn-p--sm btn-p--ghost" data-action="go-achievements">View all</button></div>' +
            '<div style="display:flex;gap:12px;flex-wrap:wrap;padding:0 16px 14px">' +
            list.map(function (a) {
                return '<div style="flex:1;min-width:180px;border:1px solid var(--line);border-radius:10px;padding:12px">' +
                    '<div style="font-size:22px">' + (ACHIEVEMENT_ICONS[a.category] || '🏆') + '</div>' +
                    '<div style="font-weight:600;font-size:13px;margin-top:4px">' + esc(a.title) + '</div>' +
                    (a.result ? '<div style="font-size:11px;color:var(--text-2);margin-top:2px">' + esc(a.result) + '</div>' : '') +
                    '</div>';
            }).join('') + '</div></div>';
    }

    function renderStudentDashboard() {
        const d = state.dashboard;
        if (!d) return loadingState();
        const student = d.student || {};
        const enrol = (d.enrollments && d.enrollments[0]) || {};
        const month = d.month_summary || {};
        const total = (month.completed || 0) + (month.scheduled || 0);
        const pct = progressPct(month.completed, total);
        const fee = d.fee;
        const report = d.latest_report;
        const syllabus = d.syllabus || {};

        const childrenSwitch = state.role === 'parent' && state.children.length > 1
            ? '<div class="child-switch">' + state.children.map(function (c) {
                return '<button data-child="' + esc(c.id) + '"' + (c.id === state.activeStudentId ? ' class="active"' : '') + '>' +
                    esc(c.first_name) + '</button>';
            }).join('') + '</div>'
            : '';

        return childrenSwitch + achievementsStrip() +
            '<div class="welcome">' +
            '<div class="welcome__left">' +
            '<span class="welcome__photo">' + esc(initials(student.full_name)) + '</span>' +
            '<div>' +
            '<h1 class="welcome__title">Welcome, ' + esc(student.full_name || 'Student') + '! 🎵</h1>' +
            '<p class="welcome__meta"><strong>' + esc(student.cma_registration_id || '') + '</strong>' +
            (enrol.programme_name ? ' | ' + esc(enrol.programme_name) : '') +
            (enrol.instructor ? ' | Faculty: ' + esc(enrol.instructor) : '') + '</p>' +
            '<p class="welcome__quote">“Consistent practice turns effort into artistry.”</p>' +
            '</div></div>' +
            '<div class="welcome__progress">' +
            '<div class="welcome__progress-label"><span>' + esc(monthLabel(d.month)) + ' Progress</span>' +
            '<strong>' + pct + '%</strong></div>' +
            '<p class="welcome__progress-sub">' + (month.completed || 0) + ' of ' + total + ' classes completed</p>' +
            '<div class="progress"><div class="progress__bar" style="width:' + pct + '%"></div></div>' +
            '</div></div>' +

            '<div class="grid grid--stats" style="margin-top:16px">' +
            statCard('ok', '✓', month.completed || 0, 'Classes Completed') +
            statCard('wait', '🗓', month.scheduled || 0, 'Classes Scheduled') +
            statCard('alert', '⟳', month.rescheduling_required || 0, 'Reschedule Pending') +
            statCard('fee', '₹', fee ? fmtPaise(fee.amount_paid_paise) : '—',
                fee && fee.status === 'paid' ? monthLabel(d.month) + ' Fee Paid'
                    : fee ? monthLabel(d.month) + ' Fee Due' : 'No Fee Issued') +
            '</div>' +

            '<div class="grid grid--main" style="margin-top:16px">' +
            '<div class="card">' +
            '<div class="card__head"><h3 class="card__title">Upcoming Classes</h3>' +
            '<button class="card__link" data-portal-nav="classes">View All →</button></div>' +
            (d.upcoming_classes && d.upcoming_classes.length
                ? '<div class="list">' + d.upcoming_classes.map(function (s) {
                    return '<div class="list__row">' +
                        '<div class="list__date">' + esc(fmtDay(s.date)) + '</div>' +
                        '<div class="list__body"><div class="list__title">' + esc(s.start) + ' – ' + esc(s.end) + '</div>' +
                        '<div class="list__sub">' + esc(s.programme || 'Class') + '</div></div>' +
                        '<div class="list__actions">' + badge(s.status) + '</div></div>';
                }).join('') + '</div>'
                : emptyState('🗓', 'No upcoming classes yet.')) +
            '</div>' +
            '<div class="card">' + renderCalendar() + '</div>' +
            '</div>' +

            '<div class="grid grid--tiles" style="margin-top:16px">' +
            tile('♛', 'Next Exam', d.upcoming_exams && d.upcoming_exams.length
                ? (d.upcoming_exams[0].board + ' Grade ' + (d.upcoming_exams[0].grade || '—')) : 'None scheduled', 'exams') +
            tile('✎', 'Assignments', d.pending_assignments ? d.pending_assignments + ' Pending' : 'All clear', 'assignments') +
            tile('◫', 'Study Material', state.materials.length + ' Resources', 'materials') +
            tile('☰', 'Monthly Report', report ? monthLabel(report.report_month) : 'No report yet', 'reports') +
            '</div>' +

            '<div class="grid grid--2" style="margin-top:16px">' +
            '<div class="card">' +
            '<div class="card__head"><h3 class="card__title">Monthly Report</h3>' +
            (report ? '<button class="card__link" data-portal-nav="reports">View Full Report →</button>' : '') + '</div>' +
            (report
                ? '<div class="report__block"><h4>Progress Summary</h4><p>' + esc(report.progress_summary || '—') + '</p></div>' +
                  '<div class="report__block" style="margin-top:12px"><h4>Next Month Focus</h4><p>' + esc(report.next_month_focus || '—') + '</p></div>'
                : emptyState('☰', 'No published report for this month yet.')) +
            '</div>' +
            '<div class="card">' +
            '<div class="card__head"><h3 class="card__title">Syllabus & Progress</h3>' +
            '<button class="card__link" data-portal-nav="syllabus">Open →</button></div>' +
            (syllabus.total
                ? '<p class="welcome__progress-sub">' + syllabus.completed + ' of ' + syllabus.total + ' topics completed</p>' +
                  '<div class="progress"><div class="progress__bar" style="width:' + (syllabus.percent || 0) + '%"></div></div>' +
                  '<p style="margin-top:10px;font-weight:700;color:var(--text)">' + (syllabus.percent || 0) + '% complete</p>'
                : emptyState('✓', 'Syllabus progress will appear once faculty updates it.')) +
            '</div>' +
            '</div>';
    }

    function tile(icon, label, value, section) {
        return '<button class="tile" data-portal-nav="' + section + '">' +
            '<span class="tile__icon">' + icon + '</span>' +
            '<span class="tile__label">' + esc(label) + '</span>' +
            '<span class="tile__value">' + esc(value) + '</span></button>';
    }

    // ------------------------------------------------------------------
    // Calendar
    // ------------------------------------------------------------------
    function renderCalendar() {
        const anchor = state.calMonth || (function () {
            const now = new Date();
            return new Date(now.getFullYear(), now.getMonth(), 1);
        })();

        const year = anchor.getFullYear();
        const month = anchor.getMonth();
        const firstDow = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const prevDays = new Date(year, month, 0).getDate();

        const dayStatus = {};
        state.sessions.forEach(function (s) {
            if (!s.scheduled_date) return;
            const key = Number(s.scheduled_date.slice(8, 10));
            const cur = dayStatus[key];
            if (s.status === 'completed') dayStatus[key] = 'completed';
            else if (s.status === 'rescheduling_required' && cur !== 'completed') dayStatus[key] = 'rescheduling';
            else if (s.status === 'scheduled' && !cur) dayStatus[key] = 'scheduled';
        });

        let cells = '';
        for (let i = firstDow - 1; i >= 0; i--) {
            cells += '<div class="cal__day cal__day--muted">' + (prevDays - i) + '</div>';
        }
        const today = new Date();
        const isoOf = function (y, m, d) {
            return y + '-' + String(m + 1).padStart(2, '0') + '-' + String(d).padStart(2, '0');
        };
        for (let day = 1; day <= daysInMonth; day++) {
            const classes = dayStatus[day] ? ' cal__day--' + dayStatus[day] : '';
            const isToday = today.getDate() === day && today.getMonth() === month && today.getFullYear() === year;
            const iso = isoOf(year, month, day);
            const isSelected = state.calSelected === iso;
            cells += '<div class="cal__day' + (isToday ? ' cal__day--today' : '') +
                (isSelected ? ' cal__day--selected' : '') + classes +
                '" data-cal-day="' + iso + '">' + day + '</div>';
        }
        const totalCells = firstDow + daysInMonth;
        for (let i = 1; i <= (7 - (totalCells % 7)) % 7; i++) {
            cells += '<div class="cal__day cal__day--muted">' + i + '</div>';
        }

        return '' +
            '<div class="cal__head">' +
            '<button class="cal__nav" data-cal-prev aria-label="Previous month">‹</button>' +
            '<span class="cal__month">' + MON[month] + ' ' + year + '</span>' +
            '<button class="cal__nav" data-cal-next aria-label="Next month">›</button>' +
            '</div>' +
            '<div class="cal__grid">' +
            DOW.map(function (d) { return '<div class="cal__dow">' + d[0] + '</div>'; }).join('') +
            cells +
            '</div>' +
            '<div class="cal__legend">' +
            '<span><i style="background:var(--success)"></i>Completed</span>' +
            '<span><i style="background:var(--scheduled-fg)"></i>Scheduled</span>' +
            '<span><i style="background:var(--danger)"></i>Reschedule</span>' +
            '</div>' +
            (function () {
                if (!state.calSelected) return '';
                const dayRows = state.sessions
                    .filter(function (s) { return s.scheduled_date === state.calSelected; })
                    .sort(function (a, b) { return a.scheduled_start < b.scheduled_start ? -1 : 1; });
                const head = '<div class="cal__selected-head">Selected: ' +
                    esc(fmtDay(state.calSelected)) + '</div>';
                if (!dayRows.length) {
                    return '<div class="cal__day-detail">' + head +
                        '<span class="cal__detail-empty">No class scheduled on this date.</span></div>';
                }
                return '<div class="cal__day-detail">' + head + dayRows.map(function (s) {
                    return '<div class="cal__detail-row">' +
                        '<strong>' + esc(s.scheduled_start) + ' – ' + esc(s.scheduled_end) + '</strong>' +
                        '<span>' + esc(s.is_online ? 'Online class' : (s.location || 'Academy class')) + '</span>' +
                        badge(s.status) + '</div>';
                }).join('') + '</div>';
            })();
    }

    // ------------------------------------------------------------------
    // Section: Classes
    // ------------------------------------------------------------------
    async function loadClasses() {
        const from = state.calMonth
            ? ymOf(state.calMonth, -1) : ymOf(new Date(), -1);
        const to = state.calMonth
            ? ymOf(state.calMonth, 1) : ymOf(new Date(), 1);
        state.sessions = await api('/sessions?date_from=' + from + '&date_to=' + to + '&limit=300');
    }

    function ymOf(date, offset) {
        const d = new Date(date.getFullYear(), date.getMonth() + offset, 1);
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-01';
    }

    function renderClasses() {
        const now = new Date();
        const monthSessions = state.sessions
            .filter(function (s) { return s.scheduled_date.slice(0, 7) === todayYm(); })
            .sort(function (a, b) { return (a.scheduled_date + a.scheduled_start) < (b.scheduled_date + b.scheduled_start) ? -1 : 1; });

        // Current week (Mon–Sun) containing today
        const weekSessions = (function () {
            const t = new Date();
            const dow = (t.getDay() + 6) % 7; // Monday = 0
            const wkStart = new Date(t.getFullYear(), t.getMonth(), t.getDate() - dow);
            const wkEnd = new Date(wkStart.getFullYear(), wkStart.getMonth(), wkStart.getDate() + 6);
            const iso = function (d) {
                return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') +
                    '-' + String(d.getDate()).padStart(2, '0');
            };
            return state.sessions
                .filter(function (s) { return s.scheduled_date >= iso(wkStart) && s.scheduled_date <= iso(wkEnd); })
                .sort(function (a, b) { return (a.scheduled_date + a.scheduled_start) < (b.scheduled_date + b.scheduled_start) ? -1 : 1; });
        })();

        let list;
        if (state.classView === 'list') {
            list = state.sessions.slice().sort(function (a, b) { return a.scheduled_date < b.scheduled_date ? 1 : -1; });
        } else if (state.classView === 'week') {
            list = weekSessions;
        } else {
            list = monthSessions;
        }
        const periodLabel = state.classView === 'week' ? 'This Week'
            : state.classView === 'list' ? 'Upcoming & Recent'
            : 'This Month';

        const actions = isFaculty()
            ? '<button class="btn-p btn-p--auto btn-p--sm" data-action="new-session">＋ New Session</button>'
            : '';

        const sessionList = list.length
            ? '<div class="list">' + list.map(function (s) {
                let facultyActions = '';
                // 24-hour notice policy: new reschedule requests close when the
                // class is less than 24h away; an existing request can still be
                // updated (it was submitted on time).
                const within24h = hoursUntilSession(s) < 24;
                const policyNote = within24h
                    ? '<div class="list__sub" style="color:var(--muted);font-size:11.5px;margin-top:6px">' +
                      esc(RESCHEDULE_POLICY_TEXT) + '</div>'
                    : '';
                const disabledAttr = ' disabled title="Rescheduling requests must be made at least 24 hours in advance"';
                if (isFaculty()) {
                    facultyActions = '<div class="btn-row" style="margin-top:8px">';
                    if (s.status === 'scheduled') {
                        facultyActions += '<button class="btn-p btn-p--sm" data-action="complete-session" data-id="' + s.id + '">Mark Completed</button>';
                        facultyActions += '<button class="btn-p btn-p--sm btn-p--ghost" data-action="flag-session" data-id="' + s.id + '"' +
                            (within24h ? disabledAttr : '') + '>Flag Reschedule</button>';
                        facultyActions += '<button class="btn-p btn-p--sm btn-p--ghost" data-action="cancel-session" data-id="' + s.id + '">Cancel</button>';
                    } else if (s.status === 'rescheduling_required') {
                        facultyActions += '<button class="btn-p btn-p--sm btn-p--ghost" data-action="flag-session" data-id="' + s.id + '">Update Proposal</button>';
                    }
                    facultyActions += '</div>' + (s.status === 'scheduled' ? policyNote : '');
                } else if (s.status === 'scheduled') {
                    facultyActions = '<div class="btn-row" style="margin-top:8px">' +
                        '<button class="btn-p btn-p--sm btn-p--ghost" data-action="flag-session" data-id="' + s.id + '"' +
                        (within24h ? disabledAttr : '') + '>Request Reschedule</button></div>' +
                        (within24h ? policyNote : '');
                } else if (s.status === 'rescheduling_required') {
                    facultyActions = '<div class="btn-row" style="margin-top:8px">' +
                        '<button class="btn-p btn-p--sm btn-p--ghost" data-action="flag-session" data-id="' + s.id + '">Update Request</button></div>';
                }
                return '<div class="list__row" style="align-items:flex-start">' +
                    '<div class="list__date">' + esc(fmtDay(s.scheduled_date)) +
                    '<span>' + esc(s.scheduled_start) + ' – ' + esc(s.scheduled_end) + '</span></div>' +
                    '<div class="list__body">' +
                    '<div class="list__title">' + (
                        isFaculty() && s.student_name
                            ? esc(s.student_name) + (s.student_cma ? ' · ' + esc(s.student_cma) : '')
                            : esc(s.is_online ? 'Online class' : (s.location || 'Academy class'))
                    ) +
                    (s.is_duration_exception ? ' · ' + esc(s.duration_minutes) + ' min (exception)' : '') + '</div>' +
                    '<div class="list__sub">' + esc((s.programme ? s.programme + ' · ' : '') +
                        (s.is_online ? 'Online class' : (s.location || 'Academy class'))) + '</div>' +
                    '<div class="list__sub">' + esc(s.topics_covered || '—') + '</div>' +
                    (s.status === 'rescheduling_required' ? '<div class="list__sub" style="color:var(--danger)">Requested: ' +
                        esc(s.reschedule_reason || 'no reason given') +
                        (s.preferred_date ? ' · Proposed: ' + esc(s.preferred_date + (s.preferred_start ? ' ' + s.preferred_start : '')) : '') + '</div>' : '') +
                    (s.status === 'completed' && s.practice_recommendations ? '<div class="list__sub">Practice: ' + esc(s.practice_recommendations) + '</div>' : '') +
                    facultyActions + '</div>' +
                    '<div class="list__actions">' + badge(s.status) + '</div></div>';
            }).join('') + '</div>'
            : emptyState('🗓', 'No classes scheduled in this period.');

        return '' +
            '<div class="card">' +
            '<div class="card__head">' +
            '<div class="tabs" style="margin:0;border:none">' +
            ['month', 'week', 'list'].map(function (v) {
                return '<button class="tabs__tab' + (state.classView === v ? ' tabs__tab--active' : '') + '" ' +
                    'data-classview="' + v + '">' + v[0].toUpperCase() + v.slice(1) + '</button>';
            }).join('') +
            '</div>' + actions +
            '<p style="font-size:11.5px;color:var(--muted);margin:8px 0 0">' + esc(RESCHEDULE_POLICY_TEXT) + '</p>' +
            '</div>' +
            '<div class="grid grid--main">' +
            '<div>' + renderCalendar() + '</div>' +
            '<div><h4 style="margin:0 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--text-2)">' + periodLabel + '</h4>' +
            sessionList + '</div>' +
            '</div></div>';
    }

    // ------------------------------------------------------------------
    // Section: Billing
    // ------------------------------------------------------------------
    async function loadBilling() {
        const isParent = state.role === 'parent';
        const sid = state.activeStudentId ||
            (state.role === 'student' && state.me && state.me.student ? state.me.student.id : null);
        const stmtQuery = isParent ? '?family=1' : (sid ? '?student_id=' + sid : '');
        const results = await Promise.all([
            api('/billing/statement' + stmtQuery),
            api('/billing/packages'),
            api('/billing/payments/config'),
        ]);
        state.statement = results[0];
        state.packages = results[1];
        state.paymentConfig = results[2];
        // Assigned package (enrollment fee_plan) drives Razorpay button eligibility
        if (!state.enrollments.length) state.enrollments = await api('/portal/enrollments');
    }

    // Razorpay payment buttons (hosted checkout). These carry no student
    // metadata — online button payments must be matched by the academy from
    // the Razorpay reference. Eligibility follows the student's assigned plan.
    const RZP_PAY4_FORM =
        '<div class="pay4"><div class="pay4__head">Pay for 4 Classes</div>' +
        '<form id="pay4Form" class="pay4__form" data-button-id="pl_Tnqy1uieHgbpW3"></form></div>';
    const RZP_PAY8_FORM =
        '<div class="pay4"><div class="pay4__head">Pay for 8 Classes</div>' +
        '<form id="pay8Form" class="pay4__form" data-button-id="pl_Tnr9UX8Me8AtYF"></form></div>';

    function assignedPackagePlans() {
        const plans = { four: false, eight: false };
        (state.enrollments || []).forEach(function (e) {
            if (e.fee_plan === '4_classes') plans.four = true;
            if (e.fee_plan === '8_classes') plans.eight = true;
        });
        return plans;
    }

    function mountRazorpayButtons() {
        ['pay4Form', 'pay8Form'].forEach(function (formId) {
            const form = document.getElementById(formId);
            if (!form || form.dataset.mounted === '1') return;
            const buttonId = form.getAttribute('data-button-id');
            if (!buttonId) return;
            form.dataset.mounted = '1';
            const script = document.createElement('script');
            script.src = 'https://checkout.razorpay.com/v1/payment-button.js';
            script.async = true;
            script.setAttribute('data-payment_button_id', buttonId);
            form.appendChild(script);
        });
    }

    const FEE_STATUS_LABEL = {
        pending: 'Unpaid', partially_paid: 'Partially paid', paid: 'Paid', void: 'Void',
    };

    function feeStatusBadge(c) {
        if (c.status === 'paid') return '<span class="badge badge--paid">Paid</span>';
        if (c.status === 'void') return '<span class="badge">Void</span>';
        const partial = c.amount_paid_paise > 0;
        const overdue = c.is_overdue;
        return '<span class="badge ' + (partial ? 'badge--pending' : (overdue ? 'badge--pending' : '')) + '">' +
            (partial ? 'Partially paid' : (overdue ? 'Overdue' : 'Unpaid')) + '</span>';
    }

    function renderBilling() {
        const stmt = state.statement || { students: [], totals: { charged_paise: 0, paid_paise: 0, outstanding_paise: 0, credit_balance_paise: 0 } };
        const tabs = [
            { id: 'statement', label: 'Statement' },
            { id: 'pay', label: 'Pay Now' },
            { id: 'history', label: 'History & Receipts' },
        ].map(function (t) {
            return '<button class="tabs__tab' + (state.billingTab === t.id ? ' tabs__tab--active' : '') + '" ' +
                'data-billingtab="' + t.id + '">' + t.label + '</button>';
        }).join('');

        let body = '';
        if (state.billingTab === 'statement') {
            const studentBlocks = stmt.students.map(function (st) {
                const chargeRows = st.charges.map(function (c) {
                    return '<tr><td>' + esc(monthLabel(c.billing_month)) + '</td>' +
                        '<td>' + esc(c.invoice_number) + '<div style="font-size:11px;color:var(--muted)">' +
                        esc(c.description || c.charge_type) + '</div></td>' +
                        '<td>' + fmtPaise(c.amount_paise) + '</td>' +
                        '<td>' + fmtPaise(c.amount_paid_paise) + '</td>' +
                        '<td>' + fmtPaise(c.outstanding_paise) + '</td>' +
                        '<td>' + feeStatusBadge(c) + '</td></tr>';
                }).join('');
                const examRows = st.exam_fees.map(function (e) {
                    return '<tr><td colspan="2"><strong>Exam:</strong> ' + esc([e.board, e.grade_level, e.exam_session].filter(Boolean).join(' · ')) + '</td>' +
                        '<td>' + fmtPaise(e.fee_charged_paise) + '</td>' +
                        '<td>' + fmtPaise(e.reimbursed_paise) + '</td>' +
                        '<td>' + fmtPaise(e.reimbursement_balance_paise) + '</td>' +
                        '<td>' + esc(e.status.replace(/_/g, ' ')) + '</td></tr>';
                }).join('');
                const creditRows = st.credits.length
                    ? '<div style="margin-top:10px;font-size:12px;color:var(--text-2)"><strong>Advance credits:</strong> ' +
                      st.credits.map(function (c) {
                          return esc(c.kind) + ' ' + fmtPaise(Math.abs(c.amount_paise)) +
                              (c.amount_paise > 0 ? ' (added)' : ' (applied)');
                      }).join(' · ') + '</div>'
                    : '';
                return '<div style="margin-bottom:18px">' +
                    (stmt.students.length > 1 ? '<h4 style="margin:12px 0 6px">' + esc(st.student_name || 'Student') + '</h4>' : '') +
                    '<table class="table-p"><thead><tr><th>Month</th><th>Charge</th><th>Amount</th><th>Paid</th><th>Balance</th><th>Status</th></tr></thead><tbody>' +
                    (chargeRows || '<tr><td colspan="6" style="color:var(--muted)">No charges issued yet</td></tr>') + examRows +
                    '</tbody></table>' +
                    '<div style="margin-top:8px;font-size:12.5px;color:var(--text-2)">Totals: charged ' + fmtPaise(st.totals.charged_paise) +
                    ' · paid ' + fmtPaise(st.totals.paid_paise) + ' · outstanding <strong>' + fmtPaise(st.totals.outstanding_paise) + '</strong>' +
                    ' · credit ' + fmtPaise(st.totals.credit_balance_paise) + '</div>' + creditRows +
                    '</div>';
            }).join('');

            body = (studentBlocks || emptyState('🧾', 'No financial records yet.')) +
                '<div style="margin-top:12px;display:flex;gap:10px;flex-wrap:wrap">' +
                (stmt.students.length ? '<button class="btn-p btn-p--sm btn-p--ghost" data-action="export-statement">Download statement (CSV)</button>' : '') +
                '</div>' +
                '<p style="font-size:11px;color:var(--muted);margin-top:10px">Payments marked admin-recorded were received by the academy (cash/UPI/bank) and confirmed manually by staff — they are not independently verified bank transactions.</p>';
        } else if (state.billingTab === 'pay') {
            const assigned = assignedPackagePlans();
            const pendingPayments = stmt.students.reduce(function (acc, st) {
                return acc.concat(st.payments.filter(function (pv) { return pv.status === 'pending_verification'; }));
            }, []);
            const allCharges = stmt.students.reduce(function (acc, st) { return acc.concat(st.charges); }, []);
            const due = allCharges.filter(function (c) { return c.status === 'pending' || c.status === 'partially_paid'; });
            const pkgCards = (state.packages.length ? state.packages : [
                { id: null, name: '4 Classes Package', fee_paise: 450000, sessions_included: 4 },
                { id: null, name: '8 Classes Package', fee_paise: 800000, sessions_included: 8 },
            ]).map(function (p, index) {
                const isFourCard = p.sessions_included === 4 || p.fee_paise === 450000;
                const isEightCard = p.sessions_included === 8 || p.fee_paise === 800000;
                const payBlock = (isFourCard && assigned.four) ? RZP_PAY4_FORM
                    : (isEightCard && assigned.eight) ? RZP_PAY8_FORM
                    : '';
                return '<div class="pack' + (index === 0 ? ' pack--featured' : '') + '">' +
                    '<div class="pack__name">' + esc(p.name) + '</div>' +
                    '<div class="pack__price">' + fmtPaise(p.fee_paise) + '</div>' +
                    '<div class="pack__note">(1 hour per class)</div>' +
                    '<ul class="pack__perks">' +
                    '<li>Valid for 1 month</li>' +
                    '<li>Access to study material</li>' +
                    '<li>Monthly faculty report</li>' +
                    '</ul>' +
                    payBlock +
                    '</div>';
            }).join('');

            const dueRows = due.map(function (c) {
                return '<div class="list__row"><div class="list__body">' +
                    '<div class="list__title">' + esc(monthLabel(c.billing_month)) + ' · ' + esc(c.description || c.charge_type) + '</div>' +
                    '<div class="list__sub">' + esc(c.invoice_number) + ' · balance ' + fmtPaise(c.outstanding_paise) + '</div></div>' +
                    '<div class="list__actions">' +
                    (state.paymentConfig && state.paymentConfig.enabled
                        ? '<button class="btn-p btn-p--sm" data-action="pay-invoice" data-id="' + c.id + '">Pay ' + fmtPaise(c.outstanding_paise) + ' via Razorpay</button>'
                        : '<span class="badge badge--pending">Settle at academy</span>') +
                    '</div></div>';
            }).join('');

            body = (pendingPayments.length ? pendingNoticeHtml() : '') +
                '<div class="grid grid--2">' + pkgCards + '</div>' +
                (dueRows ? '<h4 style="margin:16px 0 8px">Outstanding charges</h4><div class="list">' + dueRows + '</div>' : '') +
                '<div style="margin-top:12px"><button class="btn-p btn-p--sm btn-p--ghost" data-action="report-payment">Report a payment made outside the portal</button></div>' +
                '<div style="margin-top:14px;font-size:12px;color:var(--text-2);line-height:1.7">' +
                (state.paymentConfig && state.paymentConfig.enabled
                    ? '<strong>Paying online:</strong> the button and checkout use Razorpay. Complete payment using the methods ' +
                      'Razorpay shows at checkout — your fee status updates once the payment is verified. ' +
                      'If you paid via the payment button, please share the Razorpay payment reference with the academy so it can be matched to your fee.'
                    : '<strong>Paying online:</strong> the payment buttons above collect card/UPI payments through Razorpay. ' +
                      'After paying, share the Razorpay payment reference with the academy so it can be matched to your fee — ' +
                      'online payments are marked as paid only after the academy confirms them in Razorpay. ' +
                      'You can also settle dues by cash/UPI at the academy.') +
                '</div>';
        } else {
            const payments = stmt.students.reduce(function (acc, st) {
                return acc.concat(st.payments.map(function (pv) { return Object.assign({}, pv, { _student: st.student_name }); }));
            }, []);
            const hasPending = payments.some(function (pv) { return pv.status === 'pending_verification'; });
            body = (hasPending ? pendingNoticeHtml() : '') +
                (payments.length
                ? '<table class="table-p"><thead><tr><th>Date</th><th>Amount</th><th>Method</th><th>Status</th><th>Reference</th><th>Receipt</th></tr></thead><tbody>' +
                  payments.map(function (pv) {
                      const pending = pv.status === 'pending_verification';
                      return '<tr><td>' + esc(pv.paid_at ? new Date(pv.paid_at).toLocaleDateString('en-IN') : '—') + '</td>' +
                          '<td>' + fmtPaise(pv.amount_paise) + '</td>' +
                          '<td>' + esc(pv.method || pv.provider) +
                          (pv.source === 'manual' ? '<div style="font-size:10px;color:var(--muted)">admin-recorded</div>' : '') +
                          (pv.source === 'reported' ? '<div style="font-size:10px;color:var(--muted)">reported by you</div>' : '') + '</td>' +
                          '<td>' + (pending
                              ? '<span class="badge badge--pending">Pending Verification</span>'
                              : badge(pv.status === 'verified' ? 'paid' : pv.status)) + '</td>' +
                          '<td>' + esc(pv.provider_payment_id || '—') + '</td>' +
                          '<td>' + (pv.receipt_number
                              ? '<button class="btn-p btn-p--sm btn-p--ghost" data-action="view-receipt" data-id="' + pv.id + '">' + esc(pv.receipt_number) + '</button>'
                              : '—') + '</td></tr>';
                  }).join('') + '</tbody></table>'
                : emptyState('₹', 'No payments recorded yet.')) +
                '<p style="font-size:11px;color:var(--muted);margin-top:10px">Pending Verification: the payment has been recorded but is not yet confirmed — ' +
                'your fee status is updated only after the academy verifies the transaction. Confirmed payments carry a receipt number.</p>';
        }

        return '<div class="card"><div class="tabs">' + tabs + '</div>' + body + '</div>';
    }

    // ------------------------------------------------------------------
    // Section: Assignments
    // ------------------------------------------------------------------
    async function loadAssignments() {
        state.assignments = await api('/learning/assignments');
    }

    function renderAssignments() {
        const tabs = [
            { id: 'current', label: 'Current' },
            { id: 'submitted', label: 'Submitted' },
            { id: 'all', label: 'All' },
        ].map(function (t) {
            return '<button class="tabs__tab' + (state.assignmentTab === t.id ? ' tabs__tab--active' : '') + '" ' +
                'data-assignmenttab="' + t.id + '">' + t.label + '</button>';
        }).join('');

        const filtered = state.assignments.filter(function (a) {
            if (state.assignmentTab === 'all') return true;
            if (state.assignmentTab === 'submitted') return a.submission && ['submitted', 'reviewed'].indexOf(a.submission.status) >= 0;
            return !a.submission || ['assigned', 'revision_requested'].indexOf(a.status) >= 0;
        });

        const head = isFaculty()
            ? '<button class="btn-p btn-p--auto btn-p--sm" data-action="new-assignment">＋ New Assignment</button>'
            : '';

        const rows = filtered.length ? '<div class="list">' + filtered.map(function (a) {
            const sub = a.submission;
            let action = '';
            if (isFaculty()) {
                if (sub && sub.status === 'submitted') {
                    action = '<button class="btn-p btn-p--sm" data-action="review-submission" data-id="' + sub.id + '">Review</button>';
                }
            } else if (!sub || a.status === 'revision_requested') {
                action = '<button class="btn-p btn-p--sm" data-action="submit-homework" data-id="' + a.id + '">Upload</button>';
            } else if (sub.status === 'reviewed') {
                action = '<span class="badge badge--reviewed">Reviewed</span>';
            } else {
                action = '<span class="badge badge--submitted">Submitted</span>';
            }
            const due = a.due_date
                ? '<div class="list__sub list__sub--due">Due: ' + esc(fmtDay(a.due_date)) + ' ' + esc(a.due_date.slice(0, 4)) + '</div>'
                : '';
            return '<div class="list__row" style="align-items:flex-start">' +
                '<span class="list__icon">♪</span>' +
                '<div class="list__body">' +
                '<div class="list__title">' + esc(a.title) + '</div>' +
                '<div class="list__sub">' + esc(a.instructions || a.practice_notes || 'Practice as assigned.') + '</div>' +
                due +
                (sub && sub.feedback ? '<div class="list__sub" style="color:var(--success)">Faculty: ' + esc(sub.feedback) + '</div>' : '') +
                '</div>' +
                '<div class="list__actions">' + action + '</div></div>';
        }).join('') + '</div>' : emptyState('✎', 'No assignments here yet.');

        return '<div class="card"><div class="card__head"><div class="tabs" style="margin:0;border:none">' + tabs + '</div>' + head + '</div>' + rows + '</div>';
    }

    // ------------------------------------------------------------------
    // Section: Study material
    // ------------------------------------------------------------------
    async function loadMaterials() {
        state.materials = await api('/learning/materials');
    }

    function renderMaterials() {
        const filters = [
            { id: 'all', label: 'All' },
            { id: 'technique', label: 'Technique' },
            { id: 'repertoire', label: 'Repertoire' },
            { id: 'theory', label: 'Theory' },
            { id: 'ear_training', label: 'Ear Training' },
            { id: 'exam_preparation', label: 'Exams' },
        ].map(function (f) {
            return '<button class="chip' + (state.materialFilter === f.id ? ' chip--active' : '') + '" ' +
                'data-matfilter="' + f.id + '">' + f.label + '</button>';
        }).join('');

        const rows = state.materials
            .filter(function (m) { return state.materialFilter === 'all' || m.category === state.materialFilter; })
            .map(function (m) {
                const isPdf = m.content_type === 'application/pdf';
                const glyphClass = m.material_type === 'link' ? 'link' : (isPdf ? 'pdf' : (String(m.content_type || '').startsWith('audio') ? 'audio' : 'doc'));
                const glyphText = glyphClass === 'pdf' ? 'PDF' : glyphClass === 'audio' ? '♪' : glyphClass === 'link' ? '↗' : 'DOC';
                const action = m.material_type === 'link' && m.link_url
                    ? '<a class="btn-p btn-p--sm btn-p--ghost" href="' + esc(m.link_url) + '" target="_blank" rel="noopener">Open ↗</a>'
                    : '<button class="btn-p btn-p--sm btn-p--ghost" data-action="download" data-name="' + esc(m.stored_name) + '" data-filename="' + esc(m.filename || m.title) + '">⇩ Download</button>';
                return '<div class="list__row">' +
                    '<span class="glyph glyph--' + glyphClass + '">' + glyphText + '</span>' +
                    '<div class="list__body"><div class="list__title">' + esc(m.title) + '</div>' +
                    '<div class="list__sub">' + esc(m.description || m.category.replace('_', ' ')) + '</div></div>' +
                    '<div class="list__actions">' + action + '</div></div>';
            }).join('');

        const head = isFaculty()
            ? '<button class="btn-p btn-p--auto btn-p--sm" data-action="new-material">＋ Upload Material</button>'
            : '';

        return '<div class="card"><div class="card__head"><div class="chips" style="margin:0">' + filters + '</div>' + head + '</div>' +
            (rows || emptyState('◫', 'No study material here yet.')) + '</div>';
    }

    // ------------------------------------------------------------------
    // Section: Reports
    // ------------------------------------------------------------------
    async function loadReports() {
        state.reports = await api('/learning/reports');
    }

    // ------------------------------------------------------------------
    // Section: Remarks
    // ------------------------------------------------------------------
    async function loadRemarks() {
        let studentId = null;
        if (state.role === 'student' && state.me && state.me.student) {
            studentId = state.me.student.id;
        } else if (state.role === 'parent') {
            studentId = state.activeStudentId;
        }
        if (!studentId) { state.remarks = []; return; }
        state.remarks = await api('/remarks?student_id=' + studentId);
    }

    function renderRemarks() {
        const remarks = state.remarks || [];
        if (!remarks.length) {
            return '<div class="card">' + emptyState('💬', 'No remarks yet. Faculty remarks will appear here.') + '</div>';
        }
        const rows = remarks.map(function (r) {
            const visBadge = r.visibility === 'parent_visible'
                ? '<span class="badge badge--parent">For Parents</span>'
                : '<span class="badge badge--student">For Students</span>';
            return '<div class="list__row" style="align-items:flex-start;flex-direction:column;gap:6px;">' +
                '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">' +
                '<span class="list__icon">💬</span>' + visBadge +
                '<span style="font-size:0.78rem;color:var(--text-2);">' +
                esc(r.author_role === 'instructor' ? 'Faculty' : 'Academy') +
                ' · ' + esc(r.created_at ? new Date(r.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) : '') +
                '</span></div>' +
                '<div style="white-space:pre-wrap;line-height:1.55;">' + esc(r.body) + '</div>' +
                '</div>';
        }).join('');
        return '<div class="card"><div class="card__head"><h3 class="card__title">Remarks from Faculty</h3></div>' + rows + '</div>';
    }

    const REPORT_STATUS_LABEL = {
        draft: 'Draft', submitted: 'Submitted for review', published: 'Approved & published',
    };

    function renderReports() {
        const head = isFaculty()
            ? '<button class="btn-p btn-p--auto btn-p--sm" data-action="new-report">＋ Prepare Monthly Report</button>'
            : '';
        const rows = state.reports.length ? state.reports.map(function (r) {
            let actions;
            if (isFaculty()) {
                if (r.status === 'draft') {
                    actions = '<button class="btn-p btn-p--sm" data-action="edit-report" data-id="' + r.id + '">Edit</button>' +
                        '<button class="btn-p btn-p--sm btn-p--ghost" data-action="submit-report" data-id="' + r.id + '">Submit for Review</button>';
                } else if (r.status === 'submitted') {
                    actions = '<button class="btn-p btn-p--sm btn-p--ghost" data-action="view-report" data-id="' + r.id + '">View</button>' +
                        '<span class="badge badge--scheduled">Awaiting approval</span>';
                } else {
                    actions = '<button class="btn-p btn-p--sm btn-p--ghost" data-action="view-report" data-id="' + r.id + '">View</button>';
                }
            } else {
                actions = r.status === 'published'
                    ? '<button class="btn-p btn-p--sm btn-p--ghost" data-action="view-report" data-id="' + r.id + '">View</button>'
                    : '';
            }
            return '<div class="list__row">' +
                '<span class="list__icon">☰</span>' +
                '<div class="list__body"><div class="list__title">Faculty Report — ' + esc(monthLabel(r.report_month)) +
                ' <span style="font-weight:400;color:var(--muted);font-size:11px">rev ' + (r.revision || 1) + '</span></div>' +
                '<div class="list__sub">' + esc(REPORT_STATUS_LABEL[r.status] || r.status) + ' · ' +
                esc((r.progress_summary || '').slice(0, 90) || '—') + '</div></div>' +
                '<div class="list__actions">' + actions + '</div></div>';
        }).join('') : emptyState('☰', 'No reports yet.');

        return '<div class="card"><div class="card__head"><h3 class="card__title">Monthly Reports</h3>' + head + '</div>' +
            '<p style="font-size:11.5px;color:var(--muted);margin:0 16px 8px">Reports are prepared automatically from your class ' +
            'completion records — you only add observations, achievements, concerns and recommendations, then submit for review.</p>' +
            rows + '</div>';
    }

    // ------------------------------------------------------------------
    // Section: Syllabus
    // ------------------------------------------------------------------
    async function loadSyllabus() {
        const results = await Promise.all([
            api('/learning/syllabi'),
            state.activeStudentId
                ? api('/learning/syllabus-progress?student_id=' + state.activeStudentId)
                : Promise.resolve(null),
        ]);
        state.syllabi = results[0];
        state.progress = results[1];
    }

    function renderSyllabus() {
        if (!state.syllabi.length) {
            return '<div class="card">' + emptyState('✓', 'Syllabus will appear here once faculty publishes one.') + '</div>';
        }
        const syllabus = state.syllabi[0];
        const progressItems = state.progress ? state.progress.items : [];
        const pct = state.progress ? (state.progress.percent || 0) : 0;

        const checklist = syllabus.items.map(function (item) {
            const progress = progressItems.find(function (p) { return p.item_id === item.id; });
            const status = progress ? progress.status : 'not_started';
            const mark = status === 'completed'
                ? '<span class="check-mark check-mark--done">✓</span>'
                : status === 'in_progress'
                    ? '<span class="check-mark check-mark--progress">•</span>'
                    : '<span class="check-mark"></span>';
            const meta = progress
                ? '<span class="check-list__meta">' + esc(status === 'completed' ? 'Completed' : status === 'in_progress' ? 'In progress' : 'Not started') + '</span>'
                : '<span class="check-list__meta">Not started</span>';
            const facultyAction = isFaculty() && state.activeStudentId
                ? '<div class="btn-row" style="margin-left:8px">' +
                  (status !== 'completed'
                      ? '<button class="btn-p btn-p--sm btn-p--ghost" data-action="progress" data-item="' + item.id + '" data-status="' +
                        (status === 'not_started' ? 'in_progress' : 'completed') + '">' +
                        (status === 'not_started' ? 'Start' : 'Mark Done') + '</button>'
                      : '') + '</div>'
                : '';
            return '<li>' + mark + '<span>' + esc(item.title) + '</span>' + facultyAction + meta + '</li>';
        }).join('');

        return '<div class="card">' +
            '<div class="card__head"><h3 class="card__title">' + esc(syllabus.title) + '</h3>' +
            '<span class="badge badge--pending">' + esc(syllabus.grade ? 'Grade ' + syllabus.grade : syllabus.board) + '</span></div>' +
            '<div class="welcome__progress-label"><span>Overall Progress</span><strong>' + pct + '%</strong></div>' +
            '<div class="progress" style="margin:8px 0 16px"><div class="progress__bar" style="width:' + pct + '%"></div></div>' +
            '<ul class="check-list">' + checklist + '</ul>' +
            '</div>';
    }

    // ------------------------------------------------------------------
    // Section: Exams
    // ------------------------------------------------------------------
    async function loadExams() {
        const results = await Promise.all([
            api('/learning/exams'),
            api('/learning/milestones'),
        ]);
        state.exams = results[0];
        state.milestones = results[1];
    }

    function renderExams() {
        const examRows = state.exams.length ? state.exams.map(function (x) {
            const action = isFaculty()
                ? '<button class="btn-p btn-p--sm btn-p--ghost" data-action="exam-status" data-id="' + x.id + '">Update</button>'
                : '';
            return '<div class="list__row">' +
                '<span class="list__icon">♛</span>' +
                '<div class="list__body">' +
                '<div class="list__title">' + esc(x.board) + ' Grade ' + esc(x.grade || '—') + ' · ' + esc(x.instrument) + '</div>' +
                '<div class="list__sub">' +
                (x.submission_deadline ? 'Submission deadline: ' + esc(fmtLong(x.submission_deadline)) : 'No deadline set') +
                (x.readiness ? ' · Readiness: ' + esc(x.readiness) : '') + '</div></div>' +
                '<div class="list__actions">' + badge(x.submission_status === 'submitted' ? 'completed' : x.submission_status || 'pending') + action + '</div></div>';
        }).join('') : emptyState('♛', 'No exams configured yet.');

        const milestoneRows = state.milestones.length ? state.milestones.map(function (m) {
            return '<div class="list__row">' +
                '<span class="list__icon">★</span>' +
                '<div class="list__body"><div class="list__title">' + esc(m.title) + '</div>' +
                '<div class="list__sub">' + esc(m.description || m.milestone_type) +
                (m.due_date ? ' · due ' + esc(fmtDay(m.due_date)) : '') + '</div></div>' +
                '<div class="list__actions">' + badge(m.achieved_at ? 'completed' : m.status || 'pending') + '</div></div>';
        }).join('') : emptyState('★', 'No milestones yet.');

        return '<div class="grid grid--2">' +
            '<div class="card"><div class="card__head"><h3 class="card__title">Exams</h3>' +
            (isFaculty() ? '<button class="btn-p btn-p--sm" data-action="new-exam">＋ Add</button>' : '') + '</div>' + examRows + '</div>' +
            '<div class="card"><div class="card__head"><h3 class="card__title">Milestones</h3>' +
            (isFaculty() ? '<button class="btn-p btn-p--sm" data-action="new-milestone">＋ Add</button>' : '') + '</div>' + milestoneRows + '</div>' +
            '</div>';
    }

    // ------------------------------------------------------------------
    // Section: Resources
    // ------------------------------------------------------------------
    async function loadResources() {
        state.resources = await api('/learning/recommendations');
    }

    function renderResources() {
        const tabs = [
            { id: 'books', label: 'Books', types: ['book'] },
            { id: 'instruments', label: 'Instruments', types: ['instrument'] },
            { id: 'accessories', label: 'Accessories', types: ['accessory', 'stand_notebook', 'metronome_tuner'] },
            { id: 'links', label: 'Online Links', types: ['online_link'] },
        ];
        const active = tabs.find(function (t) { return t.id === state.resourceTab; }) || tabs[0];
        const rows = state.resources
            .filter(function (r) { return active.types.indexOf(r.resource_type) >= 0; })
            .map(function (r) {
                return '<div class="res-row">' +
                    '<span class="res-row__thumb">' + (r.image_url ? '♪' : (active.id === 'books' ? '📖' : active.id === 'instruments' ? '🎻' : '🎧')) + '</span>' +
                    '<div class="list__body"><div class="list__title">' + esc(r.name) + '</div>' +
                    '<div class="list__sub">' + esc(r.author_or_brand || r.suitability || '') +
                    (r.faculty_note ? ' · ' + esc(r.faculty_note) : '') + '</div></div>' +
                    '<div class="list__actions">' +
                    (r.external_url
                        ? '<a class="btn-p btn-p--sm btn-p--ghost" href="' + esc(r.external_url) + '" target="_blank" rel="noopener">Buy Link</a>'
                        : '<span class="list__sub">Ask faculty</span>') +
                    '</div></div>';
            }).join('');

        return '<div class="card">' +
            '<div class="card__head"><div class="tabs" style="margin:0;border:none">' +
            tabs.map(function (t) {
                return '<button class="tabs__tab' + (state.resourceTab === t.id ? ' tabs__tab--active' : '') + '" ' +
                    'data-restab="' + t.id + '">' + t.label + '</button>';
            }).join('') + '</div></div>' +
            (rows || emptyState('◈', 'No recommendations in this category yet.')) + '</div>';
    }

    // ------------------------------------------------------------------
    // Section: Profile & help
    // ------------------------------------------------------------------
    function backToDashboard() {
        return '<div style="margin-bottom:16px">' +
            '<button class="btn-p btn-p--sm btn-p--ghost" data-portal-nav="dashboard">\u2190 Back to Dashboard</button>' +
            '</div>';
    }

    function renderProfile() {
        const me = state.me || {};
        if (state.role === 'student' && me.student) {
            const s = me.student;
            const enrolRows = (s.enrollments || []).map(function (e) {
                return '<tr><td>' + esc(e.programme_name) + '</td><td>' + esc(e.instructor || '—') + '</td>' +
                    '<td>' + esc(e.fee_plan || '—') + '</td><td>' + badge(e.status) + '</td></tr>';
            }).join('');
            const guardianRows = (s.guardians || []).map(function (g) {
                return '<div class="list__row"><div class="list__body">' +
                    '<div class="list__title">' + esc(g.name) + '</div>' +
                    '<div class="list__sub">' + esc(g.relationship || '') + (g.phone ? ' · ' + esc(g.phone) : '') + '</div></div></div>';
            }).join('');

            return backToDashboard() +
                '<div class="grid grid--2">' +
                '<div class="card">' +
                '<div class="card__head"><h3 class="card__title">Profile</h3>' +
                '<button class="btn-p btn-p--sm btn-p--ghost" data-action="edit-profile">Edit</button></div>' +
                '<table class="table-p"><tbody>' +
                '<tr><td>Full name</td><td>' + esc(s.full_name) + '</td></tr>' +
                '<tr><td>CMA Registration ID</td><td><strong>' + esc(s.cma_registration_id) + '</strong></td></tr>' +
                '<tr><td>Email</td><td>' + esc(s.email) + '</td></tr>' +
                '<tr><td>Phone</td><td>' + esc(s.phone || '—') + '</td></tr>' +
                '<tr><td>Date of birth</td><td>' + esc(s.date_of_birth ? fmtLong(s.date_of_birth) : '—') + '</td></tr>' +
                '<tr><td>Skill level</td><td>' + esc(s.skill_level || '—') + '</td></tr>' +
                '</tbody></table></div>' +
                '<div class="card"><div class="card__head"><h3 class="card__title">Enrolled Courses</h3></div>' +
                (enrolRows
                    ? '<table class="table-p"><thead><tr><th>Programme</th><th>Faculty</th><th>Plan</th><th>Status</th></tr></thead><tbody>' + enrolRows + '</tbody></table>'
                    : emptyState('🎓', 'No enrolments yet.')) +
                '<div class="card__head" style="margin-top:18px"><h3 class="card__title">Guardians</h3></div>' +
                (guardianRows || emptyState('👪', 'No guardians on record.')) +
                '</div></div>';
        }
        if (state.role === 'parent') {
            const kids = (state.children || []).map(function (c) {
                return '<div class="list__row"><span class="portal-avatar">' + esc(initials(c.full_name)) + '</span>' +
                    '<div class="list__body"><div class="list__title">' + esc(c.full_name) + '</div>' +
                    '<div class="list__sub">' + esc(c.cma_registration_id || '') + '</div></div></div>';
            }).join('');
            return backToDashboard() +
                '<div class="card"><div class="card__head"><h3 class="card__title">Linked Children</h3></div>' +
                (kids || emptyState('👪', 'No children linked to this account.')) + '</div>';
        }
        const instructor = (state.me && state.me.instructor) || {};
        return backToDashboard() +
            '<div class="card"><div class="card__head"><h3 class="card__title">Faculty Profile</h3></div>' +
            '<table class="table-p"><tbody>' +
            '<tr><td>Name</td><td>' + esc(instructor.name || '—') + '</td></tr>' +
            '<tr><td>Email</td><td>' + esc((state.me || {}).email || '—') + '</td></tr>' +
            (instructor.specializations ? '<tr><td>Specialisations</td><td>' + esc(instructor.specializations) + '</td></tr>' : '') +
            (instructor.qualifications ? '<tr><td>Qualifications</td><td>' + esc(instructor.qualifications) + '</td></tr>' : '') +
            (instructor.experience_years ? '<tr><td>Experience</td><td>' + esc(instructor.experience_years) + '</td></tr>' : '') +
            (instructor.phone ? '<tr><td>Phone</td><td>' + esc(instructor.phone) + '</td></tr>' : '') +
            (instructor.bio ? '<tr><td>Bio</td><td>' + esc(instructor.bio) + '</td></tr>' : '') +
            '<tr><td>Students</td><td>' + state.enrollments.length + '</td></tr>' +
            '</tbody></table></div>';
    }

    // ------------------------------------------------------------------
    // Section: Achievements / Trophies
    // ------------------------------------------------------------------
    const ACHIEVEMENT_ICONS = {
        exam: '🎓', recital: '🎹', competition: '🏆', certification: '📜', award: '🥇', milestone: '⭐',
    };

    async function loadAchievements() {
        const sid = state.activeStudentId ||
            (state.role === 'student' && state.me && state.me.student ? state.me.student.id : null);
        if (!sid) { state.achievements = []; return; }
        state.achievements = await api('/portal/achievements?student_id=' + sid);
    }

    function renderAchievements() {
        const list = state.achievements || [];
        const cards = list.map(function (a) {
            return '<div class="card" style="margin:0">' +
                '<div style="display:flex;gap:12px;align-items:flex-start">' +
                '<div style="font-size:30px;line-height:1">' + (ACHIEVEMENT_ICONS[a.category] || '🏆') + '</div>' +
                '<div><div style="font-weight:600;font-size:15px">' + esc(a.title) + '</div>' +
                '<div style="font-size:12px;color:var(--text-2);margin-top:2px">' +
                esc([a.awarding_body, a.programme_id, a.grade_level].filter(Boolean).join(' · ')) + '</div>' +
                (a.result ? '<div style="margin-top:6px"><span class="badge badge--completed">' + esc(a.result) + '</span></div>' : '') +
                (a.achieved_on ? '<div style="font-size:11px;color:var(--muted);margin-top:6px">Achieved ' + esc(a.achieved_on) + '</div>' : '') +
                (a.description ? '<div style="font-size:12.5px;color:var(--text-2);margin-top:8px;line-height:1.6">' + esc(a.description) + '</div>' : '') +
                (a.certificate ? '<div style="margin-top:8px"><a style="font-size:12px" href="' +
                    BASE + '/portal/achievements/files/' + encodeURIComponent(a.certificate.stored_name) +
                    '?student_id=' + encodeURIComponent(state.activeStudentId || (state.me && state.me.student ? state.me.student.id : '')) + '" target="_blank">View certificate</a></div>' : '') +
                '</div></div></div>';
        }).join('');

        return '<div class="card"><div class="card__head"><h3 class="card__title">Achievements &amp; Trophies</h3></div>' +
            '<p style="font-size:12px;color:var(--muted);margin:0 16px 12px">Verified achievements earned through the academy — ' +
            'examinations, distinctions, recitals and awards.</p>' +
            (list.length
                ? '<div class="grid grid--2" style="padding:0 16px 16px;gap:12px">' + cards + '</div>'
                : emptyState('🏆', 'No achievements recorded yet — every verified result will appear here.')) +
            '</div>';
    }

    const SUPPORT_STATUS_LABEL = { open: 'Awaiting reply', replied: 'Replied by academy', resolved: 'Resolved' };

    function renderHelp() {
        const mine = (state.support || []).map(function (r) {
            return '<div class="list__row">' +
                '<div class="list__body"><div class="list__title">' + esc(r.subject) + '</div>' +
                '<div class="list__sub">' + esc(SUPPORT_STATUS_LABEL[r.status] || r.status) +
                (r.reply_count ? ' · ' + r.reply_count + ' repl' + (r.reply_count === 1 ? 'y' : 'ies') : '') +
                ' · ' + esc((r.created_at || '').slice(0, 10)) + '</div></div>' +
                '<div class="list__actions"><button class="btn-p btn-p--sm btn-p--ghost" data-action="open-support" data-id="' + r.id + '">Open</button></div>' +
                '</div>';
        }).join('');

        return '<div class="grid grid--2">' +
            '<div class="card"><h3 class="card__title" style="margin-bottom:10px">Help & Support</h3>' +
            '<p style="font-size:13.5px;color:var(--text-2);line-height:1.6">' +
            'Questions about classes, fees, or the portal? Reach the academy:</p>' +
            '<ul class="pack__perks"><li>Front desk: during academy hours</li>' +
            '<li>Email: chankarts.official@gmail.com</li>' +
            '<li>WhatsApp: use the number on your fee receipt</li></ul>' +
            '<h3 class="card__title" style="margin:16px 0 10px">Contact Academy Administration</h3>' +
            '<div class="field-p"><label>Subject</label><input id="supSubject" maxlength="200"></div>' +
            '<div class="field-p"><label>Message</label><textarea id="supMessage" rows="4"></textarea></div>' +
            '<div class="btn-row"><button class="btn-p" data-action="send-support">Send to Administration</button></div>' +
            '<p style="font-size:11px;color:var(--muted);margin-top:8px">Your message goes to the academy admin team inside this ' +
            'portal. Replies appear here and as a portal notification.</p>' +
            '</div>' +
            '<div class="card"><h3 class="card__title" style="margin-bottom:10px">My Requests</h3>' +
            (mine || emptyState('✉', 'No messages to the academy yet.')) + '</div>' +
            '<div class="card"><h3 class="card__title" style="margin-bottom:10px">Class Policies</h3>' +
            '<ul class="pack__perks">' +
            '<li>Rescheduling requests must be made at least 24 hours before the class start time. ' +
            'Inside 24 hours, please contact the academy directly.</li>' +
            '<li>Reschedule requests are reviewed by the academy — classes are never marked absent by the portal.</li>' +
            '<li>Standard classes run 60 minutes; legacy 30-minute slots are honoured.</li>' +
            '<li>Monthly fees are due as per your package (4 or 8 classes).</li>' +
            '</ul></div></div>';
    }

    async function sendSupport() {
        const subject = (document.getElementById('supSubject') || {}).value || '';
        const message = (document.getElementById('supMessage') || {}).value || '';
        if (subject.trim().length < 3 || message.trim().length < 5) {
            toast('Please add a subject and a message', 'error');
            return;
        }
        await api('/portal/support', {
            method: 'POST',
            body: JSON.stringify({ subject: subject.trim(), message: message.trim() }),
        });
        toast('Message sent to academy administration');
        await refreshAll();
    }

    async function openSupportThread(id) {
        const t = await api('/portal/support/' + id);
        const replies = (t.replies || []).map(function (r) {
            return '<div style="margin:8px 0;padding:10px 12px;border-radius:8px;background:' +
                (r.author_role === 'admin' ? 'var(--ivory)' : 'var(--paper)') + ';border:1px solid var(--line)">' +
                '<div style="font-size:11px;color:var(--muted);margin-bottom:4px">' +
                (r.author_role === 'admin' ? 'Academy Administration' : 'You') + ' · ' +
                esc((r.created_at || '').slice(0, 16).replace('T', ' ')) + '</div>' +
                '<div style="font-size:13px;line-height:1.6;white-space:pre-wrap">' + esc(r.body) + '</div></div>';
        }).join('');
        openModal(modalShell('Conversation: ' + t.subject,
            SUPPORT_STATUS_LABEL[t.status] || t.status, '' +
            '<div style="max-height:46vh;overflow:auto">' + (replies || '<p style="color:var(--muted);font-size:12px">No replies yet.</p>') + '</div>' +
            (t.status === 'resolved'
                ? '<p style="font-size:12px;color:var(--muted);margin-top:10px">This conversation is resolved. Please submit a new request if you need further help.</p>'
                : '<div class="field-p" style="margin-top:10px"><label>Add a message</label><textarea id="supReply" rows="3"></textarea></div>' +
                  '<div class="btn-row"><button class="btn-p" data-action="reply-support" data-id="' + t.id + '">Send</button>' +
                  '<button class="btn-p btn-p--ghost" data-modal-close>Close</button></div>')));
    }

    async function replySupport(id) {
        const body = (document.getElementById('supReply') || {}).value || '';
        if (body.trim().length < 1) { toast('Write a message first', 'error'); return; }
        await api('/portal/support/' + id + '/reply', { method: 'POST', body: JSON.stringify({ body: body.trim() }) });
        closeModal();
        toast('Message added');
        await refreshAll();
    }

    // ------------------------------------------------------------------
    // Render orchestration
    // ------------------------------------------------------------------
    async function loadHelp() {
        state.support = await api('/portal/support');
    }

    const loaders = {
        achievements: loadAchievements,
        help: loadHelp,
        dashboard: loadDashboard,
        classes: loadClasses,
        billing: loadBilling,
        assignments: loadAssignments,
        materials: loadMaterials,
        reports: loadReports,
        syllabus: loadSyllabus,
        exams: loadExams,
        resources: loadResources,
        remarks: loadRemarks,
    };

    const renderers = {
        dashboard: function () { return isFaculty() ? renderFacultyDashboard() : renderStudentDashboard(); },
        classes: renderClasses,
        billing: renderBilling,
        assignments: renderAssignments,
        materials: renderMaterials,
        reports: renderReports,
        syllabus: renderSyllabus,
        exams: renderExams,
        resources: renderResources,
        remarks: renderRemarks,
        achievements: renderAchievements,
        profile: renderProfile,
        help: renderHelp,
    };

    async function render() {
        const root = document.getElementById('portalRoot');
        if (!root) return;

        root.innerHTML =
            renderTopbar() +
            '<div class="portal-shell">' + renderSidebar() +
            '<main class="portal-main" id="portalMain">' +
            '<div id="portalSection">' + loadingState() + '</div>' +
            '</main></div>';

        bindShell();

        if (!loaders[state.section]) {
            // paintSection keeps the shared shell (topbar + sidebar) intact;
            // paint() replaced #portalRoot entirely and stripped navigation.
            paintSection(renderers[state.section]());
            return;
        }

        try {
            if (!state['loaded_' + state.section] || state.section === 'dashboard') {
                await loaders[state.section]();
            }
            paintSection(renderers[state.section]());
        } catch (err) {
            paintSection('<div class="card">' + emptyState('⚠', err.message) + '</div>');
        }
    }

    function paintSection(html) {
        const el = document.getElementById('portalSection');
        if (el) el.innerHTML = html;
        bindSection();
        mountRazorpayButtons();
    }

    function paint(html) {
        const root = document.getElementById('portalRoot');
        if (root) {
            root.innerHTML = html;
            bindSection();
        }
    }

    function markLoaded(section) {
        state['loaded_' + section] = true;
    }

    // ------------------------------------------------------------------
    // Events
    // ------------------------------------------------------------------
    function bindShell() {
        const root = document.getElementById('portalRoot');
        if (!root) return;

        root.querySelectorAll('[data-portal-nav]').forEach(function (btn) {
            btn.addEventListener('click', function () { go(btn.getAttribute('data-portal-nav')); });
        });

        const menu = root.querySelector('[data-portal-menu]');
        if (menu) {
            menu.addEventListener('click', function () {
                state.sidebarOpen = !state.sidebarOpen;
                const sidebar = document.getElementById('portalSidebar');
                if (sidebar) sidebar.classList.toggle('portal-sidebar--open', state.sidebarOpen);
            });
        }

        const notif = root.querySelector('[data-portal-notif]');
        if (notif) {
            notif.addEventListener('click', async function () {
                state.notifOpen = !state.notifOpen;
                if (state.notifOpen && !state.notifications.length) {
                    try {
                        state.notifications = await api('/portal/notifications');
                        await api('/portal/notifications/read', { method: 'POST', body: '{}' });
                    } catch (e) { /* ignore */ }
                }
                render();
            });
        }

        const logout = root.querySelector('[data-portal-logout]');
        if (logout) {
            logout.addEventListener('click', function () {
                localStorage.removeItem('academy_token');
                localStorage.removeItem('academy_user');
                window.location.href = window.AppPath('/academy/login');
            });
        }

        const home = root.querySelector('[data-portal-home]');
        if (home) {
            home.addEventListener('click', function (e) { e.preventDefault(); go('dashboard'); });
        }
    }

    function bindSection() {
        const root = document.getElementById('portalRoot');
        if (!root) return;

        root.querySelectorAll('[data-portal-nav]').forEach(function (btn) {
            if (btn.dataset.bound) return;
            btn.dataset.bound = '1';
            btn.addEventListener('click', function () { go(btn.getAttribute('data-portal-nav')); });
        });

        root.querySelectorAll('[data-cal-prev]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const anchor = state.calMonth || new Date();
                state.calMonth = new Date(anchor.getFullYear(), anchor.getMonth() - 1, 1);
                state.calSelected = null;
                refreshClasses();
            });
        });
        root.querySelectorAll('[data-cal-next]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const anchor = state.calMonth || new Date();
                state.calMonth = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 1);
                state.calSelected = null;
                refreshClasses();
            });
        });
        root.querySelectorAll('[data-cal-day]').forEach(function (cell) {
            cell.addEventListener('click', function () {
                const iso = cell.getAttribute('data-cal-day');
                state.calSelected = (state.calSelected === iso) ? null : iso;
                paintSection(state.section === 'classes' ? renderClasses() : renderStudentDashboard());
            });
        });

        root.querySelectorAll('[data-classview]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                state.classView = btn.getAttribute('data-classview');
                paintSection(renderClasses());
            });
        });
        root.querySelectorAll('[data-billingtab]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                state.billingTab = btn.getAttribute('data-billingtab');
                paintSection(renderBilling());
            });
        });
        root.querySelectorAll('[data-assignmenttab]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                state.assignmentTab = btn.getAttribute('data-assignmenttab');
                paintSection(renderAssignments());
            });
        });
        root.querySelectorAll('[data-matfilter]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                state.materialFilter = btn.getAttribute('data-matfilter');
                paintSection(renderMaterials());
            });
        });
        root.querySelectorAll('[data-restab]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                state.resourceTab = btn.getAttribute('data-restab');
                paintSection(renderResources());
            });
        });
        root.querySelectorAll('[data-child]').forEach(function (btn) {
            btn.addEventListener('click', async function () {
                state.activeStudentId = btn.getAttribute('data-child');
                state.loaded_dashboard = false;
                state.loaded_syllabus = false;
                state.loaded_billing = false;
                state.loaded_achievements = false;
                await render();
            });
        });

        root.querySelectorAll('[data-action]').forEach(function (btn) {
            btn.addEventListener('click', handleAction);
        });
    }

    async function refreshClasses() {
        try {
            await loadClasses();
            paintSection(state.section === 'classes' ? renderClasses() : renderStudentDashboard());
        } catch (err) {
            toast(err.message, 'error');
        }
    }

    // ------------------------------------------------------------------
    // Actions (modals + API writes)
    // ------------------------------------------------------------------
    function openModal(html) {
        closeModal();
        const backdrop = document.createElement('div');
        backdrop.className = 'modal-p-backdrop';
        backdrop.id = 'portalModal';
        backdrop.innerHTML = '<div class="modal-p">' + html + '</div>';
        backdrop.addEventListener('click', function (e) {
            if (e.target === backdrop) closeModal();
        });
        document.body.appendChild(backdrop);
        backdrop.querySelectorAll('[data-modal-close]').forEach(function (btn) {
            btn.addEventListener('click', closeModal);
        });
        return backdrop;
    }

    function closeModal() {
        const el = document.getElementById('portalModal');
        if (el) el.remove();
    }

    function modalShell(title, sub, bodyHtml) {
        return '<h3 class="modal-p__title">' + esc(title) + '</h3>' +
            (sub ? '<p class="modal-p__sub">' + esc(sub) + '</p>' : '') +
            bodyHtml;
    }

    async function handleAction(event) {
        const btn = event.currentTarget;
        const action = btn.getAttribute('data-action');
        const id = btn.getAttribute('data-id');

        try {
            if (action === 'download') {
                await downloadFile(btn.getAttribute('data-name'), btn.getAttribute('data-filename'));
                return;
            }
            if (action === 'complete-session') return completeSession(id);
            if (action === 'flag-session') return flagSession(id);
            if (action === 'cancel-session') return cancelSession(id);
            if (action === 'reschedule-session') return rescheduleSession(id);
            if (action === 'new-session') return newSessionModal();
            if (action === 'submit-homework') return submitHomeworkModal(id);
            if (action === 'review-submission') return reviewModal(id);
            if (action === 'new-assignment') return newAssignmentModal();
            if (action === 'new-material') return newMaterialModal();
            if (action === 'go-achievements') return go('achievements');
            if (action === 'report-payment') return reportPaymentModal();
            if (action === 'view-receipt') return openAuthedBlob('/billing/payments/' + id + '/receipt', 'receipt.html');
            if (action === 'export-statement') {
                const sid = state.statement && state.statement.students[0] ? state.statement.students[0].student_id : '';
                return openAuthedBlob('/billing/statement/export?' + (state.role === 'parent' ? 'family=1' : 'student_id=' + sid), 'statement.csv');
            }
            if (action === 'send-support') return sendSupport();
            if (action === 'open-support') return openSupportThread(id);
            if (action === 'reply-support') return replySupport(id);
            if (action === 'new-report') return newReportModal();
            if (action === 'edit-report') return editReportModal(id);
            if (action === 'submit-report') return submitReport(id);
            if (action === 'view-report') return viewReport(id);
            if (action === 'pay-invoice') return payInvoice(id);
            if (action === 'progress') return updateProgress(btn.getAttribute('data-item'), btn.getAttribute('data-status'));
            if (action === 'new-exam') return newExamModal();
            if (action === 'new-milestone') return newMilestoneModal();
            if (action === 'exam-status') return examStatusModal(id);
            if (action === 'edit-profile') return editProfileModal();
        } catch (err) {
            toast(err.message, 'error');
        }
    }

    function enrolOptions(selectedId) {
        return state.enrollments.map(function (e) {
            return '<option value="' + esc(e.id) + '"' + (e.id === selectedId ? ' selected' : '') + '>' +
                esc(e.student_name + ' — ' + e.programme_name) + '</option>';
        }).join('');
    }

    async function completeSession(id) {
        const sess = state.sessions.find(function (x) { return x.id === id; }) || {};
        const ctx = '<div class="field-p"><div style="background:var(--ivory);border:1px solid var(--line);border-radius:8px;padding:12px 14px;font-size:13px;line-height:1.7">' +
            '<strong>' + esc(sess.student_name || 'Student') + '</strong>' +
            (sess.student_cma ? ' · ' + esc(sess.student_cma) : '') + '<br>' +
            esc(sess.programme || sess.instrument || 'Class') + ' · ' +
            esc(fmtLong(sess.scheduled_date)) + ' · ' +
            esc((sess.scheduled_start || '').slice(0, 5)) + '–' + esc((sess.scheduled_end || '').slice(0, 5)) +
            '</div></div>';
        openModal(modalShell('Mark Class Completed', 'Confirm the lesson took place, then record what was covered.', '' +
            '<form class="form-p" id="completeForm">' +
            ctx +
            '<div class="field-p"><label>Topics covered</label><textarea name="topics_covered" placeholder="Scales, pieces, theory…"></textarea></div>' +
            '<div class="field-p"><label>Lesson note (how did the student do?)</label><textarea name="faculty_remarks" placeholder="Brief lesson note"></textarea></div>' +
            '<div class="field-p"><label>Practice recommendations</label><textarea name="practice_recommendations" placeholder="What to practise before the next class"></textarea></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Save Completion</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('completeForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            if (!window.confirm('Mark this class as completed? This records that the lesson took place.')) return;
            const data = Object.fromEntries(new FormData(e.target).entries());
            await api('/sessions/' + id + '/complete', { method: 'POST', body: JSON.stringify(data) });
            closeModal();
            toast('Class marked completed');
            state.sessions = [];
            await refreshAll();
        });
    }

    async function flagSession(id) {
        openModal(modalShell('Request Reschedule', 'The class stays on the schedule until the academy confirms a new time.', '' +
            '<form class="form-p" id="flagForm">' +
            '<div class="field-p"><label>Reason</label><textarea name="reason" required placeholder="Why does this class need to move?"></textarea></div>' +
            '<div class="field-p"><label>Preferred new date (optional)</label><input type="date" name="preferred_date"></div>' +
            '<div class="field-row-p"><div class="field-p field-p--half"><label>Preferred start</label>' +
            '<input type="time" name="preferred_start"></div>' +
            '<div class="field-p field-p--half"><label>Preferred end</label>' +
            '<input type="time" name="preferred_end"></div></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Send Request</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('flagForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target).entries());
            await api('/sessions/' + id + '/flag-reschedule', { method: 'POST', body: JSON.stringify(data) });
            closeModal();
            toast('Reschedule request sent');
            await refreshAll();
        });
    }

    async function cancelSession(id) {
        if (!window.confirm('Cancel this class?')) return;
        await api('/sessions/' + id + '/cancel', { method: 'POST', body: JSON.stringify({ reason: 'Cancelled by faculty' }) });
        toast('Class cancelled');
        await refreshAll();
    }

    async function rescheduleSession(id) {
        openModal(modalShell('Schedule Replacement', 'The original class stays in history; a new session is created.', '' +
            '<form class="form-p" id="reschForm">' +
            '<div class="field-row-p">' +
            '<div class="field-p"><label>Date</label><input type="date" name="new_date" required></div>' +
            '<div class="field-p"><label>Start</label><input type="time" name="new_start" value="10:00" required></div>' +
            '<div class="field-p"><label>End</label><input type="time" name="new_end" value="11:00" required></div>' +
            '</div>' +
            '<div class="field-p"><label>Reason</label><input type="text" name="reason" value="Faculty rescheduled" required></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Create Replacement</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('reschForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target).entries());
            await api('/sessions/' + id + '/reschedule', { method: 'POST', body: JSON.stringify(data) });
            closeModal();
            toast('Replacement class scheduled');
            await refreshAll();
        });
    }

    async function newSessionModal() {
        if (!state.enrollments.length) state.enrollments = await api('/portal/enrollments');
        if (!state.enrollments.length) {
            toast('No enrolments available for scheduling', 'error');
            return;
        }
        openModal(modalShell('New Class Session', 'Standard sessions are at least 60 minutes.', '' +
            '<form class="form-p" id="sessForm">' +
            '<div class="field-p"><label>Enrolment</label><select name="enrollment_id" required>' + enrolOptions() + '</select></div>' +
            '<div class="field-row-p">' +
            '<div class="field-p"><label>Date</label><input type="date" name="scheduled_date" required></div>' +
            '<div class="field-p"><label>Start</label><input type="time" name="scheduled_start" value="10:00" required></div>' +
            '<div class="field-p"><label>End</label><input type="time" name="scheduled_end" value="11:00" required></div>' +
            '</div>' +
            '<div class="field-p"><label><input type="checkbox" name="is_online" style="width:auto"> Online class</label></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Schedule</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('sessForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const payload = {
                enrollment_id: form.enrollment_id.value,
                scheduled_date: form.scheduled_date.value,
                scheduled_start: form.scheduled_start.value,
                scheduled_end: form.scheduled_end.value,
                is_online: form.is_online.checked,
            };
            await api('/sessions', { method: 'POST', body: JSON.stringify(payload) });
            closeModal();
            toast('Session scheduled');
            await refreshAll();
        });
    }

    async function submitHomeworkModal(id) {
        openModal(modalShell('Submit Homework', 'PDF, JPG or PNG' + (isFaculty() ? '' : ' (audio allowed when enabled)'), '' +
            '<form class="form-p" id="hwForm">' +
            '<div class="field-p"><label>Notes</label><textarea name="notes" placeholder="What did you practise?"></textarea></div>' +
            '<div class="field-p"><label>File</label><input type="file" name="file" accept=".pdf,.jpg,.jpeg,.png,.mp3" required></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Upload</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('hwForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const fd = new FormData();
            fd.append('notes', form.notes.value);
            const file = form.file.files[0];
            if (file) fd.append('files', file, file.name);
            await api('/learning/assignments/' + id + '/submit', { method: 'POST', body: fd });
            closeModal();
            toast('Homework submitted');
            state.loaded_assignments = false;
            await refreshAll();
        });
    }

    async function reviewModal(submissionId) {
        openModal(modalShell('Review Submission', 'Feedback is shared with the student immediately.', '' +
            '<form class="form-p" id="revForm">' +
            '<div class="field-p"><label>Feedback</label><textarea name="feedback" required placeholder="What went well, what to improve"></textarea></div>' +
            '<div class="field-p"><label>Outcome</label><select name="status">' +
            '<option value="reviewed">Reviewed — looks good</option>' +
            '<option value="revision_requested">Request revision</option></select></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Save Review</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('revForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target).entries());
            await api('/learning/submissions/' + submissionId + '/review', { method: 'POST', body: JSON.stringify(data) });
            closeModal();
            toast('Review saved');
            await refreshAll();
        });
    }

    async function newAssignmentModal() {
        if (!state.enrollments.length) state.enrollments = await api('/portal/enrollments');
        if (!state.enrollments.length) {
            toast('No enrolments available', 'error');
            return;
        }
        openModal(modalShell('New Assignment', 'Students see this in their portal immediately.', '' +
            '<form class="form-p" id="asgForm">' +
            '<div class="field-p"><label>Title</label><input name="title" required placeholder="e.g. C major scales"></div>' +
            '<div class="field-p"><label>Instructions</label><textarea name="instructions" placeholder="What to practise and how"></textarea></div>' +
            '<div class="field-row-p">' +
            '<div class="field-p"><label>Enrolment</label><select name="enrollment_id">' + enrolOptions() + '</select></div>' +
            '<div class="field-p"><label>Due date</label><input type="date" name="due_date"></div>' +
            '</div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Create</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('asgForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const payload = {
                title: form.title.value,
                instructions: form.instructions.value || null,
                enrollment_id: form.enrollment_id.value,
                due_date: form.due_date.value || null,
            };
            await api('/learning/assignments', { method: 'POST', body: JSON.stringify(payload) });
            closeModal();
            toast('Assignment created');
            await refreshAll();
        });
    }

    async function newMaterialModal() {
        openModal(modalShell('Upload Study Material', 'Files are validated (PDF/JPG/PNG/audio) and stored securely.', '' +
            '<form class="form-p" id="matForm">' +
            '<div class="field-p"><label>Title</label><input name="title" required></div>' +
            '<div class="field-p"><label>Category</label><select name="category">' +
            ['technique', 'repertoire', 'theory', 'ear_training', 'rhythm', 'exam_preparation', 'practice']
                .map(function (c) { return '<option value="' + c + '">' + c.replace('_', ' ') + '</option>'; }).join('') +
            '</select></div>' +
            '<div class="field-p"><label>Description</label><textarea name="description"></textarea></div>' +
            '<div class="field-p"><label>File (optional if link given)</label><input type="file" name="file" accept=".pdf,.jpg,.jpeg,.png,.mp3"></div>' +
            '<div class="field-p"><label>External link (https://…)</label><input type="url" name="link_url" placeholder="https://"></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Save</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('matForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const fd = new FormData();
            fd.append('title', form.title.value);
            fd.append('category', form.category.value);
            fd.append('description', form.description.value || '');
            if (form.link_url.value) fd.append('link_url', form.link_url.value);
            if (form.file.files[0]) fd.append('file', form.file.files[0]);
            await api('/learning/materials', { method: 'POST', body: fd });
            closeModal();
            toast('Material published');
            await refreshAll();
        });
    }

    function reportFormHtml(r, enrollmentId, month) {
        return '<form class="form-p" id="repForm">' +
            '<div class="field-row-p">' +
            '<div class="field-p"><label>Enrolment</label><select name="enrollment_id"' +
            (r ? ' disabled' : '') + '>' + enrolOptions(enrollmentId) + '</select></div>' +
            '<div class="field-p"><label>Month</label><input type="month" name="report_month" value="' +
            esc(month || todayYm()) + '" required' + (r ? ' disabled' : '') + '></div>' +
            '</div>' +
            '<div class="field-p"><label>Progress summary <span style="color:var(--muted);font-weight:400">(from class records)</span></label>' +
            '<textarea name="progress_summary">' + esc(r ? (r.progress_summary || '') : '') + '</textarea></div>' +
            '<div class="field-p"><label>Topics covered <span style="color:var(--muted);font-weight:400">(from class records)</span></label>' +
            '<textarea name="topics_covered" rows="5">' + esc(r ? (r.topics_covered || '') : '') + '</textarea></div>' +
            '<div class="field-p"><label>Practice recommendations <span style="color:var(--muted);font-weight:400">(from class records)</span></label>' +
            '<textarea name="practice_recommendations">' + esc(r ? (r.practice_recommendations || '') : '') + '</textarea></div>' +
            '<div class="field-row-p">' +
            '<div class="field-p"><label>Strengths / achievements</label><textarea name="strengths">' + esc(r ? (r.strengths || '') : '') + '</textarea></div>' +
            '<div class="field-p"><label>Areas for improvement / concerns</label><textarea name="areas_for_improvement">' + esc(r ? (r.areas_for_improvement || '') : '') + '</textarea></div>' +
            '</div>' +
            '<div class="field-p"><label>Recommendations / next month focus</label><textarea name="next_month_focus">' + esc(r ? (r.next_month_focus || '') : '') + '</textarea></div>' +
            '<div class="field-p"><label>Faculty remarks</label><textarea name="faculty_remarks">' + esc(r ? (r.faculty_remarks || '') : '') + '</textarea></div>' +
            '<div class="field-p"><label>Private staff notes (never shown to family)</label><textarea name="staff_notes">' + esc(r ? (r.staff_notes || '') : '') + '</textarea></div>' +
            '<div class="btn-row">' +
            (r ? '<button type="submit" class="btn-p">Save Draft</button>' +
                 '<button type="button" class="btn-p" data-action="submit-report" data-id="' + r.id + '">Submit for Review</button>'
               : '<button type="submit" class="btn-p">Save Draft</button>') +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>';
    }

    function bindReportForm(report) {
        document.getElementById('repForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const enrollment = state.enrollments.find(function (x) { return x.id === form.enrollment_id.value; });
            const payload = {
                student_id: report ? report.student_id : (enrollment ? enrollment.student_id : state.activeStudentId),
                enrollment_id: report ? report.enrollment_id : form.enrollment_id.value,
                report_month: report ? report.report_month : form.report_month.value,
                progress_summary: form.progress_summary.value || null,
                topics_covered: form.topics_covered.value || null,
                practice_recommendations: form.practice_recommendations.value || null,
                strengths: form.strengths.value || null,
                areas_for_improvement: form.areas_for_improvement.value || null,
                next_month_focus: form.next_month_focus.value || null,
                faculty_remarks: form.faculty_remarks.value || null,
                staff_notes: form.staff_notes.value || null,
            };
            if (report) {
                await api('/learning/reports/' + report.id, { method: 'PATCH', body: JSON.stringify(payload) });
            } else {
                await api('/learning/reports', { method: 'POST', body: JSON.stringify(payload) });
            }
            closeModal();
            toast('Draft report saved');
            await refreshAll();
        });
    }

    async function newReportModal() {
        if (!state.enrollments.length) state.enrollments = await api('/portal/enrollments');
        if (!state.enrollments.length) {
            toast('No enrolments available', 'error');
            return;
        }
        openModal(modalShell('Prepare Monthly Report',
            'Generate the draft from your class records, then add your observations.', '' +
            '<form class="form-p" id="genForm">' +
            '<div class="field-row-p">' +
            '<div class="field-p"><label>Enrolment</label><select name="enrollment_id">' + enrolOptions() + '</select></div>' +
            '<div class="field-p"><label>Month</label><input type="month" name="report_month" value="' + todayYm() + '" required></div>' +
            '</div>' +
            '<p style="font-size:12px;color:var(--muted);line-height:1.6">The draft collects topics covered, lesson notes and ' +
            'practice recommendations from your completed classes for the month. Nothing is invented — classes without ' +
            'lesson notes are listed as missing. You review the draft and add achievements, concerns and recommendations.</p>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Generate Draft from Class Records</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('genForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const enrollmentId = form.enrollment_id.value;
            const month = form.report_month.value;
            const body = { enrollment_id: enrollmentId, report_month: month };
            let res;
            try {
                res = await api('/learning/reports/generate-draft', { method: 'POST', body: JSON.stringify(body) });
            } catch (err) {
                if (/already exists/i.test(err.message || '')) {
                    if (!window.confirm('A report already exists for this month. Regenerate the draft from class records? ' +
                        'Fields you wrote yourself are kept.')) return;
                    res = await api('/learning/reports/generate-draft', {
                        method: 'POST',
                        body: JSON.stringify({ enrollment_id: enrollmentId, report_month: month, confirm_overwrite: true }),
                    });
                } else {
                    toast(err.message || 'Could not generate the draft', 'error');
                    return;
                }
            }
            openModal(modalShell('Review Monthly Report',
                'Check the generated summary and add your own observations.', reportFormHtml(res, enrollmentId, month)));
            bindReportForm(res);
            toast('Draft prepared from class records');
        });
    }

    async function editReportModal(id) {
        const r = state.reports.find(function (x) { return x.id === id; });
        if (!r) return;
        openModal(modalShell('Edit Monthly Report', 'Generated content and your observations.', reportFormHtml(r)));
        bindReportForm(r);
    }

    async function submitReport(id) {
        const r = state.reports.find(function (x) { return x.id === id; });
        if (!r) return;
        await api('/learning/reports/' + id + '/submit', { method: 'POST', body: '{}' });
        closeModal();
        toast('Report submitted for review');
        await refreshAll();
    }

    async function viewReport(id) {
        const report = state.reports.find(function (r) { return r.id === id; });
        if (!report) return;
        const blocks = [
            ['Progress Summary', report.progress_summary],
            ['Topics Covered', report.topics_covered],
            ['Strengths', report.strengths],
            ['Areas for Improvement', report.areas_for_improvement],
            ['Practice Recommendations', report.practice_recommendations],
            ['Next Month Focus', report.next_month_focus],
            ['Faculty Remarks', report.faculty_remarks],
        ].map(function (pair) {
            return '<div class="report__block" style="margin-bottom:12px"><h4>' + esc(pair[0]) + '</h4>' +
                '<p>' + esc(pair[1] || '—') + '</p></div>';
        }).join('');
        openModal(modalShell('Faculty Report — ' + monthLabel(report.report_month),
            'Revision ' + report.revision + ' · ' + report.status, blocks));
    }

    const PENDING_CONFIRMATION_NOTICE = {
        title: 'Payment Confirmation Pending',
        body: 'Thank you for your payment. Your transaction is awaiting verification by ChankArts Music ' +
            'Academy. Our administration team will verify your payment and update your fee status in the ' +
            'portal within 24 hours. Please avoid making another payment while your transaction is being verified.',
    };

    function pendingNoticeHtml() {
        return '<div class="card" style="border:1px solid var(--accent, #B58A35);margin:12px 0">' +
            '<h3 class="card__title" style="margin:0 0 8px">' + PENDING_CONFIRMATION_NOTICE.title + '</h3>' +
            '<p style="font-size:13px;line-height:1.7;color:var(--text-2);margin:0">' +
            PENDING_CONFIRMATION_NOTICE.body + '</p></div>';
    }

    function showPendingConfirmation() {
        openModal(modalShell(PENDING_CONFIRMATION_NOTICE.title, '', '' +
            '<p style="font-size:13.5px;line-height:1.8;color:var(--text-2)">' + PENDING_CONFIRMATION_NOTICE.body + '</p>' +
            '<div class="btn-row" style="margin-top:12px"><button class="btn-p" data-modal-close>Close</button></div>'));
    }

    async function reportPaymentModal() {
        openModal(modalShell('Report a Payment',
            'Made a payment outside this portal (payment button, bank transfer, counter)? Report it here.', '' +
            '<form class="form-p" id="reportPayForm">' +
            '<div class="field-p"><label>Amount (₹)</label><input name="amount" type="number" step="0.01" min="1" required></div>' +
            '<div class="field-p"><label>Method</label><select name="method">' +
            '<option value="upi">UPI</option><option value="cash">Cash</option>' +
            '<option value="bank_transfer">Bank transfer</option><option value="card">Card / payment button</option>' +
            '</select></div>' +
            '<div class="field-p"><label>Transaction / reference number</label><input name="reference" placeholder="e.g. Razorpay pay_XXXX or UTR"></div>' +
            '<div class="field-p"><label>Date paid</label><input name="paid_at" type="date"></div>' +
            '<div class="field-p"><label>Note (optional)</label><textarea name="notes" rows="2"></textarea></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Submit for Verification</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('reportPayForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const sid = state.activeStudentId ||
                (state.role === 'student' && state.me && state.me.student ? state.me.student.id : null);
            if (!sid) { toast('Select a student first (parent accounts)', 'error'); return; }
            await api('/billing/payments/report', {
                method: 'POST',
                body: JSON.stringify({
                    student_id: sid,
                    amount_paise: Math.round(parseFloat(form.amount.value || '0') * 100),
                    method: form.method.value,
                    reference: form.reference.value || null,
                    paid_at: form.paid_at.value || null,
                    notes: form.notes.value || null,
                }),
            });
            closeModal();
            showPendingConfirmation();
            state.statement = null;
            await refreshAll();
        });
    }

    async function openAuthedBlob(path, filename) {
        try {
            const response = await fetch(BASE + path, {
                headers: token() ? { Authorization: 'Bearer ' + token() } : {},
            });
            if (!response.ok) throw new Error('Download failed');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
        } catch (err) {
            toast(err.message, 'error');
        }
    }

    function loadRazorpayCheckout() {
        return new Promise(function (resolve, reject) {
            if (window.Razorpay) return resolve();
            const script = document.createElement('script');
            script.src = 'https://checkout.razorpay.com/v1/checkout.js';
            script.onload = resolve;
            script.onerror = function () { reject(new Error('Could not load the Razorpay checkout')); };
            document.head.appendChild(script);
        });
    }

    async function payInvoice(id) {
        try {
            const order = await api('/billing/payments/orders', { method: 'POST', body: JSON.stringify({ invoice_id: id }) });
            if (!state.paymentConfig || !state.paymentConfig.enabled) {
                toast('Payment order ' + order.order_id + ' created — online checkout is not configured; settle at the academy or use the payment button');
                return;
            }
            await loadRazorpayCheckout();
            const rzp = new window.Razorpay({
                key: state.paymentConfig.key_id,
                order_id: order.order_id,
                name: 'ChankArts Music Academy',
                description: 'Fee payment',
                theme: { color: '#B58A35' },
                handler: async function (resp) {
                    try {
                        // server-side signature verification — the browser
                        // response alone is never trusted
                        await api('/billing/payments/verify', {
                            method: 'POST',
                            body: JSON.stringify({
                                razorpay_order_id: resp.razorpay_order_id,
                                razorpay_payment_id: resp.razorpay_payment_id,
                                razorpay_signature: resp.razorpay_signature,
                            }),
                        });
                        state.statement = null;
                        await refreshAll();
                        showPendingConfirmation();
                    } catch (err) {
                        toast(err.message, 'error');
                    }
                },
            });
            rzp.open();
        } catch (err) {
            toast(err.message, 'error');
        }
    }

    async function updateProgress(itemId, status) {
        if (!state.activeStudentId) {
            toast('Select a student first (parent accounts)', 'error');
            return;
        }
        await api('/learning/syllabus-progress/' + itemId +
            '?student_id=' + state.activeStudentId + '&enrollment_id=' + (state.enrollments[0] ? state.enrollments[0].id : ''),
            { method: 'POST', body: JSON.stringify({ status: status }) });
        toast('Progress updated');
        state.loaded_syllabus = false;
        await refreshAll();
    }

    async function newExamModal() {
        if (!state.enrollments.length) state.enrollments = await api('/portal/enrollments');
        openModal(modalShell('Add Exam', 'Board exams, graded assessments or recitals.', '' +
            '<form class="form-p" id="examForm">' +
            '<div class="field-p"><label>Enrolment</label><select name="enrollment_id">' + enrolOptions() + '</select></div>' +
            '<div class="field-row-p">' +
            '<div class="field-p"><label>Board</label><input name="board" value="Trinity" required></div>' +
            '<div class="field-p"><label>Grade</label><input name="grade" placeholder="1"></div>' +
            '<div class="field-p"><label>Instrument</label><input name="instrument" required></div>' +
            '</div>' +
            '<div class="field-p"><label>Submission deadline</label><input type="date" name="submission_deadline"></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Save</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('examForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const enrollment = state.enrollments.find(function (x) { return x.id === form.enrollment_id.value; });
            const payload = {
                student_id: enrollment ? enrollment.student_id : null,
                enrollment_id: form.enrollment_id.value,
                board: form.board.value,
                grade: form.grade.value || null,
                instrument: form.instrument.value,
                submission_deadline: form.submission_deadline.value || null,
            };
            await api('/learning/exams', { method: 'POST', body: JSON.stringify(payload) });
            closeModal();
            toast('Exam added');
            await refreshAll();
        });
    }

    async function examStatusModal(id) {
        const exam = state.exams.find(function (x) { return x.id === id; });
        if (!exam) return;
        openModal(modalShell('Update Exam', exam.board + ' Grade ' + (exam.grade || '—'), '' +
            '<form class="form-p" id="exUpd">' +
            '<div class="field-p"><label>Application status</label><select name="application_status">' +
            ['not_started', 'in_progress', 'submitted', 'confirmed'].map(function (s) {
                return '<option' + (exam.application_status === s ? ' selected' : '') + '>' + s + '</option>';
            }).join('') + '</select></div>' +
            '<div class="field-p"><label>Readiness</label><select name="readiness">' +
            ['', 'on_track', 'needs_work', 'ready'].map(function (s) {
                return '<option value="' + s + '"' + (exam.readiness === s ? ' selected' : '') + '>' + (s || 'unset') + '</option>';
            }).join('') + '</select></div>' +
            '<div class="field-p"><label>Notes</label><textarea name="notes">' + esc(exam.notes || '') + '</textarea></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Save</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('exUpd').addEventListener('submit', async function (e) {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target).entries());
            await api('/learning/exams/' + id, { method: 'PATCH', body: JSON.stringify(data) });
            closeModal();
            toast('Exam updated');
            await refreshAll();
        });
    }

    async function newMilestoneModal() {
        if (!state.enrollments.length) state.enrollments = await api('/portal/enrollments');
        openModal(modalShell('Add Milestone', 'Achievements, recitals or goals.', '' +
            '<form class="form-p" id="msForm">' +
            '<div class="field-p"><label>Student enrolment</label><select name="enrollment_id">' + enrolOptions() + '</select></div>' +
            '<div class="field-p"><label>Title</label><input name="title" required></div>' +
            '<div class="field-p"><label>Description</label><textarea name="description"></textarea></div>' +
            '<div class="field-p"><label>Due date</label><input type="date" name="due_date"></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Save</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('msForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const form = e.target;
            const enrollment = state.enrollments.find(function (x) { return x.id === form.enrollment_id.value; });
            await api('/learning/milestones', {
                method: 'POST',
                body: JSON.stringify({
                    student_id: enrollment ? enrollment.student_id : null,
                    enrollment_id: form.enrollment_id.value,
                    title: form.title.value,
                    description: form.description.value || null,
                    due_date: form.due_date.value || null,
                }),
            });
            closeModal();
            toast('Milestone added');
            await refreshAll();
        });
    }

    async function editProfileModal() {
        const student = (state.me || {}).student || {};
        openModal(modalShell('Edit Profile', 'Name, CMA ID and DOB are managed by the academy.', '' +
            '<form class="form-p" id="profForm">' +
            '<div class="field-p"><label>Phone</label><input name="phone" value="' + esc(student.phone || '') + '" placeholder="+91…"></div>' +
            '<div class="field-p"><label>Address</label><textarea name="address">' + esc(student.address || '') + '</textarea></div>' +
            '<div class="field-p"><label>Skill level</label><select name="skill_level">' +
            ['', 'beginner', 'intermediate', 'advanced'].map(function (s) {
                return '<option value="' + s + '"' + (student.skill_level === s ? ' selected' : '') + '>' + (s || 'unset') + '</option>';
            }).join('') + '</select></div>' +
            '<div class="btn-row"><button type="submit" class="btn-p">Save</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-modal-close>Cancel</button></div>' +
            '</form>'));
        document.getElementById('profForm').addEventListener('submit', async function (e) {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(e.target).entries());
            await api('/portal/profile', { method: 'PATCH', body: JSON.stringify(data) });
            closeModal();
            toast('Profile updated');
            state.me = await api('/portal/me');
            await render();
        });
    }

    // ------------------------------------------------------------------
    // Boot
    // ------------------------------------------------------------------
    async function refreshAll() {
        Object.keys(state).forEach(function (key) {
            if (key.indexOf('loaded_') === 0) state[key] = false;
        });
        await render();
    }

    async function init() {
        const stored = storedUser();
        if (!token() || ['student', 'parent', 'instructor'].indexOf(stored.role) < 0) {
            window.location.href = window.AppPath('/academy/login');
            return;
        }
        state.role = stored.role;
        state.section = sectionFromPath();
        state.calMonth = new Date();
        state.activeStudentId = null;

        try {
            state.me = await api('/portal/me');
            if (state.role === 'parent') {
                state.children = (state.me.children || []);
                if (state.children.length) state.activeStudentId = state.children[0].id;
            }
            state.notifications = await api('/portal/notifications');
            const materialsPromise = api('/learning/materials').then(function (m) {
                state.materials = m;
            }).catch(function () { state.materials = []; });
            const enrollmentsPromise = api('/portal/enrollments').then(function (e) {
                state.enrollments = e;
            }).catch(function () { state.enrollments = []; });
            await Promise.all([materialsPromise, enrollmentsPromise]);
        } catch (err) {
            console.error('Portal init failed', err);
        }

        await render();

        if (!window.__portalPopstateBound) {
            window.__portalPopstateBound = true;
            window.addEventListener('popstate', function () {
                const section = sectionFromPath();
                if (section !== state.section && document.getElementById('portalRoot')) {
                    state.section = section;
                    render();
                }
            });
        }
    }

    return {
        init: init,
        navigate: go,
    };
})();
