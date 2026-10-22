/* ============================================
   ChankArts Music Academy - Admin Dashboard
   ============================================ */

const Admin = (function() {
    'use strict';

    // API origin: window.CHANKARTS_API_BASE overrides (set in index.html when
    // the API lives on a different origin); same-origin in production.
    function apiOrigin() {
        return window.CHANKARTS_API_BASE !== undefined
            ? window.CHANKARTS_API_BASE
            : (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
                ? 'http://localhost:8000' : '');
    }

    const API_BASE = apiOrigin() + '/api/v1/admin';
    let currentSection = 'dashboard';
    let sidebarOpen = false;

    // ========================================
    // SVG Icon System (lightweight, stroke-based)
    // ========================================
    const SVG_ATTRS = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="18" height="18" aria-hidden="true"';

    const ICONS = {
        dashboard: `<svg ${SVG_ATTRS}><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>`,
        registrations: `<svg ${SVG_ATTRS}><path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/></svg>`,
        students: `<svg ${SVG_ATTRS}><circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/><circle cx="19" cy="6" r="1.5"/><path d="M19 7.5V11"/></svg>`,
        enrollments: `<svg ${SVG_ATTRS}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
        instructors: `<svg ${SVG_ATTRS}><circle cx="12" cy="7" r="3"/><path d="M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/><path d="M16 3.5 21 6l-5 2.5"/></svg>`,
        classes: `<svg ${SVG_ATTRS}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/></svg>`,
        fees: `<svg ${SVG_ATTRS}><rect x="2" y="6" width="20" height="13" rx="2"/><path d="M2 10h20"/><path d="M6 15h4"/></svg>`,
        attendance: `<svg ${SVG_ATTRS}><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12.5l2.5 2.5L16 9.5"/></svg>`,
        progress: `<svg ${SVG_ATTRS}><path d="M3 17l6-6 4 4 7-7"/><path d="M14 8h6v6"/></svg>`,
        exams: `<svg ${SVG_ATTRS}><circle cx="12" cy="9" r="5.5"/><path d="M8.5 13.5 7 21l5-2.5L17 21l-1.5-7.5"/></svg>`,
        assignments: `<svg ${SVG_ATTRS}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M9 13h6M9 17h4"/></svg>`,
        resources: `<svg ${SVG_ATTRS}><path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>`,
        reports: `<svg ${SVG_ATTRS}><path d="M3 21h18"/><rect x="5" y="11" width="3.5" height="7" rx="0.8"/><rect x="10.25" y="7" width="3.5" height="11" rx="0.8"/><rect x="15.5" y="13" width="3.5" height="5" rx="0.8"/></svg>`,
        settings: `<svg ${SVG_ATTRS}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1-1.55 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.55-1 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34h0a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55h0a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87v0a1.7 1.7 0 0 0 1.55 1H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/></svg>`,
        // Stat / status icons
        pending: `<svg ${SVG_ATTRS}><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>`,
        approved: `<svg ${SVG_ATTRS}><circle cx="12" cy="12" r="8.5"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/></svg>`,
        rejected: `<svg ${SVG_ATTRS}><circle cx="12" cy="12" r="8.5"/><path d="M9.5 9.5l5 5M14.5 9.5l-5 5"/></svg>`,
        info: `<svg ${SVG_ATTRS}><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><circle cx="12" cy="8" r="0.5" fill="currentColor"/></svg>`,
        mail: `<svg ${SVG_ATTRS}><rect x="3" y="5.5" width="18" height="13" rx="2"/><path d="M3.5 7l8.5 6 8.5-6"/></svg>`,
        clock: `<svg ${SVG_ATTRS}><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>`,
        wallet: `<svg ${SVG_ATTRS}><path d="M3 7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2"/><rect x="3" y="7" width="18" height="12" rx="2"/><circle cx="16" cy="13" r="1.2"/></svg>`,
        users: `<svg ${SVG_ATTRS}><circle cx="9" cy="8" r="3"/><path d="M3.5 19a5.5 5.5 0 0 1 11 0"/><circle cx="17" cy="9" r="2.5"/><path d="M15.5 15.5A4.5 4.5 0 0 1 21 19"/></svg>`,
        book: `<svg ${SVG_ATTRS}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
        // Empty states
        inbox: `<svg ${SVG_ATTRS}><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.5 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.5A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.5z"/></svg>`,
        warn: `<svg ${SVG_ATTRS}><path d="M12 3.5 22 20H2z"/><path d="M12 10v4"/><circle cx="12" cy="17" r="0.5" fill="currentColor"/></svg>`,
        search: `<svg ${SVG_ATTRS}><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>`,
        plus: `<svg ${SVG_ATTRS}><path d="M12 5v14M5 12h14"/></svg>`,
        menu: `<svg ${SVG_ATTRS}><path d="M4 6h16M4 12h16M4 18h16"/></svg>`,
        key: `<svg ${SVG_ATTRS}><circle cx="8" cy="15" r="3.5"/><path d="M10.5 12.5 20 3M17 6l2 2M15 8l2 2"/></svg>`,
    };

    function icon(name) {
        return ICONS[name] || ICONS.inbox;
    }

    // ========================================
    // Registration State
    // ========================================
    let regState = {
        requests: [],
        filtered: [],
        loading: false,
        error: null,
        search: '',
        statusFilter: 'all',
        programmeFilter: 'all',
        currentView: 'list', // 'list' | 'detail'
        selectedRequest: null,
        detailLoading: false,
        detailError: null,
        actionLoading: false,
    };

    // ========================================
    // API Helper
    // ========================================
    async function apiCall(endpoint, options = {}) {
        const token = localStorage.getItem('academy_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...options.headers,
        };

        try {
            const response = await fetch(`${API_BASE}${endpoint}`, {
                ...options,
                headers,
            });

            if (response.status === 401) {
                localStorage.removeItem('academy_token');
                localStorage.removeItem('academy_user');
                window.location.href = window.AppPath('/academy/login');
                return null;
            }

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || 'Request failed');
            }

            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    // General API helper for non-/admin paths (e.g. /learning, /sessions)
    async function apiV1Call(path, options = {}) {
        const base = apiOrigin() + '/api/v1';
        const token = localStorage.getItem('academy_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
            ...options.headers,
        };

        try {
            const response = await fetch(`${base}${path}`, { ...options, headers });
            if (response.status === 401) {
                localStorage.removeItem('academy_token');
                localStorage.removeItem('academy_user');
                window.location.href = window.AppPath('/academy/login');
                return null;
            }
            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                if (error.detail === 'PIN_CHANGE_REQUIRED') {
                    try {
                        const u = JSON.parse(localStorage.getItem('academy_user') || '{}');
                        u.must_change_pin = true;
                        localStorage.setItem('academy_user', JSON.stringify(u));
                    } catch (e) { /* ignore */ }
                    window.location.reload();
                }
                throw new Error(error.detail || 'Request failed');
            }
            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    // ========================================
    // Navigation
    // ========================================
    const NAV_ITEMS = [
        { section: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
        { section: 'registrations', label: 'Registration Requests', icon: 'registrations', badge: 'pending' },
        { section: 'support', label: 'Support Inbox', icon: 'inbox' },
        { section: 'students', label: 'Students', icon: 'students' },
        { section: 'enrollments', label: 'Enrollments', icon: 'enrollments' },
        { divider: true },
        { section: 'instructors', label: 'Instructors', icon: 'instructors' },
        { section: 'classes', label: 'Classes / Schedules', icon: 'classes' },
        { section: 'fees', label: 'Fees & Payments', icon: 'fees' },
        { section: 'attendance', label: 'Attendance', icon: 'attendance' },
        { section: 'progress', label: 'Progress', icon: 'progress' },
        { divider: true },
                { section: 'achievements', label: 'Achievements', icon: 'medal' },
        { section: 'syllabi', label: 'Syllabi', icon: 'reports' },
{ section: 'exams', label: 'Exams / Certifications', icon: 'exams' },
        { section: 'assignments', label: 'Assignments / Quizzes', icon: 'assignments' },
        { section: 'resources', label: 'Resources', icon: 'resources' },
        { section: 'reports', label: 'Reports', icon: 'reports' },
        { divider: true },
        { section: 'class-reports', label: 'Class Reports', icon: 'reports' },
        { section: 'reschedule-requests', label: 'Reschedule Requests', icon: 'clock' },
        { section: 'pin-resets', label: 'PIN Resets', icon: 'key' },
        { section: 'settings', label: 'Settings', icon: 'settings' },
    ];

    function renderSidebar() {
        return `
            <aside class="admin-sidebar ${sidebarOpen ? 'admin-sidebar--open' : ''}" id="adminSidebar">
                <div class="admin-sidebar__section">
                    <div class="admin-sidebar__label">Main</div>
                    ${NAV_ITEMS.slice(0, 4).map(item => {
                        if (item.divider) return '';
                        return `
                            <a href="#" class="admin-sidebar__link ${currentSection === item.section ? 'admin-sidebar__link--active' : ''}" 
                               data-section="${item.section}">
                                <span class="admin-sidebar__icon">${icon(item.icon)}</span>
                                <span>${item.label}</span>
                                ${item.badge ? `<span class="admin-sidebar__badge" id="pendingBadge">-</span>` : ''}
                            </a>
                        `;
                    }).join('')}
                </div>
                <div class="admin-sidebar__section">
                    <div class="admin-sidebar__label">Management</div>
                    ${NAV_ITEMS.slice(4, 9).map(item => {
                        if (item.divider) return '';
                        return `
                            <a href="#" class="admin-sidebar__link ${currentSection === item.section ? 'admin-sidebar__link--active' : ''}" 
                               data-section="${item.section}">
                                <span class="admin-sidebar__icon">${icon(item.icon)}</span>
                                <span>${item.label}</span>
                            </a>
                        `;
                    }).join('')}
                </div>
                <div class="admin-sidebar__section">
                    <div class="admin-sidebar__label">Academic</div>
                    ${NAV_ITEMS.slice(9, 14).map(item => {
                        if (item.divider) return '';
                        return `
                            <a href="#" class="admin-sidebar__link ${currentSection === item.section ? 'admin-sidebar__link--active' : ''}" 
                               data-section="${item.section}">
                                <span class="admin-sidebar__icon">${icon(item.icon)}</span>
                                <span>${item.label}</span>
                            </a>
                        `;
                    }).join('')}
                </div>
                <div class="admin-sidebar__section">
                    <div class="admin-sidebar__label">System</div>
                    ${NAV_ITEMS.slice(14).map(item => {
                        if (item.divider) return '';
                        return `
                            <a href="#" class="admin-sidebar__link ${currentSection === item.section ? 'admin-sidebar__link--active' : ''}" 
                               data-section="${item.section}">
                                <span class="admin-sidebar__icon">${icon(item.icon)}</span>
                                <span>${item.label}</span>
                            </a>
                        `;
                    }).join('')}
                </div>
            </aside>
        `;
    }

    function bindSidebarEvents() {
        document.querySelectorAll('.admin-sidebar__link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const section = link.dataset.section;
                navigateTo(section);
            });
        });

        const toggle = document.getElementById('adminSidebarToggle');
        if (toggle) {
            toggle.addEventListener('click', () => {
                sidebarOpen = !sidebarOpen;
                document.getElementById('adminSidebar').classList.toggle('admin-sidebar--open', sidebarOpen);
            });
        }
    }

    function navigateTo(section) {
        closeModalDirect();
        currentSection = section;
        if (section === 'registrations') {
            regState.currentView = 'list';
            regState.selectedRequest = null;
        }
        render();
    }

    // ========================================
    // Dashboard
    // ========================================
    async function renderDashboard() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading dashboard...</div>';

        try {
            const stats = await apiCall('/dashboard/stats');
            
            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Dashboard</h1>
                        <p class="admin-header__subtitle">Welcome back, Chanakya Sir</p>
                    </div>
                </div>

                <div class="admin-stats">
                    <div class="admin-stat admin-stat--accent">
                        <div class="admin-stat__icon"> ${icon("students")}</div>
                        <div class="admin-stat__value">${stats.total_students}</div>
                        <div class="admin-stat__label">Total Students</div>
                    </div>
                    <div class="admin-stat admin-stat--warning">
                        <div class="admin-stat__icon"> ${icon("registrations")}</div>
                        <div class="admin-stat__value">${stats.pending_registrations}</div>
                        <div class="admin-stat__label">Pending Registrations</div>
                    </div>
                    <div class="admin-stat admin-stat--success">
                        <div class="admin-stat__icon"> ${icon("enrollments")}</div>
                        <div class="admin-stat__value">${stats.active_enrollments}</div>
                        <div class="admin-stat__label">Active Enrollments</div>
                    </div>
                    <div class="admin-stat">
                        <div class="admin-stat__icon"> ${icon("fees")}</div>
                        <div class="admin-stat__value">${stats.pending_fee_records}</div>
                        <div class="admin-stat__label">Pending Fees</div>
                    </div>
                </div>

                <div class="admin-card">
                    <div class="admin-card__header">
                        <h3 class="admin-card__title">Recent Registrations</h3>
                        <a href="#" class="btn btn--secondary" data-section="registrations">View All</a>
                    </div>
                    <div class="admin-card__body" style="padding: 0;">
                        ${stats.recent_registrations.length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr>
                                        <th>Request ID</th>
                                        <th>Name</th>
                                        <th>Email</th>
                                        <th>Status</th>
                                        <th>Submitted</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${stats.recent_registrations.map(r => `
                                        <tr>
                                            <td><strong>${r.request_id}</strong></td>
                                            <td>${r.full_name}</td>
                                            <td>${r.email}</td>
                                            <td><span class="badge badge--${getStatusBadgeClass(r.status)}">${formatStatus(r.status)}</span></td>
                                            <td>${formatDate(r.submitted_at)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("registrations")}</div>
                                <div class="admin-empty__title">No registrations yet</div>
                                <div class="admin-empty__text">Registration requests will appear here</div>
                            </div>
                        `}
                    </div>
                </div>
            `;

            container.querySelector('[data-section="registrations"]')?.addEventListener('click', (e) => {
                e.preventDefault();
                navigateTo('registrations');
            });

            const badge = document.getElementById('pendingBadge');
            if (badge) badge.textContent = stats.pending_registrations;

        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load dashboard</div>
                    <div class="admin-empty__text">Please check your connection and try again</div>
                </div>
            `;
        }
    }

    // ========================================
    // Registration Requests - List
    // ========================================
    async function loadRegistrations() {
        regState.loading = true;
        regState.error = null;
        renderRegistrationsList();

        try {
            const requests = await apiCall('/registration-requests');
            regState.requests = requests || [];
            applyRegFilters();
        } catch (error) {
            regState.error = error.message;
            regState.requests = [];
            regState.filtered = [];
        } finally {
            regState.loading = false;
            renderRegistrationsList();
        }
    }

    function applyRegFilters() {
        let filtered = [...regState.requests];

        // Status filter
        if (regState.statusFilter !== 'all') {
            filtered = filtered.filter(r => r.status === regState.statusFilter);
        }

        // Programme filter
        if (regState.programmeFilter !== 'all') {
            filtered = filtered.filter(r =>
                (r.selected_programmes || []).some(p => p.id === regState.programmeFilter)
            );
        }

        // Search filter
        if (regState.search.trim()) {
            const q = regState.search.toLowerCase();
            filtered = filtered.filter(r =>
                r.full_name.toLowerCase().includes(q) ||
                r.email.toLowerCase().includes(q) ||
                r.request_id.toLowerCase().includes(q)
            );
        }

        regState.filtered = filtered;
    }

    function getUniqueProgrammes() {
        const map = new Map();
        regState.requests.forEach(r => {
            (r.selected_programmes || []).forEach(p => {
                if (!map.has(p.id)) map.set(p.id, p.name);
            });
        });
        return Array.from(map.entries()).map(([id, name]) => ({ id, name }));
    }

    function getStatusCounts() {
        const counts = {
            pending_email_verification: 0,
            email_verified: 0,
            pending_review: 0,
            needs_information: 0,
            approved: 0,
            rejected: 0,
        };
        regState.requests.forEach(r => {
            if (counts.hasOwnProperty(r.status)) counts[r.status]++;
        });
        return counts;
    }

    function renderRegistrationsList() {
        const container = document.getElementById('adminContent');
        const counts = getStatusCounts();
        const programmes = getUniqueProgrammes();

        if (regState.loading) {
            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Registration Requests</h1>
                        <p class="admin-header__subtitle">Review and manage new ChankArts Music Academy applications.</p>
                    </div>
                </div>
                <div class="admin-loading"><div class="admin-loading__spinner"></div>Loading registration requests...</div>
            `;
            return;
        }

        if (regState.error) {
            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Registration Requests</h1>
                        <p class="admin-header__subtitle">Review and manage new ChankArts Music Academy applications.</p>
                    </div>
                </div>
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load registration requests</div>
                    <div class="admin-empty__text">${escapeHtml(regState.error)}</div>
                    <button class="btn btn--primary" onclick="Admin.loadRegistrations()" style="margin-top: 16px;">Try Again</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="admin-header">
                <div>
                    <h1 class="admin-header__title">Registration Requests</h1>
                    <p class="admin-header__subtitle">Review and manage new ChankArts Music Academy applications.</p>
                </div>
            </div>

            <!-- Summary Cards -->
            <div class="admin-stats">
                <div class="admin-stat admin-stat--warning" onclick="Admin.filterByStatus('pending_review')" style="cursor:pointer;">
                    <div class="admin-stat__icon"> ${icon("pending")}</div>
                    <div class="admin-stat__value">${counts.pending_review}</div>
                    <div class="admin-stat__label">Pending Review</div>
                </div>
                <div class="admin-stat admin-stat--accent" onclick="Admin.filterByStatus('email_verified')" style="cursor:pointer;">
                    <div class="admin-stat__icon"> ${icon("mail")}</div>
                    <div class="admin-stat__value">${counts.email_verified}</div>
                    <div class="admin-stat__label">Email Verified</div>
                </div>
                <div class="admin-stat" onclick="Admin.filterByStatus('needs_information')" style="cursor:pointer;">
                    <div class="admin-stat__icon"> ${icon("info")}</div>
                    <div class="admin-stat__value">${counts.needs_information}</div>
                    <div class="admin-stat__label">Needs Information</div>
                </div>
                <div class="admin-stat admin-stat--success" onclick="Admin.filterByStatus('approved')" style="cursor:pointer;">
                    <div class="admin-stat__icon"> ${icon("attendance")}</div>
                    <div class="admin-stat__value">${counts.approved}</div>
                    <div class="admin-stat__label">Approved</div>
                </div>
                <div class="admin-stat" style="border-color: rgba(248,113,113,0.2);" onclick="Admin.filterByStatus('rejected')" style="cursor:pointer;">
                    <div class="admin-stat__icon"> ${icon("rejected")}</div>
                    <div class="admin-stat__value" style="color: var(--color-error);">${counts.rejected}</div>
                    <div class="admin-stat__label">Rejected</div>
                </div>
            </div>

            <!-- Filters -->
            <div class="admin-card" style="margin-bottom: var(--space-xl);">
                <div class="admin-card__body" style="padding: var(--space-lg) var(--space-xl);">
                    <div class="reg-filters">
                        <div class="reg-filters__search">
                            <input type="text" class="auth__input" id="regSearch" placeholder="Search by name, email or request ID" value="${escapeHtml(regState.search)}">
                        </div>
                        <div class="reg-filters__selects">
                            <select class="auth__input auth__select" id="regStatusFilter">
                                <option value="all" ${regState.statusFilter === 'all' ? 'selected' : ''}>All Statuses</option>
                                <option value="pending_email_verification" ${regState.statusFilter === 'pending_email_verification' ? 'selected' : ''}>Pending Email Verification</option>
                                <option value="email_verified" ${regState.statusFilter === 'email_verified' ? 'selected' : ''}>Email Verified</option>
                                <option value="pending_review" ${regState.statusFilter === 'pending_review' ? 'selected' : ''}>Pending Approval</option>
                                <option value="needs_information" ${regState.statusFilter === 'needs_information' ? 'selected' : ''}>Needs Information</option>
                                <option value="approved" ${regState.statusFilter === 'approved' ? 'selected' : ''}>Approved</option>
                                <option value="rejected" ${regState.statusFilter === 'rejected' ? 'selected' : ''}>Rejected</option>
                            </select>
                            <select class="auth__input auth__select" id="regProgrammeFilter">
                                <option value="all">All Programmes</option>
                                ${programmes.map(p => `
                                    <option value="${p.id}" ${regState.programmeFilter === p.id ? 'selected' : ''}>${p.name}</option>
                                `).join('')}
                            </select>
                            ${(regState.search || regState.statusFilter !== 'all' || regState.programmeFilter !== 'all') ? `
                                <button class="btn btn--secondary" onclick="Admin.clearRegFilters()">Clear Filters</button>
                            ` : ''}
                        </div>
                    </div>
                </div>
            </div>

            <!-- Results -->
            <div class="admin-card">
                <div class="admin-card__header">
                    <h3 class="admin-card__title">${regState.filtered.length} Request${regState.filtered.length !== 1 ? 's' : ''}</h3>
                </div>
                <div class="admin-card__body" style="padding: 0;">
                    ${regState.filtered.length > 0 ? `
                        <!-- Desktop Table -->
                        <div class="reg-table-desktop">
                            <table class="admin-table">
                                <thead>
                                    <tr>
                                        <th>Request ID</th>
                                        <th>Student</th>
                                        <th>Email</th>
                                        <th>Mobile</th>
                                        <th>Programmes</th>
                                        <th>Submitted</th>
                                        <th>Review Deadline</th>
                                        <th>Status</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${regState.filtered.map(r => renderRegRow(r)).join('')}
                                </tbody>
                            </table>
                        </div>
                        <!-- Mobile Cards -->
                        <div class="reg-table-mobile">
                            ${regState.filtered.map(r => renderRegCard(r)).join('')}
                        </div>
                    ` : `
                        <div class="admin-empty">
                            <div class="admin-empty__icon"> ${icon("registrations")}</div>
                            <div class="admin-empty__title">No Registration Requests</div>
                            <div class="admin-empty__text">New Academy applications will appear here when students register.</div>
                        </div>
                    `}
                </div>
            </div>
        `;

        // Bind filter events
        const searchInput = document.getElementById('regSearch');
        if (searchInput) {
            let debounce;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(debounce);
                debounce = setTimeout(() => {
                    regState.search = e.target.value;
                    applyRegFilters();
                    renderRegistrationsList();
                }, 300);
            });
        }

        const statusSelect = document.getElementById('regStatusFilter');
        if (statusSelect) {
            statusSelect.addEventListener('change', (e) => {
                regState.statusFilter = e.target.value;
                applyRegFilters();
                renderRegistrationsList();
            });
        }

        const progSelect = document.getElementById('regProgrammeFilter');
        if (progSelect) {
            progSelect.addEventListener('change', (e) => {
                regState.programmeFilter = e.target.value;
                applyRegFilters();
                renderRegistrationsList();
            });
        }
    }

    function renderRegRow(r) {
        const deadline = r.review_deadline ? new Date(r.review_deadline) : null;
        const now = new Date();
        const isOverdue = deadline && now > deadline && ['pending_review', 'email_verified', 'needs_information', 'pending_email_verification'].includes(r.status);
        const programmes = (r.selected_programmes || []).map(p => p.name).join(', ') || '-';

        return `
            <tr class="${isOverdue ? 'reg-row--overdue' : ''}">
                <td><strong>${r.request_id}</strong></td>
                <td>
                    <div class="reg-student-cell">
                        <span>${r.full_name}</span>
                        ${r.is_minor ? '<span class="badge badge--needs-info" style="font-size:0.65rem;">Minor</span>' : ''}
                    </div>
                </td>
                <td>${r.email}</td>
                <td>${r.mobile}</td>
                <td><span class="reg-programmes-cell">${programmes}</span></td>
                <td>${formatDate(r.submitted_at)}</td>
                <td>
                    ${deadline ? `
                        <span class="${isOverdue ? 'reg-deadline--overdue' : ''}">${formatDate(r.review_deadline)}</span>
                        ${isOverdue ? '<span class="badge badge--rejected" style="font-size:0.6rem; margin-left:4px;">OVERDUE</span>' : ''}
                    ` : '-'}
                </td>
                <td><span class="badge badge--${getStatusBadgeClass(r.status)}">${formatStatus(r.status)}</span></td>
                <td>
                    <button class="btn btn--secondary btn--sm" onclick="Admin.viewRegistration('${r.id}')">View</button>
                </td>
            </tr>
        `;
    }

    function renderRegCard(r) {
        const deadline = r.review_deadline ? new Date(r.review_deadline) : null;
        const now = new Date();
        const isOverdue = deadline && now > deadline && ['pending_review', 'email_verified', 'needs_information', 'pending_email_verification'].includes(r.status);
        const programmes = (r.selected_programmes || []).map(p => p.name);

        return `
            <div class="reg-card ${isOverdue ? 'reg-card--overdue' : ''}" onclick="Admin.viewRegistration('${r.id}')">
                <div class="reg-card__header">
                    <strong>${r.request_id}</strong>
                    <span class="badge badge--${getStatusBadgeClass(r.status)}">${formatStatus(r.status)}</span>
                </div>
                <div class="reg-card__name">${r.full_name} ${r.is_minor ? '<span class="badge badge--needs-info" style="font-size:0.6rem;">Minor</span>' : ''}</div>
                <div class="reg-card__meta">${r.email} · ${r.mobile}</div>
                <div class="reg-card__programmes">
                    ${programmes.map(p => `<span class="badge badge--approved" style="font-size:0.7rem;">${p}</span>`).join('')}
                </div>
                <div class="reg-card__footer">
                    <span>${formatDate(r.submitted_at)}</span>
                    ${isOverdue ? '<span class="badge badge--rejected" style="font-size:0.6rem;">OVERDUE</span>' : ''}
                </div>
            </div>
        `;
    }

    // ========================================
    // Registration Requests - Detail
    // ========================================
    async function viewRegistration(id) {
        regState.currentView = 'detail';
        regState.detailLoading = true;
        regState.detailError = null;
        regState.selectedRequest = null;
        renderRegDetail();

        try {
            const req = await apiCall(`/registration-requests/${id}`);
            regState.selectedRequest = req;
        } catch (error) {
            regState.detailError = error.message;
        } finally {
            regState.detailLoading = false;
            renderRegDetail();
        }
    }

    function renderRegDetail() {
        const container = document.getElementById('adminContent');

        if (regState.detailLoading) {
            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Registration Request</h1>
                        <p class="admin-header__subtitle">Loading details...</p>
                    </div>
                    <button class="btn btn--secondary" onclick="Admin.backToList()">← Back to List</button>
                </div>
                <div class="admin-loading"><div class="admin-loading__spinner"></div>Loading request details...</div>
            `;
            return;
        }

        if (regState.detailError) {
            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Registration Request</h1>
                        <p class="admin-header__subtitle">Error loading request</p>
                    </div>
                    <button class="btn btn--secondary" onclick="Admin.backToList()">← Back to List</button>
                </div>
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load registration</div>
                    <div class="admin-empty__text">${escapeHtml(regState.detailError)}</div>
                </div>
            `;
            return;
        }

        const req = regState.selectedRequest;
        if (!req) return;

        const deadline = req.review_deadline ? new Date(req.review_deadline) : null;
        const now = new Date();
        const isOverdue = deadline && now > deadline && ['pending_review', 'email_verified', 'needs_information', 'pending_email_verification'].includes(req.status);
        const age = calculateAge(req.date_of_birth);
        const programmes = req.selected_programmes || [];

        // Determine which actions are available
        const canApprove = ['pending_review', 'email_verified', 'needs_information'].includes(req.status);
        const canReject = ['pending_review', 'email_verified', 'needs_information'].includes(req.status);
        const canRequestInfo = ['pending_review', 'email_verified'].includes(req.status);

        container.innerHTML = `
            <div class="admin-header">
                <div>
                    <h1 class="admin-header__title">Registration Request</h1>
                    <p class="admin-header__subtitle">${req.request_id}</p>
                </div>
                <button class="btn btn--secondary" onclick="Admin.backToList()">← Back to List</button>
            </div>

            <div class="admin-detail">
                <!-- Header -->
                <div class="admin-detail__header">
                    <div>
                        <h2 class="admin-detail__title">${req.full_name}</h2>
                        <div class="admin-detail__meta">
                            <span class="admin-detail__meta-item">${icon("mail")} ${req.email}</span>
                            <span class="admin-detail__meta-item">${icon("users")} ${req.mobile}</span>
                            <span class="admin-detail__meta-item">${icon("clock")} Submitted ${formatDateTime(req.submitted_at)}</span>
                        </div>
                    </div>
                    <div class="admin-detail__status-group">
                        <span class="badge badge--${getStatusBadgeClass(req.status)}" style="font-size: 0.85rem; padding: 6px 14px;">${formatStatus(req.status)}</span>
                        ${isOverdue ? '<span class="badge badge--rejected" style="font-size: 0.85rem; padding: 6px 14px; margin-left: 8px;">OVERDUE</span>' : ''}
                    </div>
                </div>

                <!-- 72-Hour Review Indicator -->
                ${deadline ? `
                    <div class="reg-deadline-banner ${isOverdue ? 'reg-deadline-banner--overdue' : ''}">
                        <div class="reg-deadline-banner__icon">${isOverdue ? '⚠️' : '⏱️'}</div>
                        <div class="reg-deadline-banner__text">
                            <strong>${isOverdue ? 'Review Overdue' : '72-Hour Review Window'}</strong>
                            <span>${isOverdue
                                ? 'Review deadline has passed.'
                                : `Review deadline: ${formatDateTime(req.review_deadline)}`
                            }</span>
                        </div>
                    </div>
                ` : ''}

                <!-- Application Timeline -->
                <div class="admin-detail__section">
                    <h3 class="admin-detail__section-title">Application Timeline</h3>
                    <div class="reg-timeline">
                        ${renderTimeline(req)}
                    </div>
                </div>

                <!-- Applicant Information -->
                <div class="admin-detail__section">
                    <h3 class="admin-detail__section-title">Applicant Information</h3>
                    <div class="admin-detail__grid">
                        <div class="admin-detail__field">
                            <span class="admin-detail__field-label">Full Name</span>
                            <span class="admin-detail__field-value">${req.full_name}</span>
                        </div>
                        <div class="admin-detail__field">
                            <span class="admin-detail__field-label">Email</span>
                            <span class="admin-detail__field-value">${req.email}</span>
                        </div>
                        <div class="admin-detail__field">
                            <span class="admin-detail__field-label">Mobile</span>
                            <span class="admin-detail__field-value">${req.mobile}</span>
                        </div>
                        <div class="admin-detail__field">
                            <span class="admin-detail__field-label">Date of Birth</span>
                            <span class="admin-detail__field-value">${formatDate(req.date_of_birth)}</span>
                        </div>
                        <div class="admin-detail__field">
                            <span class="admin-detail__field-label">Age</span>
                            <span class="admin-detail__field-value">${age} years ${req.is_minor ? '(Under 18)' : '(18+)'}</span>
                        </div>
                        ${req.address ? `
                            <div class="admin-detail__field" style="grid-column: 1 / -1;">
                                <span class="admin-detail__field-label">Address</span>
                                <span class="admin-detail__field-value">${req.address}</span>
                            </div>
                        ` : ''}
                    </div>
                </div>

                <!-- Guardian Information (minors only) -->
                ${req.is_minor && req.guardian_name ? `
                    <div class="admin-detail__section">
                        <h3 class="admin-detail__section-title">Guardian Information</h3>
                        <div class="admin-detail__grid">
                            <div class="admin-detail__field">
                                <span class="admin-detail__field-label">Guardian Name</span>
                                <span class="admin-detail__field-value">${req.guardian_name}</span>
                            </div>
                            <div class="admin-detail__field">
                                <span class="admin-detail__field-label">Relationship</span>
                                <span class="admin-detail__field-value">${req.guardian_relationship || '-'}</span>
                            </div>
                            ${req.guardian_email ? `
                                <div class="admin-detail__field">
                                    <span class="admin-detail__field-label">Guardian Email</span>
                                    <span class="admin-detail__field-value">${req.guardian_email}</span>
                                </div>
                            ` : ''}
                            <div class="admin-detail__field">
                                <span class="admin-detail__field-label">Guardian Mobile</span>
                                <span class="admin-detail__field-value">${req.guardian_mobile || '-'}</span>
                            </div>
                        </div>
                    </div>
                ` : ''}

                <!-- Selected Programmes -->
                <div class="admin-detail__section">
                    <h3 class="admin-detail__section-title">Selected Programmes</h3>
                    <div class="reg-programmes-grid">
                        ${programmes.map(p => `
                            <div class="reg-programme-card">
                                <span class="reg-programme-card__icon">${icon("book")}</span>
                                <span class="reg-programme-card__name">${p.name}</span>
                            </div>
                        `).join('')}
                    </div>
                    <p class="reg-note">ONE student → ONE CMA Registration ID → ${programmes.length} course enrollment${programmes.length !== 1 ? 's' : ''}</p>
                </div>

                <!-- Review Notes (if already reviewed) -->
                ${req.review_notes ? `
                    <div class="admin-detail__section">
                        <h3 class="admin-detail__section-title">Review Notes</h3>
                        <div class="reg-review-notes">
                            <p>${escapeHtml(req.review_notes)}</p>
                            ${req.reviewed_at ? `<span class="reg-review-notes__date">Reviewed on ${formatDateTime(req.reviewed_at)}</span>` : ''}
                        </div>
                    </div>
                ` : ''}

                <!-- Approved State -->
                ${req.status === 'approved' ? `
                    <div class="admin-detail__section">
                        <div class="reg-approved-banner">
                            <div class="reg-approved-banner__icon">${icon("approved")}</div>
                            <div class="reg-approved-banner__text">
                                <strong>Approved</strong>
                                <span>This application has been approved. The student account will be activated and a permanent CMA Registration ID will be assigned.</span>
                            </div>
                        </div>
                    </div>
                ` : ''}

                <!-- Rejected State -->
                ${req.status === 'rejected' ? `
                    <div class="admin-detail__section">
                        <div class="reg-rejected-banner">
                            <div class="reg-rejected-banner__icon">${icon("rejected")}</div>
                            <div class="reg-rejected-banner__text">
                                <strong>Rejected</strong>
                                <span>This application has been rejected.${req.review_notes ? ' Reason: ' + escapeHtml(req.review_notes) : ''}</span>
                            </div>
                        </div>
                    </div>
                ` : ''}

                <!-- Pending Email Verification State -->
                ${req.status === 'pending_email_verification' ? `
                    <div class="admin-detail__section">
                        <div class="reg-pending-banner">
                            <div class="reg-pending-banner__icon">${icon("mail")}</div>
                            <div class="reg-pending-banner__text">
                                <strong>Waiting for Email Verification</strong>
                                <span>The applicant has not yet verified their email address. Admin approval is not available until email is verified.</span>
                            </div>
                        </div>
                    </div>
                ` : ''}

                <!-- Admin Actions -->
                ${canApprove || canReject || canRequestInfo ? `
                    <div class="admin-detail__section">
                        <h3 class="admin-detail__section-title">Admin Actions</h3>
                        <div class="admin-actions">
                            ${canApprove ? `
                                <button class="btn btn--primary" onclick="Admin.showApproveModal('${req.id}')">
                                    ✓ Approve Application
                                </button>
                            ` : ''}
                            ${canRequestInfo ? `
                                <button class="btn btn--secondary reg-btn--warning" onclick="Admin.showRequestInfoModal('${req.id}')">
                                    ℹ Request More Information
                                </button>
                            ` : ''}
                            ${canReject ? `
                                <button class="btn btn--secondary reg-btn--danger" onclick="Admin.showRejectModal('${req.id}')">
                                    ✕ Reject Application
                                </button>
                            ` : ''}
                        </div>
                    </div>
                ` : ''}
            </div>
        `;
    }

    function renderTimeline(req) {
        const events = [];

        // Application Submitted
        events.push({
            done: true,
            label: 'Application Submitted',
            date: req.submitted_at,
        });

        // Email Verification
        if (req.status === 'pending_email_verification') {
            events.push({
                done: false,
                current: true,
                label: 'Email Verification',
                date: null,
            });
        } else {
            events.push({
                done: true,
                label: 'Email Verification',
                date: req.submitted_at, // approximate
            });
        }

        // Admin Review
        if (['pending_review', 'email_verified', 'needs_information'].includes(req.status)) {
            events.push({
                done: false,
                current: true,
                label: 'Pending Admin Review',
                date: null,
            });
        } else if (req.status === 'approved') {
            events.push({
                done: true,
                label: 'Admin Review',
                date: req.reviewed_at,
            });
        } else if (req.status === 'rejected') {
            events.push({
                done: true,
                label: 'Application Rejected',
                date: req.reviewed_at,
            });
        } else if (req.status === 'needs_information') {
            events.push({
                done: false,
                current: true,
                label: 'Awaiting Information',
                date: null,
            });
        }

        // Approval (only if approved)
        if (req.status === 'approved') {
            events.push({
                done: true,
                label: 'Approval',
                date: req.reviewed_at,
            });
            events.push({
                done: false,
                label: 'Student Activation',
                date: null,
            });
        } else if (req.status === 'rejected') {
            events.push({
                done: false,
                label: 'Approval',
                date: null,
                skipped: true,
            });
            events.push({
                done: false,
                label: 'Student Activation',
                date: null,
                skipped: true,
            });
        } else {
            events.push({
                done: false,
                label: 'Approval',
                date: null,
            });
            events.push({
                done: false,
                label: 'Student Activation',
                date: null,
            });
        }

        return events.map(e => `
            <div class="reg-timeline__item ${e.done ? 'reg-timeline__item--done' : ''} ${e.current ? 'reg-timeline__item--current' : ''} ${e.skipped ? 'reg-timeline__item--skipped' : ''}">
                <div class="reg-timeline__dot">${e.done ? '✓' : e.current ? '●' : e.skipped ? '✕' : '○'}</div>
                <div class="reg-timeline__content">
                    <span class="reg-timeline__label">${e.label}</span>
                    ${e.date ? `<span class="reg-timeline__date">${formatDateTime(e.date)}</span>` : ''}
                </div>
            </div>
        `).join('');
    }

    // ========================================
    // Modal System
    // ========================================
    function showModal(html) {
        let overlay = document.getElementById('adminModalOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'adminModalOverlay';
            document.body.appendChild(overlay);
        }
        overlay.innerHTML = `
            <div class="admin-modal-overlay" onclick="Admin.closeModal(event)">
                <div class="admin-modal" onclick="event.stopPropagation()">
                    ${html}
                </div>
            </div>
        `;
        document.body.style.overflow = 'hidden';
    }

    function closeModal(e) {
        if (e && e.target && !e.target.classList.contains('admin-modal-overlay')) return;
        const overlay = document.getElementById('adminModalOverlay');
        if (overlay) overlay.innerHTML = '';
        document.body.style.overflow = '';
    }

    function closeModalDirect() {
        const overlay = document.getElementById('adminModalOverlay');
        if (overlay) overlay.innerHTML = '';
        document.body.style.overflow = '';
    }

    // ========================================
    // Student PIN reset (administrator)
    // ========================================
    async function resetPin(studentId) {
        if (!window.confirm('Generate a new temporary PIN for this student? The current PIN will stop working immediately.')) {
            return;
        }
        try {
            const res = await apiCall(`/students/${studentId}/reset-pin`, { method: 'POST' });
            showModal(`
                <div class="admin-modal__header admin-modal__header--warning">
                    <h3 class="admin-modal__title">New temporary PIN</h3>
                </div>
                <div class="admin-modal__body">
                    <p>Login ID: <strong>${res.login_id}</strong></p>
                    <p style="font-size:2rem;font-weight:700;letter-spacing:0.35em;text-align:center;margin:16px 0;
                              padding:14px;background:rgba(201,169,110,0.12);border-radius:10px;"
                       id="newPinDisplay">${res.new_pin}</p>
                    <p style="color:var(--color-error);font-size:0.85rem;">
                        Shown once only — record it in your secure password manager.
                        Stored as a hash; the student must change it at next login.
                    </p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--primary" onclick="Admin.closeModalDirect()">Done</button>
                </div>
            `);
        } catch (e) {
            alert('PIN reset failed: ' + (e.message || 'unknown error'));
        }
    }

    // ========================================
    // Approve Modal
    // ========================================
    function showApproveModal(id) {
        const req = regState.selectedRequest;
        if (!req) return;

        const programmes = (req.selected_programmes || []).map(p => p.name).join(', ');

        showModal(`
            <div class="admin-modal__header admin-modal__header--success">
                <h2 class="admin-modal__title">Approve Registration?</h2>
            </div>
            <div class="admin-modal__body">
                <p>You are about to approve this Academy registration.</p>
                <div class="admin-modal__info">
                    <strong>After approval:</strong>
                    <ul>
                        <li>A permanent CMA Registration ID will be created.</li>
                        <li>The student account will be activated according to the LMS workflow.</li>
                        <li>The selected programmes will become course enrollments.</li>
                    </ul>
                </div>
                <div class="admin-modal__applicant">
                    <div><strong>${req.full_name}</strong></div>
                    <div style="color: var(--color-text-secondary); font-size: 0.9rem;">${req.email}</div>
                    <div style="color: var(--color-text-secondary); font-size: 0.9rem; margin-top: 4px;">Programmes: ${programmes}</div>
                </div>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" id="modalApproveBtn" onclick="Admin.confirmApprove('${id}')">Approve Application</button>
            </div>
        `);
    }

    async function confirmApprove(id) {
        const btn = document.getElementById('modalApproveBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Approving...';
        }

        try {
            const res = await apiCall(`/registration-requests/${id}/status`, {
                method: 'PATCH',
                body: JSON.stringify({ status: 'approved', notes: '' }),
            });
            closeModalDirect();
            // Approval never creates an account — provisioning is explicit
            showModal(`
                <div class="admin-modal__header admin-modal__header--success">
                    <h3 class="admin-modal__title">Application approved</h3>
                </div>
                <div class="admin-modal__body">
                    <p>No student account has been created yet, per academy policy.</p>
                    <p style="color:var(--color-text-secondary);font-size:0.9rem;margin-top:8px">
                        Use <strong>Provision Student</strong> to create the account, enrolment and a
                        temporary PIN (shown once) when you are ready.</p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Later</button>
                    <button class="btn btn--primary" onclick="Admin.provisionStudent('${id}')">Provision Student</button>
                </div>
            `);
            await viewRegistration(id);
        } catch (error) {
            showToast('Failed to approve: ' + error.message, 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Approve Application';
            }
        }
    }

    // ========================================
    // Reject Modal
    // ========================================
    function showRejectModal(id) {
        const req = regState.selectedRequest;
        if (!req) return;

        showModal(`
            <div class="admin-modal__header admin-modal__header--danger">
                <h2 class="admin-modal__title">Reject Registration?</h2>
            </div>
            <div class="admin-modal__body">
                <p>You are about to reject this Academy registration. This action preserves the application in the system.</p>
                <div class="admin-modal__field">
                    <label class="auth__label">Rejection Reason <span style="color: var(--color-error);">*</span></label>
                    <textarea class="auth__input auth__textarea" id="rejectReason" placeholder="Enter the reason for rejecting this application..." rows="4"></textarea>
                    <span class="auth__error" id="rejectReasonError">Rejection reason is required</span>
                </div>
                <div class="admin-modal__applicant">
                    <div><strong>${req.full_name}</strong> · ${req.request_id}</div>
                </div>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary reg-btn--danger" id="modalRejectBtn" onclick="Admin.confirmReject('${id}')">Reject Application</button>
            </div>
        `);
    }

    async function confirmReject(id) {
        const reason = document.getElementById('rejectReason')?.value.trim();
        const errorEl = document.getElementById('rejectReasonError');

        if (!reason) {
            if (errorEl) errorEl.classList.add('auth__error--visible');
            return;
        }
        if (errorEl) errorEl.classList.remove('auth__error--visible');

        const btn = document.getElementById('modalRejectBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Rejecting...';
        }

        try {
            await apiCall(`/registration-requests/${id}/status`, {
                method: 'PATCH',
                body: JSON.stringify({ status: 'rejected', notes: reason }),
            });
            closeModalDirect();
            showToast('Registration rejected successfully.', 'success');
            await viewRegistration(id);
        } catch (error) {
            showToast('Failed to reject: ' + error.message, 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Reject Application';
            }
        }
    }

    // ========================================
    // Request More Information Modal
    // ========================================
    function showRequestInfoModal(id) {
        const req = regState.selectedRequest;
        if (!req) return;

        showModal(`
            <div class="admin-modal__header admin-modal__header--warning">
                <h2 class="admin-modal__title">Request More Information</h2>
            </div>
            <div class="admin-modal__body">
                <p>Send a request to the applicant for additional information. The status will change to "Needs Information".</p>
                <div class="admin-modal__field">
                    <label class="auth__label">Information Required</label>
                    <textarea class="auth__input auth__textarea" id="infoRequest" placeholder="Describe what information is needed from the applicant..." rows="4"></textarea>
                </div>
                <div class="admin-modal__applicant">
                    <div><strong>${req.full_name}</strong> · ${req.email}</div>
                </div>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" id="modalInfoBtn" onclick="Admin.confirmRequestInfo('${id}')">Send Request</button>
            </div>
        `);
    }

    async function confirmRequestInfo(id) {
        const notes = document.getElementById('infoRequest')?.value.trim() || '';

        const btn = document.getElementById('modalInfoBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Sending...';
        }

        try {
            await apiCall(`/registration-requests/${id}/status`, {
                method: 'PATCH',
                body: JSON.stringify({ status: 'needs_information', notes: notes }),
            });
            closeModalDirect();
            showToast('Information request sent successfully.', 'success');
            await viewRegistration(id);
        } catch (error) {
            showToast('Failed to send request: ' + error.message, 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Send Request';
            }
        }
    }

    // ========================================
    // Toast System
    // ========================================
    function showToast(message, type = 'success') {
        let container = document.getElementById('adminToastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'adminToastContainer';
            container.className = 'admin-toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `admin-toast admin-toast--${type}`;
        toast.innerHTML = `
            <span class="admin-toast__icon">${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
            <span class="admin-toast__message">${escapeHtml(message)}</span>
        `;
        container.appendChild(toast);

        setTimeout(() => toast.classList.add('admin-toast--visible'), 10);
        setTimeout(() => {
            toast.classList.remove('admin-toast--visible');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    // ========================================
    // Filter Helpers
    // ========================================
    function filterByStatus(status) {
        regState.statusFilter = status;
        regState.currentView = 'list';
        applyRegFilters();
        renderRegistrationsList();
    }

    function clearRegFilters() {
        regState.search = '';
        regState.statusFilter = 'all';
        regState.programmeFilter = 'all';
        applyRegFilters();
        renderRegistrationsList();
    }

    function backToList() {
        regState.currentView = 'list';
        regState.selectedRequest = null;
        loadRegistrations();
    }

    // ========================================
    // Students
    // ========================================
    async function renderStudents() {
        if (studentWs.active) {
            renderStudentWorkspace();
            return;
        }
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading students...</div>';

        try {
            const students = await apiCall('/students');

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Students</h1>
                        <p class="admin-header__subtitle">Manage student profiles and CMA registrations</p>
                    </div>
                    <div class="admin-actions">
                        <button class="btn btn--primary" onclick="Admin.createStudentModal()">+ Add Student</button>
                    </div>
                </div>

                <div class="admin-card">
                    <div class="admin-card__body" style="padding: 0;">
                        ${students.length > 0 ? `
                            <div class="table-scroll-outer">
                                <div class="table-scroll" tabindex="0" aria-label="Students table — scroll horizontally for all columns and actions">
                                    <table class="admin-table">
                                <thead>
                                    <tr>
                                        <th>CMA ID</th>
                                        <th>Login ID</th>
                                        <th>Name</th>
                                        <th>Phone</th>
                                        <th>Status</th>
                                        <th>Enrollments</th>
                                        <th>Registered</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${students.map(s => `
                                        <tr style="cursor:pointer;" onclick="Admin.openStudentWorkspace('${s.id}')">
                                            <td><strong>${s.cma_registration_id}</strong></td>
                                            <td>${s.login_id || '-'}</td>
                                            <td>${s.full_name}</td>
                                            <td>${s.phone || '-'}</td>
                                            <td><span class="badge badge--${s.status}">${s.status}</span></td>
                                            <td>${s.enrollment_count}</td>
                                            <td>${formatDate(s.created_at)}</td>
                                            <td style="white-space:nowrap;">
                                                <button class="btn btn--secondary btn--sm" onclick="event.stopPropagation();Admin.openStudentWorkspace('${s.id}')">Open →</button>
                                                <button class="btn btn--secondary btn--sm" onclick="event.stopPropagation();Admin.editStudentModal('${s.id}')">Edit</button>
                                                <button class="btn btn--secondary btn--sm" onclick="event.stopPropagation();Admin.resetPin('${s.id}')">Reset PIN</button>
                                                ${s.status === 'active'
                                                    ? `<button class="btn btn--secondary btn--sm" onclick="event.stopPropagation();Admin.setStudentStatus('${s.id}','suspended')">Suspend</button>`
                                                    : `<button class="btn btn--secondary btn--sm" onclick="event.stopPropagation();Admin.setStudentStatus('${s.id}','active')">Reactivate</button>`}
                                                <button class="btn btn--secondary btn--sm" onclick="event.stopPropagation();Admin.archiveStudent('${s.id}')">Archive</button>
                                                <button class="btn btn--secondary btn--sm" onclick="event.stopPropagation();Admin.deleteStudentPermanently('${s.id}')">Delete permanently</button>
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                                    </table>
                                </div>
                                <div class="table-scroll-hint">Scroll sideways for all columns &amp; actions →</div>
                            </div>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("students")}</div>
                                <div class="admin-empty__title">No students yet</div>
                                <div class="admin-empty__text">Students will appear here after registration approval</div>
                            </div>
                        `}
                    </div>
                </div>
            `;

        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load students</div>
                    <div class="admin-empty__text">${error.message}</div>
                </div>
            `;
        }
    }

    // ========================================
    // Enrollments
    // ========================================
    async function renderEnrollments() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading enrollments...</div>';

        try {
            const enrollments = await apiCall('/enrollments');

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Enrollments</h1>
                        <p class="admin-header__subtitle">Manage course enrollments</p>
                    </div>
                </div>

                <div class="admin-card">
                    <div class="admin-card__body" style="padding: 0;">
                        ${enrollments.length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr>
                                        <th>Programme</th>
                                        <th>Student ID</th>
                                        <th>Fee Plan</th>
                                        <th>Status</th>
                                        <th>Start Date</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${enrollments.map(e => `
                                        <tr>
                                            <td><strong>${e.programme_name}</strong></td>
                                            <td>${e.student_id.substring(0, 8)}...</td>
                                            <td>${e.fee_plan || '-'}</td>
                                            <td><span class="badge badge--${e.status}">${e.status}</span></td>
                                            <td>${formatDate(e.start_date)}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("enrollments")}</div>
                                <div class="admin-empty__title">No enrollments yet</div>
                                <div class="admin-empty__text">Enrollments will appear here</div>
                            </div>
                        `}
                    </div>
                </div>
            `;

        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load enrollments</div>
                    <div class="admin-empty__text">${error.message}</div>
                </div>
            `;
        }
    }

    // ========================================
    // ========================================
    // Instructors
    // ========================================
    async function renderInstructors() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading instructors...</div>';

        try {
            const instructors = await apiCall('/instructors');
            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Instructors</h1>
                        <p class="admin-header__subtitle">Faculty directory and specialisations</p>
                    </div>
                    <div class="admin-actions">
                        <button class="btn btn--primary" onclick="Admin.createInstructorModal()">+ Add Instructor</button>
                    </div>
                </div>
                <div class="admin-card">
                    <div class="admin-card__body" style="padding: 0;">
                        ${instructors.length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Phone</th>
                                        <th>Specializations</th>
                                        <th>Experience</th>
                                        <th>Status</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${instructors.map(i => `
                                        <tr>
                                            <td><strong>${escapeHtml(i.full_name)}</strong></td>
                                            <td>${escapeHtml(i.phone || '-')}</td>
                                            <td>${escapeHtml(i.specializations || '-')}</td>
                                            <td>${i.experience_years ? escapeHtml(i.experience_years) + ' yrs' : '-'}</td>
                                            <td><span class="badge badge--${i.is_active ? 'active' : 'inactive'}">${i.is_active ? 'Active' : 'Inactive'}</span></td>
                                            <td style="white-space:nowrap;">
                                                <button class="btn btn--secondary btn--sm" onclick="Admin.editInstructorModal('${i.id}')">Edit</button>
                                                ${i.is_active
                                                    ? `<button class="btn btn--secondary btn--sm" onclick="Admin.deactivateInstructor('${i.id}')">Deactivate</button>`
                                                    : `<button class="btn btn--secondary btn--sm" onclick="Admin.setInstructorActive('${i.id}',true)">Reactivate</button>`}
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("instructors")}</div>
                                <div class="admin-empty__title">No instructors yet</div>
                                <div class="admin-empty__text">Faculty profiles will appear here</div>
                            </div>
                        `}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load instructors</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    // ========================================
    // Classes / Schedules
    // ========================================
    let classStatusFilter = 'all';

    async function renderClasses() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading classes...</div>';

        try {
            const now = new Date();
            const ym = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0');
            const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
            const token = localStorage.getItem('academy_token');
            const response = await fetch(
                `${apiOrigin()}` +
                `/api/v1/sessions?date_from=${ym}-01&date_to=${ym}-${lastDay}&limit=300`,
                { headers: token ? { Authorization: `Bearer ${token}` } : {} }
            );
            if (!response.ok) throw new Error('Failed to load classes');
            let sessions = await response.json();

            const students = await apiCall('/students');
            const studentMap = {};
            students.forEach(s => { studentMap[s.id] = s.full_name; });

            // Authoritative weekly timetable + conflict detection
            const weekly = await apiCall('/schedules');
            const dayOrder = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
            const dayTitle = d => d.charAt(0).toUpperCase() + d.slice(1);
            const conflictHtml = (weekly.conflicts || []).length ? `
                <div class="reg-deadline-banner reg-deadline-banner--overdue" style="margin-bottom:16px;">
                    <span class="reg-deadline-banner__icon">${icon("warn")}</span>
                    <div class="reg-deadline-banner__text">
                        <strong>Schedule conflict — awaiting your approval</strong>
                        <span>${weekly.conflicts.map(c =>
                            `${dayTitle(c.day_of_week)} ${c.overlap_start.slice(0,5)}–${c.overlap_end.slice(0,5)}: ` +
                            `${c.student_a} ↔ ${c.student_b} (both classes kept, neither moved)`
                        ).join('<br>')}</span>
                    </div>
                </div>` : '';
            const byDay = {};
            (weekly.schedules || []).forEach(s => { (byDay[s.day_of_week] = byDay[s.day_of_week] || []).push(s); });
            const timetableRows = dayOrder.filter(d => byDay[d]).map(d => `
                <tr>
                    <td style="vertical-align:top;"><strong>${dayTitle(d)}</strong></td>
                    <td colspan="4" style="padding-top:0;">
                        ${byDay[d].map(s => `
                            <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;padding:5px 0;border-bottom:1px solid rgba(255,255,255,0.04);">
                                <span style="min-width:105px;font-variant-numeric:tabular-nums;">${s.start_time.slice(0,5)} – ${s.end_time.slice(0,5)}</span>
                                <strong style="min-width:150px;">${escapeHtml(s.student_name)}</strong>
                                <span style="min-width:90px;color:var(--color-text-muted);">${s.login_id}</span>
                                <span style="min-width:170px;">${escapeHtml(s.instrument)}</span>
                                <span style="color:${s.instructor_name ? 'var(--color-text-secondary)' : 'var(--color-warning)'};">
                                    ${s.instructor_name ? escapeHtml(s.instructor_name) : 'Instructor not assigned ⚠'}
                                    <button class="btn btn--secondary btn--sm" style="margin-left:8px"
                                        onclick="Admin.assignInstructor('${s.enrollment_id}','${s.day_of_week}','${s.start_time.slice(0,5)}','${s.end_time.slice(0,5)}')">
                                        ${s.instructor_name ? 'Change' : 'Assign'}
                                    </button>
                                </span>
                            </div>
                        `).join('')}
                    </td>
                </tr>`).join('');
            const timetableHtml = `
                <div class="admin-card" style="margin-bottom:16px;">
                    <div class="admin-card__header">
                        <h3 class="admin-card__title">Weekly Timetable (fixed, recurring)</h3>
                        <span style="font-size:0.8rem;color:var(--color-text-muted);">
                            ${(weekly.schedules || []).length} classes · instructors pending for ${(weekly.missing_instructor || []).length}
                        </span>
                    </div>
                    <div class="admin-card__body" style="padding:8px 24px 16px;">
                        ${conflictHtml}
                        <table class="admin-table">
                            <thead><tr><th>Day</th><th>Classes</th></tr></thead>
                            <tbody>${timetableRows}</tbody>
                        </table>
                    </div>
                </div>`;

            if (classStatusFilter !== 'all') {
                sessions = sessions.filter(s => s.status === classStatusFilter);
            }
            sessions.sort((a, b) => (a.scheduled_date + a.scheduled_start) < (b.scheduled_date + b.scheduled_start) ? -1 : 1);

            const filters = ['all', 'scheduled', 'completed', 'rescheduling_required', 'cancelled'].map(f => `
                <button class="admin-filter ${classStatusFilter === f ? 'admin-filter--active' : ''}"
                        onclick="Admin.filterClasses('${f}')">
                    ${f === 'all' ? 'All' : formatStatus(f)}
                </button>
            `).join('');

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Classes / Schedules</h1>
                        <p class="admin-header__subtitle">${now.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })} — ${sessions.length} sessions</p>
                    </div>
                </div>
                <div class="admin-filters">${filters}</div>
                ${timetableHtml}
                <div class="admin-card">
                    <div class="admin-card__body" style="padding: 0;">
                        <div style="padding:14px 24px 0;"><h3 class="admin-card__title">${now.toLocaleDateString('en-IN', { month: 'long', year: 'numeric' })} dated sessions</h3></div>
                        ${sessions.length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Time</th>
                                        <th>Student</th>
                                        <th>Faculty</th>
                                        <th>Duration</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${sessions.map(s => `
                                        <tr>
                                            <td>${formatDate(s.scheduled_date)}</td>
                                            <td>${s.scheduled_start} – ${s.scheduled_end}</td>
                                            <td><strong>${escapeHtml(s.student_name || studentMap[s.student_id] || '—')}</strong></td>
                                            <td>${escapeHtml(s.instructor_name || '—')}</td>
                                            <td>${s.duration_minutes} min${s.is_duration_exception ? ' ⚠' : ''}</td>
                                            <td><span class="badge badge--${getStatusBadgeClass(s.status)}">${formatStatus(s.status)}</span></td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("classes")}</div>
                                <div class="admin-empty__title">No classes match this filter</div>
                                <div class="admin-empty__text">Sessions scheduled this month will appear here</div>
                            </div>
                        `}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load classes</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    function filterClasses(status) {
        classStatusFilter = status;
        renderClasses();
    }

    // ========================================
    // Fees & Payments — financial ledger
    // ========================================
    function todayYm() {
        const d = new Date();
        return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
    }

    const feeState = { month: todayYm(), student: '', type: '', status: '' };

    function feeMonthLabel(ym) {
        const [y, m] = ym.split('-');
        return new Date(Number(y), Number(m) - 1, 1).toLocaleString('en-IN', { month: 'long', year: 'numeric' });
    }

    function shiftFeeMonth(delta) {
        const [y, m] = feeState.month.split('-').map(Number);
        const d = new Date(y, m - 1 + delta, 1);
        feeState.month = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
        renderFees();
    }

    function setFeeFilter(key, value) {
        feeState[key] = value;
        renderFees();
    }

    async function renderFees() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading ledger...</div>';
        try {
            const [invoices, students, payments, report, examFees] = await Promise.all([
                apiV1Call('/billing/invoices?limit=300'),
                apiCall('/students'),
                apiV1Call('/billing/payments?limit=300'),
                apiV1Call('/billing/reports/collections?billing_month=' + feeState.month).catch(() => null),
                apiV1Call('/billing/exam-fees').catch(() => []),
            ]);
            const nameOf = {};
            (students || []).forEach(st => { nameOf[st.id] = st.full_name; });

            let rows = (invoices || []).filter(i => i.billing_month === feeState.month && i.status !== 'void');
            if (feeState.student) rows = rows.filter(i => i.student_id === feeState.student);
            if (feeState.type) rows = rows.filter(i => (i.charge_type || 'tuition') === feeState.type);
            if (feeState.status) {
                rows = rows.filter(i => feeState.status === 'outstanding'
                    ? (i.status === 'pending' || i.status === 'partially_paid')
                    : i.status === feeState.status);
            }

            const totals = report ? report.totals : {
                charged_paise: rows.reduce((s, i) => s + i.amount_paise, 0),
                collected_paise: 0, outstanding_paise: rows.reduce((s, i) => s + Math.max(i.amount_paise - i.amount_paid_paise, 0), 0),
            };

            const studentOpts = (students || []).map(st =>
                `<option value="${st.id}" ${feeState.student === st.id ? 'selected' : ''}>${escapeHtml(st.full_name)}</option>`).join('');

            const invoiceById = {};
            (invoices || []).forEach(i => { invoiceById[i.id] = i; });
            const pending = (payments || []).filter(p => p.status === 'pending_verification');
            const pendingRows = pending.map(p => {
                const inv = p.invoice_id ? invoiceById[p.invoice_id] : null;
                const studentCell = p.student_name
                    ? `<strong>${escapeHtml(p.student_name)}</strong>
                       <div style="font-size:0.72rem;color:var(--color-text-muted)">${escapeHtml(p.cma_registration_id || '')}${p.invoice_number ? ' · ' + escapeHtml(p.invoice_number) : ''}${p.fee_label ? '<br>' + escapeHtml(p.fee_label) : ''}</div>`
                    : (inv || p.claim_unlinked
                        ? `<span style="color:var(--color-warning)">⚠ Unlinked claim — resolve</span>
                           <div style="font-size:0.72rem;color:var(--color-text-muted)">${escapeHtml((p.method || p.provider) + ' claim, no student/fee association')}</div>`
                        : '—');
                const expected = (p.expected_paise != null)
                    ? `₹${(p.expected_paise / 100).toFixed(2)}${p.outstanding_paise ? `<div style="font-size:0.72rem;color:var(--color-text-muted)">₹${(p.outstanding_paise / 100).toFixed(2)} due</div>` : ''}`
                    : '—';
                return `<tr>
                    <td>${studentCell}</td>
                    <td>${expected}</td>
                    <td>₹${(p.amount_paise / 100).toFixed(2)}</td>
                    <td>${escapeHtml(p.method || p.provider)}</td>
                    <td>${p.paid_at ? formatDate(p.paid_at) : (p.created_at ? formatDate(p.created_at) : '—')}</td>
                    <td>${escapeHtml(p.provider_payment_id || '—')}</td>
                    <td><span class="badge badge--pending">Awaiting verification</span></td>
                    <td style="white-space:nowrap">
                        <button class="btn btn--primary btn--sm" onclick="Admin.feeConfirmPayment('${p.id}')">Verify &amp; Mark Paid</button>
                        <button class="btn btn--secondary btn--sm" onclick="Admin.feeClarifyPayment('${p.id}')">Request clarification</button>
                        <button class="btn btn--secondary btn--sm" onclick="Admin.feeRejectPayment('${p.id}')">Reject claim</button>
                    </td>
                </tr>`;
            }).join('');

            const trs = rows.map(i => {
                const outstanding = Math.max(i.amount_paise - i.amount_paid_paise, 0);
                const partial = i.amount_paid_paise > 0 && outstanding > 0;
                const overdue = i.due_date && outstanding > 0 && i.due_date < new Date().toISOString().slice(0, 10);
                return `<tr>
                    <td><strong>${escapeHtml(nameOf[i.student_id] || i.student_id)}</strong>
                        <div style="font-size:0.72rem;color:var(--color-text-muted)">${escapeHtml(i.invoice_number)}</div></td>
                    <td>${escapeHtml(i.description || (i.charge_type || 'tuition'))}
                        ${i.charge_type === 'exam' ? '<span class="badge badge--needs-info" style="margin-left:6px">Exam</span>' : ''}</td>
                    <td>${escapeHtml(i.billing_month)}</td>
                    <td>${i.due_date ? formatDate(i.due_date) : '—'}</td>
                    <td>₹${(i.amount_paise / 100).toFixed(2)}</td>
                    <td>₹${(i.amount_paid_paise / 100).toFixed(2)}</td>
                    <td><strong>₹${(outstanding / 100).toFixed(2)}</strong></td>
                    <td>${partial ? '<span class="badge badge--pending">Partial</span>'
                        : overdue ? '<span class="badge badge--rejected">Overdue</span>'
                        : `<span class="badge badge--${i.status === 'paid' ? 'approved' : 'pending'}">${i.status === 'paid' ? 'Paid' : 'Unpaid'}</span>`}</td>
                    <td>
                        ${outstanding > 0 ? `<button class="btn btn--primary btn--sm" onclick="Admin.feeRecordPayment('${i.id}')">Record Payment</button>` : ''}
                        <button class="btn btn--secondary btn--sm" onclick="Admin.feeInvoiceDetail('${i.id}')">Detail</button>
                    </td>
                </tr>`;
            }).join('');

            const paymentsStrip = (payments || [])
                .filter(p => p.paid_at && p.paid_at.slice(0, 7) === feeState.month)
                .slice(0, 8)
                .map(p => `<div style="display:flex;justify-content:space-between;font-size:0.8rem;padding:6px 0;border-bottom:1px solid var(--color-border)">
                    <span>${escapeHtml(p.method || p.provider)}${p.source === 'manual' ? ' · admin-recorded' : ' · online'}</span>
                    <span>₹${(p.amount_paise / 100).toFixed(2)} ${p.receipt_number ? `<button class="btn btn--secondary btn--sm" onclick="Admin.feeViewReceipt('${p.id}')">${escapeHtml(p.receipt_number)}</button>` : ''}</span>
                </div>`).join('');

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Fees &amp; Payments</h1>
                        <p class="admin-header__subtitle">Financial ledger — charges, payments, credits and receipts (financial status is independent of class attendance)</p>
                    </div>
                    <div style="display:flex;gap:8px;flex-wrap:wrap">
                        <button class="btn btn--primary" onclick="Admin.feeRecordPayment()">+ Record Payment</button>
                        <button class="btn btn--secondary" onclick="Admin.feeCreateCharge()">+ Create Charge</button>
                        <button class="btn btn--secondary" onclick="Admin.feeAdvance()">Advance Credit</button>
                        <button class="btn btn--secondary" onclick="Admin.feeApplyCredit()">Apply Credit</button>
                        <button class="btn btn--secondary" onclick="Admin.feeGenerateCharges()">Generate Monthly Charges</button>
                        <button class="btn btn--secondary" onclick="Admin.feeExport()">Export CSV</button>
                    </div>
                </div>
                <div class="admin-card" style="margin-bottom:12px;border-color:var(--color-accent)"><div class="admin-card__body" style="padding:0">
                    <div style="padding:14px 16px 0"><h3 class="admin-card__title">Payments Awaiting Verification (${pending.length})</h3>
                    <div style="font-size:0.78rem;color:var(--color-text-muted);margin-bottom:8px">Online and family-reported payments appear here. Mark a payment as Paid only after verifying the transaction — this updates the student's fee status and issues the receipt.</div></div>
                    ${pendingRows ? `<table class="admin-table"><thead><tr>
                        <th>Student / fee</th><th>Expected</th><th>Reported</th><th>Method</th><th>Submitted</th><th>Reference</th><th>Status</th><th></th>
                    </tr></thead><tbody>${pendingRows}</tbody></table>`
                    : '<div style="padding:12px 16px;color:var(--color-text-muted);font-size:0.85rem">No payments awaiting verification</div>'}
                </div></div>
                ${(function () {
                    const rejected = (payments || []).filter(p => p.status === 'rejected').slice(0, 8);
                    if (!rejected.length) return '';
                    return `<div class="admin-card" style="margin-bottom:12px"><div class="admin-card__body" style="padding:0">
                        <div style="padding:14px 16px 0"><h3 class="admin-card__title">Rejected claims (${rejected.length}${(payments || []).filter(p => p.status === 'rejected').length > 8 ? ' recent' : ''})</h3>
                        <div style="font-size:0.78rem;color:var(--color-text-muted);margin-bottom:8px">Rejected claims never change collected totals or outstanding balances. Rejected students keep the response (and any attachment) in their portal.</div></div>
                        <table class="admin-table"><thead><tr>
                            <th>Student / fee</th><th>Reported</th><th>Method</th><th>Reference</th><th>Status</th><th>Reason</th></tr></thead><tbody>
                            ${rejected.map(p => `<tr>
                                <td>${p.student_name ? `<strong>${escapeHtml(p.student_name)}</strong><div style="font-size:0.72rem;color:var(--color-text-muted)">${escapeHtml(p.cma_registration_id || '')}${p.invoice_number ? ' · ' + escapeHtml(p.invoice_number) : ''}</div>` : '<span style="color:var(--color-warning)">⚠ Unlinked claim</span>'}</td>
                                <td>₹${(p.amount_paise / 100).toFixed(2)}</td>
                                <td>${escapeHtml(p.method || p.provider)}</td>
                                <td>${escapeHtml(p.provider_payment_id || '—')}</td>
                                <td><span class="badge badge--rejected">Rejected claim</span></td>
                                <td style="font-size:0.8rem">${escapeHtml(((p.notes || '').split('Rejected [')[1] || '').split(']')[0] || '—')}</td>
                            </tr>`).join('')}
                        </tbody></table></div></div>`;
                })()}
                <div class="admin-card" style="margin-bottom:12px"><div class="admin-card__body" style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
                    <button class="btn btn--secondary btn--sm" onclick="Admin.shiftFeeMonth(-1)">◀</button>
                    <strong style="min-width:180px;text-align:center">${feeMonthLabel(feeState.month)}</strong>
                    <button class="btn btn--secondary btn--sm" onclick="Admin.shiftFeeMonth(1)">▶</button>
                    <select class="admin-filter" onchange="Admin.setFeeFilter('student', this.value)">
                        <option value="">All students</option>${studentOpts}</select>
                    <select class="admin-filter" onchange="Admin.setFeeFilter('type', this.value)">
                        <option value="">All charge types</option>
                        <option value="tuition" ${feeState.type === 'tuition' ? 'selected' : ''}>Tuition</option>
                        <option value="exam" ${feeState.type === 'exam' ? 'selected' : ''}>Exam fees</option>
                        <option value="other" ${feeState.type === 'other' ? 'selected' : ''}>Other</option>
                    </select>
                    <select class="admin-filter" onchange="Admin.setFeeFilter('status', this.value)">
                        <option value="">All statuses</option>
                        <option value="outstanding" ${feeState.status === 'outstanding' ? 'selected' : ''}>Outstanding</option>
                        <option value="paid" ${feeState.status === 'paid' ? 'selected' : ''}>Paid</option>
                        <option value="partially_paid" ${feeState.status === 'partially_paid' ? 'selected' : ''}>Partially paid</option>
                    </select>
                </div></div>
                <div class="ws-grid" style="margin-bottom:12px">
                    <div class="ws-stat"><div class="ws-stat__label">Charged</div><div class="ws-stat__value">₹${(totals.charged_paise / 100).toFixed(2)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Collected</div><div class="ws-stat__value">₹${((totals.collected_paise || 0) / 100).toFixed(2)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Outstanding</div><div class="ws-stat__value">₹${((totals.outstanding_paise || 0) / 100).toFixed(2)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Exam (academy paid / reimbursed)</div><div class="ws-stat__value">₹${(((totals.exam_academy_paid_paise) || 0) / 100).toFixed(0)} / ₹${(((totals.exam_reimbursed_paise) || 0) / 100).toFixed(0)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Credits added / used</div><div class="ws-stat__value">₹${(((totals.credit_added_paise) || 0) / 100).toFixed(0)} / ₹${(((totals.credit_used_paise) || 0) / 100).toFixed(0)}</div></div>
                </div>
                <div class="admin-card" style="margin-bottom:12px"><div class="admin-card__body" style="padding:0">
                    ${trs ? `<table class="admin-table"><thead><tr>
                        <th>Student</th><th>Charge</th><th>Period</th><th>Due</th><th>Amount</th><th>Paid</th><th>Balance</th><th>Status</th><th></th>
                    </tr></thead><tbody>${trs}</tbody></table>`
                    : `<div class="admin-empty"><div class="admin-empty__icon">${icon('reports')}</div>
                       <div class="admin-empty__title">No charges for ${feeMonthLabel(feeState.month)}</div>
                       <div class="admin-empty__text">Use “Create Charge” or generate monthly charges from enrolment plans</div></div>`}
                </div></div>
                <div class="admin-card" style="margin-bottom:12px"><div class="admin-card__body">
                    <div style="display:flex;justify-content:space-between;align-items:center">
                        <h3 class="admin-card__title">Payment activity this month</h3>
                    </div>
                    ${paymentsStrip || '<div style="color:var(--color-text-muted);font-size:0.85rem">No payments recorded in ' + feeMonthLabel(feeState.month) + '</div>'}
                </div></div>
                <div class="admin-card"><div class="admin-card__body" style="padding:0">
                    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px 0">
                        <h3 class="admin-card__title">Exam fees &amp; reimbursements</h3>
                        <button class="btn btn--secondary btn--sm" onclick="Admin.examFeeCreate()">+ Record Exam Fee</button>
                    </div>
                    <div style="padding:0 16px 8px;font-size:0.78rem;color:var(--color-text-muted)">Academy payments to exam boards are recorded as costs — they are never counted as money received from families.</div>
                    ${(examFees || []).length ? `<table class="admin-table"><thead><tr>
                        <th>Student</th><th>Exam</th><th>Charged</th><th>Academy paid</th><th>Reimbursed</th><th>Balance</th><th>Status</th><th></th>
                    </tr></thead><tbody>
                    ${examFees.map(e => `<tr>
                        <td>${escapeHtml(nameOf[e.student_id] || e.student_id)}</td>
                        <td>${escapeHtml([e.board, e.grade_level, e.exam_session].filter(Boolean).join(' · '))}</td>
                        <td>₹${(e.fee_charged_paise / 100).toFixed(2)}</td>
                        <td>₹${(e.academy_paid_paise / 100).toFixed(2)}</td>
                        <td>₹${(e.reimbursed_paise / 100).toFixed(2)}</td>
                        <td><strong>₹${(e.reimbursement_balance_paise / 100).toFixed(2)}</strong></td>
                        <td>${escapeHtml((e.status || '').replace(/_/g, ' '))}</td>
                        <td>
                            <button class="btn btn--secondary btn--sm" onclick="Admin.examFeeAcademyPayment('${e.id}')">Academy Paid…</button>
                            <button class="btn btn--secondary btn--sm" onclick="Admin.examFeeReimburse('${e.id}')">Reimburse…</button>
                        </td>
                    </tr>`).join('')}
                    </tbody></table>` : '<div style="padding:12px 16px;color:var(--color-text-muted);font-size:0.85rem">No exam fees recorded</div>'}
                </div></div>`;
        } catch (error) {
            container.innerHTML = `<div class="admin-empty"><div class="admin-empty__icon">${icon('warn')}</div>
                <div class="admin-empty__title">Unable to load the ledger</div>
                <div class="admin-empty__text">${escapeHtml(error.message)}</div></div>`;
        }
    }

    function filterFees(status) {
        feeState.status = status;
        renderFees();
    }

    // ---- modals ----
    async function feeInvoiceOptions(studentId) {
        const invoices = await apiV1Call('/billing/invoices?limit=300');
        return (invoices || [])
            .filter(i => i.status !== 'void' && (!studentId || i.student_id === studentId))
            .map(i => `<option value="${i.id}">${escapeHtml(i.invoice_number)} — ₹${((i.amount_paise - i.amount_paid_paise) / 100).toFixed(2)} due (${escapeHtml(i.billing_month)})</option>`)
            .join('');
    }

    async function feeStudentOptions(selected) {
        const students = await apiCall('/students');
        return (students || []).map(st =>
            `<option value="${st.id}" ${selected === st.id ? 'selected' : ''}>${escapeHtml(st.full_name)}</option>`).join('');
    }

    async function feeRecordPayment(invoiceId) {
        const students = await feeStudentOptions();
        const invoices = await feeInvoiceOptions();
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Record Payment</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.82rem;color:var(--color-text-secondary)">Cash / UPI / bank payments are recorded by staff and confirmed manually.
                They are labelled as admin-recorded — not as independently verified bank transactions.</p>
                <div class="admin-modal__field"><label class="auth__label">Charge (invoice)</label>
                    <select class="auth__input" id="rpInvoice">${invoices}</select></div>
                <div class="admin-modal__field"><label class="auth__label">Amount (₹)</label>
                    <input class="auth__input" id="rpAmount" type="number" step="0.01" min="1"></div>
                <div class="admin-modal__field"><label class="auth__label">Method</label>
                    <select class="auth__input" id="rpMethod">
                        <option value="cash">Cash</option><option value="upi">UPI</option>
                        <option value="bank_transfer">Bank transfer</option><option value="cheque">Cheque</option>
                    </select></div>
                <div class="admin-modal__field"><label class="auth__label">Date</label>
                    <input class="auth__input" type="date" id="rpDate" value="${new Date().toISOString().slice(0, 10)}"></div>
                <div class="admin-modal__field"><label class="auth__label">Reference / receipt no. (optional)</label>
                    <input class="auth__input" id="rpReference"></div>
                <div class="admin-modal__field"><label class="auth__label">Payer name (optional)</label>
                    <input class="auth__input" id="rpPayer"></div>
                <div class="admin-modal__field"><label class="auth__label">Notes</label>
                    <textarea class="auth__input" id="rpNotes" rows="2"></textarea></div>
                <div class="admin-modal__field"><label class="auth__label" style="display:flex;gap:8px;align-items:center">
                    <input type="checkbox" id="rpKeepCredit"> Keep any amount beyond the charge as an advance credit</label></div>
                <p id="rpError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmFeePayment()">Save Payment</button>
            </div>`);
        if (invoiceId) {
            const sel = document.getElementById('rpInvoice');
            if (sel) sel.value = invoiceId;
        }
    }

    async function confirmFeePayment() {
        const err = document.getElementById('rpError');
        const invoiceId = (document.getElementById('rpInvoice') || {}).value;
        const amountRupees = parseFloat((document.getElementById('rpAmount') || {}).value || '0');
        const amount = Math.round(amountRupees * 100);
        if (!invoiceId || !amount) { err.textContent = 'Choose a charge and enter an amount.'; err.style.display = 'block'; return; }
        try {
            await apiV1Call('/billing/payments/manual', {
                method: 'POST',
                body: JSON.stringify({
                    amount_paise: amount,
                    method: (document.getElementById('rpMethod') || {}).value || 'cash',
                    paid_at: (document.getElementById('rpDate') || {}).value || null,
                    reference: (document.getElementById('rpReference') || {}).value || null,
                    payer_name: (document.getElementById('rpPayer') || {}).value || null,
                    notes: (document.getElementById('rpNotes') || {}).value || null,
                    allocations: [{ invoice_id: invoiceId, amount_paise: amount }],
                    keep_remainder_as_credit: !!(document.getElementById('rpKeepCredit') || {}).checked,
                }),
            });
            closeModalDirect();
            showToast('Payment recorded and receipt issued.', 'success');
            renderFees();
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
    }

    async function feeCreateCharge() {
        const students = await feeStudentOptions();
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Create Charge</h3></div>
            <div class="admin-modal__body">
                <div class="admin-modal__field"><label class="auth__label">Student</label>
                    <select class="auth__input" id="ccStudent">${students}</select></div>
                <div class="admin-modal__field"><label class="auth__label">Charge type</label>
                    <select class="auth__input" id="ccType">
                        <option value="tuition">Tuition</option><option value="exam">Exam fee</option><option value="other">Other</option>
                    </select></div>
                <div class="admin-modal__field"><label class="auth__label">Billing month</label>
                    <input class="auth__input" type="month" id="ccMonth" value="${feeState.month}"></div>
                <div class="admin-modal__field"><label class="auth__label">Amount (₹)</label>
                    <input class="auth__input" id="ccAmount" type="number" step="0.01" min="1"></div>
                <div class="admin-modal__field"><label class="auth__label">Description</label>
                    <input class="auth__input" id="ccDescription" placeholder="e.g. Trinity Grade 2 exam fee"></div>
                <div class="admin-modal__field"><label class="auth__label">Due date (optional)</label>
                    <input class="auth__input" type="date" id="ccDue"></div>
                <p id="ccError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmFeeCharge()">Create Charge</button>
            </div>`);
    }

    async function confirmFeeCharge() {
        const err = document.getElementById('ccError');
        const studentId = (document.getElementById('ccStudent') || {}).value;
        const amount = Math.round(parseFloat((document.getElementById('ccAmount') || {}).value || '0') * 100);
        const month = (document.getElementById('ccMonth') || {}).value;
        if (!studentId || !amount || !month) { err.textContent = 'Student, month and amount are required.'; err.style.display = 'block'; return; }
        try {
            const students = await apiCall('/students');
            const st = students.find(x => x.id === studentId);
            const detail = await apiCall('/students/' + studentId);
            const enrol = (detail.enrollments || []).find(e => e.status === 'active') || (detail.enrollments || [])[0];
            if (!enrol) { err.textContent = 'This student has no enrolment — charges attach to an enrolment.'; err.style.display = 'block'; return; }
            await apiV1Call('/billing/invoices', {
                method: 'POST',
                body: JSON.stringify({
                    enrollment_id: enrol.id,
                    billing_month: month,
                    charge_type: (document.getElementById('ccType') || {}).value || 'tuition',
                    description: (document.getElementById('ccDescription') || {}).value || null,
                    amount_paise: amount,
                    due_date: (document.getElementById('ccDue') || {}).value || null,
                }),
            });
            closeModalDirect();
            showToast('Charge created.', 'success');
            renderFees();
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
    }

    async function feeAdvance() {
        const students = await feeStudentOptions();
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Record Advance Payment</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.82rem;color:var(--color-text-secondary)">Held as a credit on the family account and applied to future charges later.</p>
                <div class="admin-modal__field"><label class="auth__label">Student</label>
                    <select class="auth__input" id="adStudent">${students}</select></div>
                <div class="admin-modal__field"><label class="auth__label">Amount (₹)</label>
                    <input class="auth__input" id="adAmount" type="number" step="0.01" min="1"></div>
                <div class="admin-modal__field"><label class="auth__label">Method</label>
                    <select class="auth__input" id="adMethod"><option value="cash">Cash</option><option value="upi">UPI</option><option value="bank_transfer">Bank transfer</option></select></div>
                <div class="admin-modal__field"><label class="auth__label">Reference (optional)</label><input class="auth__input" id="adReference"></div>
                <div class="admin-modal__field"><label class="auth__label">Notes</label><textarea class="auth__input" id="adNotes" rows="2"></textarea></div>
                <p id="adError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmFeeAdvance()">Save Advance</button>
            </div>`);
    }

    async function confirmFeeAdvance() {
        const err = document.getElementById('adError');
        const amount = Math.round(parseFloat((document.getElementById('adAmount') || {}).value || '0') * 100);
        try {
            await apiV1Call('/billing/credits/advance', {
                method: 'POST',
                body: JSON.stringify({
                    student_id: (document.getElementById('adStudent') || {}).value,
                    amount_paise: amount,
                    method: (document.getElementById('adMethod') || {}).value || 'cash',
                    reference: (document.getElementById('adReference') || {}).value || null,
                    notes: (document.getElementById('adNotes') || {}).value || null,
                }),
            });
            closeModalDirect();
            showToast('Advance credit recorded.', 'success');
            renderFees();
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
    }

    async function feeApplyCredit() {
        const students = await feeStudentOptions();
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Apply Advance Credit</h3></div>
            <div class="admin-modal__body">
                <div class="admin-modal__field"><label class="auth__label">Student</label>
                    <select class="auth__input" id="acpStudent" onchange="Admin.feeCreditInvoiceRefresh()">${students}</select></div>
                <div class="admin-modal__field"><label class="auth__label">Charge (invoice)</label>
                    <select class="auth__input" id="acpInvoice"></select></div>
                <div class="admin-modal__field"><label class="auth__label">Amount (₹)</label>
                    <input class="auth__input" id="acpAmount" type="number" step="0.01" min="1"></div>
                <div class="admin-modal__field"><label class="auth__label">Note</label><input class="auth__input" id="acpNote"></div>
                <p id="acpError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmFeeCredit()">Apply</button>
            </div>`);
        await feeCreditInvoiceRefresh();
    }

    async function feeCreditInvoiceRefresh() {
        const studentId = (document.getElementById('acpStudent') || {}).value;
        const sel = document.getElementById('acpInvoice');
        if (sel) sel.innerHTML = await feeInvoiceOptions(studentId);
    }

    async function confirmFeeCredit() {
        const err = document.getElementById('acpError');
        const amount = Math.round(parseFloat((document.getElementById('acpAmount') || {}).value || '0') * 100);
        try {
            await apiV1Call('/billing/credits/apply', {
                method: 'POST',
                body: JSON.stringify({
                    student_id: (document.getElementById('acpStudent') || {}).value,
                    invoice_id: (document.getElementById('acpInvoice') || {}).value,
                    amount_paise: amount,
                    note: (document.getElementById('acpNote') || {}).value || null,
                }),
            });
            closeModalDirect();
            showToast('Credit applied.', 'success');
            renderFees();
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
    }

    const CLAIM_REASONS = [
        'No payment received',
        'Amount does not match the reported amount',
        'Amount is below the required amount',
        'Incorrect transaction reference',
        'Duplicate payment submission',
        'Invalid or missing proof',
        'Wrong student or package',
        'Other',
    ];
    const CLAIM_REASON_MESSAGES = {
        'No payment received': 'We could not verify the payment against the required fee. Please check the amount and submit the correct transaction details.',
        'Amount does not match the reported amount': 'The amount reported does not match our records for this fee. Please review the statement and submit the correct transaction details.',
        'Amount is below the required amount': 'The amount reported is lower than the selected package fee. Please contact the Academy before submitting another claim.',
        'Incorrect transaction reference': 'We could not locate a matching payment using the submitted reference. Please provide a valid transaction reference and proof.',
        'Duplicate payment submission': 'This looks like a duplicate of an earlier submission. Please contact the Academy if you believe this is a mistake.',
        'Invalid or missing proof': 'The submitted proof could not be accepted (missing or unreadable). Please attach a clear PDF, JPG, PNG or WebP of the payment confirmation.',
        'Wrong student or package': 'This claim appears to be linked to the wrong student or fee package. Please contact the Academy to correct it.',
        'Other': 'Please contact the Academy for details about this payment claim.',
    };

    async function _claimAction(paymentId, action, fields, file) {
        const token = localStorage.getItem('academy_token');
        const fd = new FormData();
        Object.entries(fields).forEach(([k, v]) => fd.append(k, v));
        if (file) fd.append('file', file);
        const resp = await fetch(`${API_BASE}/payments/${paymentId}/${action}`, {
            method: 'POST',
            headers: token ? { 'Authorization': `Bearer ${token}` } : {},
            body: fd,
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            const detail = data.detail;
            throw new Error(typeof detail === 'string' ? detail
                : (detail && detail.message) || 'Request failed');
        }
        return data;
    }

    function feeRejectPayment(paymentId) {
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Reject payment claim</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.85rem">Rejecting does <strong>not</strong> change any fee, allocation or collected total — only unverified claims are affected. The student sees your message (with any attachment) in their portal.</p>
                <div class="admin-modal__field"><label class="auth__label">Reason *</label>
                    <select class="auth__input" id="frReason" onchange="Admin.claimReasonChanged()">
                        ${CLAIM_REASONS.map(r => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`).join('')}
                    </select></div>
                <div class="admin-modal__field"><label class="auth__label">Message to student</label>
                    <textarea class="auth__input" id="frMessage" rows="4">${escapeHtml(CLAIM_REASON_MESSAGES['No payment received'])}</textarea></div>
                <div class="admin-modal__field"><label class="auth__label">Attachment (PDF, JPG, PNG, WebP — optional)</label>
                    <input class="auth__input" id="frFile" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp"></div>
                <p id="frError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" id="frBtn" onclick="Admin.feeRejectSubmit('${paymentId}')">Reject claim</button>
            </div>`);
    }

    function claimReasonChanged() {
        const sel = document.getElementById('frReason');
        const ta = document.getElementById('frMessage');
        if (sel && ta && CLAIM_REASON_MESSAGES[sel.value]) ta.value = CLAIM_REASON_MESSAGES[sel.value];
    }

    async function feeRejectSubmit(paymentId) {
        const err = document.getElementById('frError');
        err.style.display = 'none';
        const btn = document.getElementById('frBtn');
        try {
            btn.disabled = true; btn.textContent = 'Rejecting…';
            const fileEl = document.getElementById('frFile');
            const res = await _claimAction(paymentId, 'reject', {
                reason: (document.getElementById('frReason') || {}).value || '',
                message: (document.getElementById('frMessage') || {}).value || '',
            }, fileEl && fileEl.files ? fileEl.files[0] : null);
            closeModalDirect();
            showToast(res.claim_unlinked
                ? 'Claim rejected (⚠ no student link — flagged for resolution)'
                : 'Claim rejected — student notified in their portal', 'success');
            await renderFees();
        } catch (e) {
            err.textContent = e.message; err.style.display = 'block';
            btn.disabled = false; btn.textContent = 'Reject claim';
        }
    }

    function feeClarifyPayment(paymentId) {
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Request clarification</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.85rem">The claim stays <strong>awaiting verification</strong>. Your question (and optional attachment) appears in the student's portal conversation.</p>
                <div class="admin-modal__field"><label class="auth__label">What do you need from the student? *</label>
                    <textarea class="auth__input" id="fcqMessage" rows="4" placeholder="e.g. Please share the UPI transaction reference screenshot for ₹4,500 on 21 October."></textarea></div>
                <div class="admin-modal__field"><label class="auth__label">Attachment (PDF, JPG, PNG, WebP — optional)</label>
                    <input class="auth__input" id="fcqFile" type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp"></div>
                <p id="fcqError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" id="fcqBtn" onclick="Admin.feeClarifySubmit('${paymentId}')">Send request</button>
            </div>`);
    }

    async function feeClarifySubmit(paymentId) {
        const err = document.getElementById('fcqError');
        err.style.display = 'none';
        const btn = document.getElementById('fcqBtn');
        try {
            btn.disabled = true; btn.textContent = 'Sending…';
            const fileEl = document.getElementById('fcqFile');
            await _claimAction(paymentId, 'clarify', {
                message: (document.getElementById('fcqMessage') || {}).value || '',
            }, fileEl && fileEl.files ? fileEl.files[0] : null);
            closeModalDirect();
            showToast('Clarification requested — student notified in their portal', 'success');
            await renderFees();
        } catch (e) {
            err.textContent = e.message; err.style.display = 'block';
            btn.disabled = false; btn.textContent = 'Send request';
        }
    }

    async function feeConfirmPayment(paymentId) {
        // choose the charge this payment settles, then confirm manually
        const [payments, invoices, students] = await Promise.all([
            apiV1Call('/billing/payments?status=pending_verification&limit=100'),
            apiV1Call('/billing/invoices?limit=300'),
            apiCall('/students'),
        ]);
        const payment = (payments || []).find(p => p.id === paymentId);
        if (!payment) { alert('Payment not found (already confirmed?)'); return; }
        const nameOf = {};
        (students || []).forEach(st => { nameOf[st.id] = st.full_name; });
        const outstanding = (invoices || []).filter(i => i.status !== 'void' &&
            (i.amount_paise - i.amount_paid_paise) > 0);
        const opts = outstanding.map(i =>
            `<option value="${i.id}" data-due="${i.amount_paise - i.amount_paid_paise}">` +
            `${escapeHtml(i.invoice_number)} — ${escapeHtml(nameOf[i.student_id] || '')} — ` +
            `₹${((i.amount_paise - i.amount_paid_paise) / 100).toFixed(2)} due (${escapeHtml(i.billing_month)})</option>`).join('');
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Confirm Payment</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.85rem">Verifying a payment of <strong>₹${(payment.amount_paise / 100).toFixed(2)}</strong>
                (${escapeHtml(payment.method || payment.provider)}${payment.provider_payment_id ? ' · ' + escapeHtml(payment.provider_payment_id) : ''}).
                Mark it as Paid only after checking the transaction.</p>
                <div class="admin-modal__field"><label class="auth__label">Apply to charge</label>
                    <select class="auth__input" id="fcInvoice">${opts}
                        <option value="">— no allocation (keep as credit) —</option></select></div>
                <div class="admin-modal__field"><label class="auth__label">Amount to apply (₹)</label>
                    <input class="auth__input" id="fcAmount" type="number" step="0.01" min="0"
                        value="${(payment.amount_paise / 100).toFixed(2)}"></div>
                <div class="admin-modal__field"><label class="auth__label">Verification note (recorded in the audit trail)</label>
                    <textarea class="auth__input" id="fcNote" rows="2" placeholder="e.g. matched bank statement / Razorpay dashboard"></textarea></div>
                <p id="fcError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmFeePaymentSubmit('${paymentId}')">Confirm &amp; Mark Paid</button>
            </div>`);
    }

    async function confirmFeePaymentSubmit(paymentId) {
        const err = document.getElementById('fcError');
        const invoiceId = (document.getElementById('fcInvoice') || {}).value;
        const amount = Math.round(parseFloat((document.getElementById('fcAmount') || {}).value || '0') * 100);
        const note = ((document.getElementById('fcNote') || {}).value || '').trim() || null;
        const payload = { note };
        if (invoiceId && amount > 0) {
            payload.allocations = [{ invoice_id: invoiceId, amount_paise: amount }];
        }
        try {
            const res = await apiV1Call('/billing/payments/' + paymentId + '/confirm', {
                method: 'POST', body: JSON.stringify(payload),
            });
            const applied = (res.allocations || []).map(a => a.invoice + ' ₹' + (a.amount_paise / 100).toFixed(2)).join(', ');
            closeModalDirect();
            showToast('Payment confirmed' + (applied ? ' — applied to ' + applied : '') +
                (res.receipt_number ? ' · receipt ' + res.receipt_number : ''), 'success');
            renderFees();
        } catch (e) { if (err) { err.textContent = e.message; err.style.display = 'block'; } else { alert(e.message); } }
    }

    async function feeInvoiceDetail(invoiceId) {
        const inv = await apiV1Call('/billing/invoices/' + invoiceId);
        const allocs = (inv.allocations || []).map(a => `
            <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--color-border);font-size:0.85rem">
                <span>${escapeHtml(a.allocated_at ? a.allocated_at.slice(0, 10) : '')} · ₹${(a.amount_paise / 100).toFixed(2)}${a.reason ? ' — ' + escapeHtml(a.reason) : ''}</span>
                ${a.amount_paise > 0 ? `<button class="btn btn--secondary btn--sm" onclick="Admin.feeReverseAllocation('${a.id}')">Reverse</button>` : '<span style="color:var(--color-text-muted)">reversal</span>'}
            </div>`).join('');
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">${escapeHtml(inv.invoice_number)}</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.85rem">${escapeHtml(inv.description || inv.charge_type)} · ${escapeHtml(inv.billing_month)}<br>
                Charged ₹${(inv.amount_paise / 100).toFixed(2)} · Paid ₹${(inv.amount_paid_paise / 100).toFixed(2)} ·
                <strong>Balance ₹${(inv.outstanding_paise / 100).toFixed(2)}</strong> · ${escapeHtml(inv.status)}</p>
                <h4 style="margin:12px 0 6px;font-size:0.9rem">Payment activity</h4>
                ${allocs || '<div style="color:var(--color-text-muted);font-size:0.85rem">No payments yet</div>'}
                ${inv.notes ? `<p style="margin-top:10px;font-size:0.8rem;color:var(--color-text-secondary)">Notes: ${escapeHtml(inv.notes)}</p>` : ''}
                <p id="ifError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Close</button>
                ${inv.status !== 'void' && inv.amount_paid_paise === 0
                    ? `<button class="btn btn--secondary" onclick="Admin.feeVoidInvoice('${inv.id}')">Void Charge</button>` : ''}
            </div>`);
    }

    async function feeReverseAllocation(allocationId) {
        if (!window.confirm('Reverse this allocation? The entry is kept with a reversal record — nothing is deleted.')) return;
        const reason = window.prompt('Reason for the reversal (required):');
        if (!reason || reason.trim().length < 3) { alert('A reason of at least 3 characters is required.'); return; }
        try {
            await apiV1Call('/billing/allocations/' + allocationId + '/reverse', {
                method: 'POST', body: JSON.stringify({ reason: reason.trim() }),
            });
            closeModalDirect();
            showToast('Allocation reversed and recorded in the audit trail.', 'success');
            renderFees();
        } catch (e) { alert(e.message); }
    }

    async function feeVoidInvoice(invoiceId) {
        const reason = window.prompt('Reason for voiding this charge (required):');
        if (!reason || reason.trim().length < 3) { alert('A reason of at least 3 characters is required.'); return; }
        try {
            await apiV1Call('/billing/invoices/' + invoiceId + '/void', {
                method: 'POST', body: JSON.stringify({ reason: reason.trim() }),
            });
            closeModalDirect();
            showToast('Charge voided.', 'success');
            renderFees();
        } catch (e) { alert(e.message); }
    }

    async function feeViewReceipt(paymentId) {
        try {
            const response = await fetch((window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
                ? 'http://127.0.0.1:8000' : '') + '/api/v1/billing/payments/' + paymentId + '/receipt', {
                headers: { Authorization: 'Bearer ' + localStorage.getItem('academy_token') },
            });
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            window.open(url, '_blank');
            setTimeout(() => URL.revokeObjectURL(url), 8000);
        } catch (e) { alert(e.message); }
    }

    function feeExport() {
        apiV1Call('/billing/statement/export?student_id=' + (feeState.student || '')).catch(() => null);
        const base = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
            ? 'http://127.0.0.1:8000' : '';
        fetch(base + '/api/v1/billing/statement/export' + (feeState.student ? '?student_id=' + feeState.student : ''), {
            headers: { Authorization: 'Bearer ' + localStorage.getItem('academy_token') },
        }).then(async (response) => {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'chankarts-statement.csv';
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 4000);
        }).catch(e => alert(e.message));
    }

    async function examFeeCreate() {
        const students = await feeStudentOptions();
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Record Exam Fee</h3></div>
            <div class="admin-modal__body">
                <div class="admin-modal__field"><label class="auth__label">Student</label>
                    <select class="auth__input" id="efStudent">${students}</select></div>
                <div class="admin-modal__field"><label class="auth__label">Exam board</label>
                    <input class="auth__input" id="efBoard" placeholder="Trinity, Rockschool…"></div>
                <div class="admin-modal__field"><label class="auth__label">Instrument</label><input class="auth__input" id="efInstrument" placeholder="piano"></div>
                <div class="admin-modal__field"><label class="auth__label">Grade / level</label><input class="auth__input" id="efGrade"></div>
                <div class="admin-modal__field"><label class="auth__label">Exam session</label><input class="auth__input" id="efSession" placeholder="Spring 2027"></div>
                <div class="admin-modal__field"><label class="auth__label">Fee charged to family (₹)</label>
                    <input class="auth__input" id="efCharged" type="number" step="0.01" min="0"></div>
                <div class="admin-modal__field"><label class="auth__label">Already paid by academy to the board (₹, optional)</label>
                    <input class="auth__input" id="efAcademyPaid" type="number" step="0.01" min="0" value="0"></div>
                <div class="admin-modal__field"><label class="auth__label">Provider reference (optional)</label><input class="auth__input" id="efRef"></div>
                <div class="admin-modal__field"><label class="auth__label" style="display:flex;gap:8px;align-items:center">
                    <input type="checkbox" id="efInvoice" checked> Create the family charge as an exam invoice</label></div>
                <p id="efError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmExamFee()">Save</button>
            </div>`);
    }

    async function confirmExamFee() {
        const err = document.getElementById('efError');
        try {
            await apiV1Call('/billing/exam-fees', {
                method: 'POST',
                body: JSON.stringify({
                    student_id: (document.getElementById('efStudent') || {}).value,
                    board: (document.getElementById('efBoard') || {}).value || null,
                    instrument: (document.getElementById('efInstrument') || {}).value || null,
                    grade_level: (document.getElementById('efGrade') || {}).value || null,
                    exam_session: (document.getElementById('efSession') || {}).value || null,
                    fee_charged_paise: Math.round(parseFloat((document.getElementById('efCharged') || {}).value || '0') * 100),
                    academy_paid_paise: Math.round(parseFloat((document.getElementById('efAcademyPaid') || {}).value || '0') * 100),
                    provider_reference: (document.getElementById('efRef') || {}).value || null,
                    create_invoice: !!(document.getElementById('efInvoice') || {}).checked,
                    billing_month: feeState.month,
                }),
            });
            closeModalDirect();
            showToast('Exam fee recorded.', 'success');
            renderFees();
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
    }

    async function examFeeAcademyPayment(examFeeId) {
        const amount = window.prompt('Amount the academy paid the exam board (₹):');
        if (!amount) return;
        const ref = window.prompt('Provider reference (optional):') || null;
        try {
            await apiV1Call('/billing/exam-fees/' + examFeeId + '/academy-payment', {
                method: 'POST',
                body: JSON.stringify({
                    academy_paid_delta_paise: Math.round(parseFloat(amount) * 100),
                    provider_reference: ref,
                }),
            });
            showToast('Academy payment recorded as a cost.', 'success');
            renderFees();
        } catch (e) { alert(e.message); }
    }

    async function examFeeReimburse(examFeeId) {
        const amount = window.prompt('Amount reimbursed by the family (₹):');
        if (!amount) return;
        const method = window.prompt('Method (cash/upi/bank_transfer):', 'upi') || 'upi';
        const ref = window.prompt('Reference (optional):') || null;
        try {
            await apiV1Call('/billing/exam-fees/' + examFeeId + '/reimburse', {
                method: 'POST',
                body: JSON.stringify({
                    amount_paise: Math.round(parseFloat(amount) * 100),
                    method: method,
                    reference: ref,
                }),
            });
            showToast('Reimbursement recorded — receipt issued.', 'success');
            renderFees();
        } catch (e) { alert(e.message); }
    }

    async function feeGenerateCharges() {
        try {
            const res = await apiV1Call('/billing/generate-charges', {
                method: 'POST', body: JSON.stringify({ billing_month: feeState.month, due_day: 5 }),
            });
            showToast(`Generated ${res.created.length} charge(s), ${res.skipped.length} skipped.`, 'success');
            renderFees();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Attendance (per-student session history)
    // ========================================
    let attendanceStudentId = null;

    async function renderAttendance() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading attendance...</div>';

        try {
            const students = await apiCall('/students');
            if (!attendanceStudentId && students.length > 0) attendanceStudentId = students[0].id;

            const options = students.map(s => `
                <option value="${s.id}" ${s.id === attendanceStudentId ? 'selected' : ''}>
                    ${escapeHtml(s.full_name)} (${escapeHtml(s.cma_registration_id || '')})
                </option>
            `).join('');

            let sessions = [];
            if (attendanceStudentId) {
                sessions = await apiV1Call(`/sessions?student_id=${attendanceStudentId}&limit=300`);
            }
            sessions.sort((a, b) => (a.scheduled_date + a.scheduled_start) < (b.scheduled_date + b.scheduled_start) ? 1 : -1);

            const counts = {
                scheduled: sessions.filter(s => s.status === 'scheduled').length,
                completed: sessions.filter(s => s.status === 'completed').length,
                rescheduling_required: sessions.filter(s => s.status === 'rescheduling_required').length,
                cancelled: sessions.filter(s => s.status === 'cancelled').length,
            };

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Attendance / Session Records</h1>
                        <p class="admin-header__subtitle">Completed, scheduled and rescheduled classes per student</p>
                    </div>
                </div>
                <div class="admin-card">
                    <div class="admin-card__body">
                        <label class="form-label" for="attendanceStudent">Select student</label>
                        <select id="attendanceStudent" class="auth__input" onchange="Admin.selectAttendanceStudent(this.value)">
                            ${options || '<option value="">No students yet</option>'}
                        </select>
                    </div>
                </div>
                ${attendanceStudentId ? `
                    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px;">
                        <div class="admin-card"><div class="admin-card__body"><div style="font-size:12px;color:#706B60">Scheduled</div><div style="font-size:22px;font-weight:700">${counts.scheduled}</div></div></div>
                        <div class="admin-card"><div class="admin-card__body"><div style="font-size:12px;color:#706B60">Completed</div><div style="font-size:22px;font-weight:700;color:#176B3A">${counts.completed}</div></div></div>
                        <div class="admin-card"><div class="admin-card__body"><div style="font-size:12px;color:#706B60">Reschedule pending</div><div style="font-size:22px;font-weight:700;color:#E84141">${counts.rescheduling_required}</div></div></div>
                        <div class="admin-card"><div class="admin-card__body"><div style="font-size:12px;color:#706B60">Cancelled</div><div style="font-size:22px;font-weight:700;color:#706B60">${counts.cancelled}</div></div></div>
                    </div>
                    <div class="admin-card">
                        <div class="admin-card__body" style="padding:0;">
                            ${sessions.length > 0 ? `
                                <table class="admin-table">
                                    <thead>
                                        <tr>
                                            <th>Date</th>
                                            <th>Time</th>
                                            <th>Faculty</th>
                                            <th>Status</th>
                                            <th>Topics covered</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${sessions.map(s => `
                                            <tr>
                                                <td>${formatDate(s.scheduled_date)}</td>
                                                <td>${s.scheduled_start} – ${s.scheduled_end}</td>
                                                <td>${escapeHtml(s.instructor_name || '—')}</td>
                                                <td><span class="badge badge--${getStatusBadgeClass(s.status)}">${formatStatus(s.status)}</span></td>
                                                <td>${escapeHtml(s.topics_covered || '—')}</td>
                                            </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                                <div class="admin-empty">
                                    <div class="admin-empty__icon"> ${icon("attendance")}</div>
                                    <div class="admin-empty__title">No sessions recorded</div>
                                    <div class="admin-empty__text">Completed and scheduled classes appear here</div>
                                </div>
                            `}
                        </div>
                    </div>
                ` : ''}
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load attendance</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    function selectAttendanceStudent(id) {
        attendanceStudentId = id;
        renderAttendance();
    }

    // ========================================
    // Progress (syllabus + reports overview)
    // ========================================
    async function renderProgress() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading progress...</div>';

        try {
            const data = await apiCall('/progress');
            const rows = data.students || [];

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Student Progress</h1>
                        <p class="admin-header__subtitle">Syllabus completion, latest reports and pending assignments</p>
                    </div>
                </div>
                <div class="admin-card">
                    <div class="admin-card__body" style="padding:0;">
                        ${rows.length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr>
                                        <th>Student</th>
                                        <th>Syllabus Progress</th>
                                        <th>Latest Report</th>
                                        <th>Pending Assignments</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${rows.map(r => `
                                        <tr>
                                            <td><strong>${escapeHtml(r.student_name)}</strong><br>
                                                <small>${escapeHtml(r.cma_registration_id || '')}</small></td>
                                            <td>
                                                ${r.syllabus_total > 0 ? `
                                                    <div style="display:flex;align-items:center;gap:8px;">
                                                        <div style="flex:1;height:6px;background:#E7DFD0;border-radius:3px;overflow:hidden;">
                                                            <div style="height:100%;width:${r.syllabus_percent}%;background:#B58A35;"></div>
                                                        </div>
                                                        <span>${r.syllabus_completed}/${r.syllabus_total} (${r.syllabus_percent}%)</span>
                                                    </div>
                                                ` : '<span style="color:#706B60">No syllabus items yet</span>'}
                                            </td>
                                            <td>${r.latest_report ? `
                                                <strong>${escapeHtml(r.latest_report.report_month)}</strong><br>
                                                <span class="badge badge--${getStatusBadgeClass(r.latest_report.status)}">${formatStatus(r.latest_report.status)}</span>
                                            ` : '<span style="color:#706B60">None yet</span>'}</td>
                                            <td>${r.pending_assignments}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("progress")}</div>
                                <div class="admin-empty__title">No students yet</div>
                                <div class="admin-empty__text">Progress data appears once students are enrolled</div>
                            </div>
                        `}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load progress</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    // ========================================
    // Exams / Milestones
    // ========================================
    async function renderExams() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading exams...</div>';

        try {
            const [exams, milestones, students] = await Promise.all([
                apiV1Call('/learning/exams'),
                apiV1Call('/learning/milestones'),
                apiCall('/students'),
            ]);
            const studentMap = {};
            (students || []).forEach(s => { studentMap[s.id] = s.full_name; });

            const examRows = (exams || []).map(e => `
                <tr>
                    <td><strong>${escapeHtml(e.board)} Grade ${escapeHtml(e.grade || '—')}</strong><br>
                        <small>${escapeHtml(e.instrument)}</small></td>
                    <td>${escapeHtml(studentMap[e.student_id] || '—')}</td>
                    <td>${e.submission_deadline ? formatDate(e.submission_deadline) : '—'}</td>
                    <td><span class="badge badge--${getStatusBadgeClass(e.readiness === 'exam_ready' ? 'completed' : (e.readiness || 'pending'))}">${formatStatus(e.readiness || 'not_assessed')}</span></td>
                    <td>${(e.items || []).length}</td>
                    <td>
                        <button class="btn btn--secondary" onclick="Admin.editExam('${e.id}')">Update</button>
                    </td>
                </tr>
            `).join('');

            const milestoneRows = (milestones || []).map(m => `
                <tr>
                    <td><strong>${escapeHtml(m.title)}</strong><br><small>${escapeHtml(m.milestone_type)}</small></td>
                    <td>${escapeHtml(studentMap[m.student_id] || '—')}</td>
                    <td>${m.due_date ? formatDate(m.due_date) : '—'}</td>
                    <td>${m.achieved_at ? formatDate(m.achieved_at) : '—'}</td>
                    <td><span class="badge badge--${getStatusBadgeClass(m.status === 'achieved' ? 'completed' : m.status || 'pending')}">${formatStatus(m.status || 'upcoming')}</span></td>
                </tr>
            `).join('');

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Exams / Certifications</h1>
                        <p class="admin-header__subtitle">Board exams, graded assessments and milestones</p>
                    </div>
                    <button class="btn btn--primary" onclick="Admin.showExamModal()">+ New Exam</button>
                </div>
                <div class="admin-card">
                    <div class="admin-card__body" style="padding:0;">
                        <h3 style="margin:0 0 12px;padding:16px 16px 0;">Exams</h3>
                        ${(exams || []).length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr><th>Exam</th><th>Student</th><th>Deadline</th><th>Readiness</th><th>Items</th><th></th></tr>
                                </thead>
                                <tbody>${examRows}</tbody>
                            </table>
                        ` : '<div class="admin-empty" style="padding:16px;"><div class="admin-empty__icon"> ${icon("exams")}</div><div class="admin-empty__title">No exams configured</div><div class="admin-empty__text">Create the first exam to get started</div></div>'}
                    </div>
                </div>
                <div class="admin-card">
                    <div class="admin-card__body" style="padding:0;">
                        <div style="display:flex;justify-content:space-between;align-items:center;padding:16px 16px 0;">
                            <h3 style="margin:0;">Milestones</h3>
                            <button class="btn btn--secondary" onclick="Admin.showMilestoneModal()">+ New Milestone</button>
                        </div>
                        ${(milestones || []).length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr><th>Milestone</th><th>Student</th><th>Due</th><th>Achieved</th><th>Status</th></tr>
                                </thead>
                                <tbody>${milestoneRows}</tbody>
                            </table>
                        ` : '<div class="admin-empty" style="padding:16px;"><div class="admin-empty__icon"> ${icon("exams")}</div><div class="admin-empty__title">No milestones yet</div></div>'}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load exams</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    async function editExam(id) {
        const exams = await apiV1Call('/learning/exams');
        const exam = (exams || []).find(x => x.id === id);
        if (!exam) return;
        showModal(`
            <div class="admin-modal__header">
                <h2 class="admin-modal__title">Update Exam — ${escapeHtml(exam.board)} Grade ${escapeHtml(exam.grade || '—')}</h2>
            </div>
            <div class="admin-modal__body">
                <label class="form-label">Application status</label>
                <select id="examAppStatus" class="auth__input">
                    ${['not_started', 'preparing', 'applied', 'confirmed'].map(s => `<option value="${s}" ${exam.application_status === s ? 'selected' : ''}>${s.replace('_', ' ')}</option>`).join('')}
                </select>
                <label class="form-label" style="margin-top:12px;">Readiness</label>
                <select id="examReadiness" class="auth__input">
                    ${['not_assessed', 'developing', 'ready', 'exam_ready'].map(s => `<option value="${s}" ${exam.readiness === s ? 'selected' : ''}>${s.replace('_', ' ')}</option>`).join('')}
                </select>
                <label class="form-label" style="margin-top:12px;">Result</label>
                <input id="examResult" class="auth__input" value="${escapeHtml(exam.result || '')}" placeholder="pending, pass, merit, distinction…" />
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmExamUpdate('${id}')">Save</button>
            </div>
        `);
    }

    async function confirmExamUpdate(id) {
        const payload = {
            application_status: document.getElementById('examAppStatus').value,
            readiness: document.getElementById('examReadiness').value,
            result: document.getElementById('examResult').value.trim() || null,
        };
        try {
            await apiV1Call(`/learning/exams/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
            closeModalDirect();
            renderExams();
        } catch (e) { alert(e.message); }
    }

    async function showExamModal() {
        const enrollments = await apiV1Call('/portal/enrollments');
        if (!enrollments || !enrollments.length) { alert('No enrollments found — create an enrollment first.'); return; }
        const options = enrollments.map(e => `<option value="${e.id}">${escapeHtml(e.student_name)} — ${escapeHtml(e.programme_name)}</option>`).join('');
        showModal(`
            <div class="admin-modal__header">
                <h2 class="admin-modal__title">Add Exam</h2>
            </div>
            <div class="admin-modal__body">
                <label class="form-label">Enrollment</label>
                <select id="examEnrollment" class="auth__input">${options}</select>
                <label class="form-label" style="margin-top:12px;">Board</label>
                <input id="examBoard" class="auth__input" value="academy" />
                <label class="form-label" style="margin-top:12px;">Instrument</label>
                <input id="examInstrument" class="auth__input" placeholder="e.g. Piano" />
                <label class="form-label" style="margin-top:12px;">Grade</label>
                <input id="examGrade" class="auth__input" placeholder="e.g. 2" />
                <label class="form-label" style="margin-top:12px;">Submission deadline</label>
                <input id="examDeadline" type="date" class="auth__input" />
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmExam()">Add Exam</button>
            </div>
        `);
    }

    async function confirmExam() {
        const enrollmentId = document.getElementById('examEnrollment').value;
        const enrollments = await apiV1Call('/portal/enrollments');
        const enrollment = (enrollments || []).find(e => e.id === enrollmentId);
        const payload = {
            student_id: enrollment ? enrollment.student_id : null,
            enrollment_id: enrollmentId,
            board: document.getElementById('examBoard').value.trim() || 'academy',
            instrument: document.getElementById('examInstrument').value.trim(),
            grade: document.getElementById('examGrade').value.trim() || null,
            submission_deadline: document.getElementById('examDeadline').value || null,
        };
        if (!payload.instrument) { alert('Instrument is required'); return; }
        try {
            await apiV1Call('/learning/exams', { method: 'POST', body: JSON.stringify(payload) });
            closeModalDirect();
            renderExams();
        } catch (e) { alert(e.message); }
    }

    async function showMilestoneModal() {
        const enrollments = await apiV1Call('/portal/enrollments');
        if (!enrollments || !enrollments.length) { alert('No enrollments found — create an enrollment first.'); return; }
        const options = enrollments.map(e => `<option value="${e.id}">${escapeHtml(e.student_name)} — ${escapeHtml(e.programme_name)}</option>`).join('');
        showModal(`
            <div class="admin-modal__header">
                <h2 class="admin-modal__title">Add Milestone</h2>
            </div>
            <div class="admin-modal__body">
                <label class="form-label">Enrollment</label>
                <select id="msEnrollment" class="auth__input">${options}</select>
                <label class="form-label" style="margin-top:12px;">Title</label>
                <input id="msTitle" class="auth__input" placeholder="e.g. First recital performance" />
                <label class="form-label" style="margin-top:12px;">Description</label>
                <textarea id="msDescription" class="auth__input auth__textarea" rows="2"></textarea>
                <label class="form-label" style="margin-top:12px;">Due date</label>
                <input id="msDue" type="date" class="auth__input" />
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmMilestone()">Add Milestone</button>
            </div>
        `);
    }

    async function confirmMilestone() {
        const enrollmentId = document.getElementById('msEnrollment').value;
        const enrollments = await apiV1Call('/portal/enrollments');
        const enrollment = (enrollments || []).find(e => e.id === enrollmentId);
        const title = document.getElementById('msTitle').value.trim();
        if (!title) { alert('Title is required'); return; }
        try {
            await apiV1Call('/learning/milestones', {
                method: 'POST',
                body: JSON.stringify({
                    student_id: enrollment ? enrollment.student_id : null,
                    enrollment_id: enrollmentId,
                    title,
                    description: document.getElementById('msDescription').value.trim() || null,
                    due_date: document.getElementById('msDue').value || null,
                }),
            });
            closeModalDirect();
            renderExams();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Assignments
    // ========================================
    async function renderAssignments() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading assignments...</div>';

        try {
            const [data, students] = await Promise.all([
                apiV1Call('/learning/assignments?limit=200'),
                apiCall('/students'),
            ]);
            const assignments = Array.isArray(data) ? data : (data.assignments || []);
            const studentMap = {};
            (students || []).forEach(s => { studentMap[s.id] = s.full_name; });

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Assignments / Quizzes</h1>
                        <p class="admin-header__subtitle">All assignments issued to students</p>
                    </div>
                    <button class="btn btn--primary" onclick="Admin.showAssignmentModal()">+ New Assignment</button>
                </div>
                <div class="admin-card">
                    <div class="admin-card__body" style="padding:0;">
                        ${assignments.length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr><th>Title</th><th>Student</th><th>Assigned</th><th>Due</th><th>Status</th><th>Submission</th></tr>
                                </thead>
                                <tbody>
                                    ${assignments.map(a => `
                                        <tr>
                                            <td>${escapeHtml(a.title)}</td>
                                            <td>${escapeHtml(studentMap[a.student_id] || '—')}</td>
                                            <td>${formatDate(a.assigned_date)}</td>
                                            <td>${a.due_date ? formatDate(a.due_date) : '—'}</td>
                                            <td><span class="badge badge--${getStatusBadgeClass(a.status)}">${formatStatus(a.status)}</span></td>
                                            <td>${a.submission && a.submission.submitted_at ? formatDate(a.submission.submitted_at) : '—'}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("assignments")}</div>
                                <div class="admin-empty__title">No assignments yet</div>
                                <div class="admin-empty__text">Create the first assignment to get started</div>
                            </div>
                        `}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load assignments</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    async function showAssignmentModal() {
        const enrollments = await apiV1Call('/portal/enrollments');
        if (!enrollments || !enrollments.length) { alert('No enrollments found — create an enrollment first.'); return; }
        const options = enrollments.map(e => `<option value="${e.id}">${escapeHtml(e.student_name)} — ${escapeHtml(e.programme_name)}</option>`).join('');
        showModal(`
            <div class="admin-modal__header">
                <h2 class="admin-modal__title">Create Assignment</h2>
            </div>
            <div class="admin-modal__body">
                <label class="form-label">Enrollment</label>
                <select id="assignEnrollment" class="auth__input">${options}</select>
                <label class="form-label" style="margin-top:12px;">Title</label>
                <input id="assignTitle" class="auth__input" placeholder="e.g. Scales practice – C & G major" />
                <label class="form-label" style="margin-top:12px;">Instructions</label>
                <textarea id="assignInstructions" class="auth__input auth__textarea" rows="3"></textarea>
                <label class="form-label" style="margin-top:12px;">Due date (optional)</label>
                <input id="assignDue" type="date" class="auth__input" />
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmAssignment()">Create Assignment</button>
            </div>
        `);
    }

    async function confirmAssignment() {
        const enrollmentId = document.getElementById('assignEnrollment').value;
        const title = document.getElementById('assignTitle').value.trim();
        const instructions = document.getElementById('assignInstructions').value.trim();
        const dueDate = document.getElementById('assignDue').value;
        if (!title) { alert('Title is required'); return; }
        try {
            await apiV1Call('/learning/assignments', {
                method: 'POST',
                body: JSON.stringify({
                    enrollment_id: enrollmentId,
                    title,
                    instructions: instructions || null,
                    due_date: dueDate || null,
                }),
            });
            closeModalDirect();
            renderAssignments();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Resources (global recommendation catalogue)
    // ========================================
    const RESOURCE_TYPES = [
        { id: 'book', label: 'Books' },
        { id: 'instrument', label: 'Instruments' },
        { id: 'accessory', label: 'Accessories' },
        { id: 'stand_notebook', label: 'Stand/Notebook' },
        { id: 'metronome_tuner', label: 'Metronome/Tuner' },
        { id: 'online_link', label: 'Online Links' },
    ];

    async function renderResources() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading resources...</div>';

        try {
            const items = await apiV1Call('/learning/recommendations');

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Resource Recommendations</h1>
                        <p class="admin-header__subtitle">Global catalogue shared with all students (books, instruments, accessories, links)</p>
                    </div>
                    <button class="btn btn--primary" onclick="Admin.showResourceModal()">+ New Recommendation</button>
                </div>
                <div class="admin-card">
                    <div class="admin-card__body" style="padding:0;">
                        ${items.length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr><th>Name</th><th>Type</th><th>Author / Brand</th><th>Link</th><th>Faculty Note</th></tr>
                                </thead>
                                <tbody>
                                    ${items.map(r => `
                                        <tr>
                                            <td><strong>${escapeHtml(r.name)}</strong>${r.suitability ? `<br><small>${escapeHtml(r.suitability)}</small>` : ''}</td>
                                            <td><span class="badge badge--accent">${escapeHtml(r.resource_type)}</span></td>
                                            <td>${escapeHtml(r.author_or_brand || '—')}</td>
                                            <td>${r.external_url ? `<a href="${escapeHtml(r.external_url)}" target="_blank" rel="noopener">Open</a>` : '—'}</td>
                                            <td>${escapeHtml(r.faculty_note || '—')}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("resources")}</div>
                                <div class="admin-empty__title">No recommendations yet</div>
                                <div class="admin-empty__text">Add books, instruments, accessories and links to the shared catalogue</div>
                            </div>
                        `}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load resources</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    async function showResourceModal() {
        const students = await apiCall('/students');
        showModal(`
            <div class="admin-modal__header">
                <h2 class="admin-modal__title">New Resource Recommendation</h2>
            </div>
            <div class="admin-modal__body">
                <label class="form-label">Resource type</label>
                <select id="resType" class="auth__input">
                    ${RESOURCE_TYPES.map(t => `<option value="${t.id}">${t.label}</option>`).join('')}
                </select>
                <label class="form-label" style="margin-top:12px;">Name</label>
                <input id="resName" class="auth__input" placeholder="e.g. Hanon Exercise No.1" />
                <label class="form-label" style="margin-top:12px;">Author / Brand</label>
                <input id="resAuthor" class="auth__input" />
                <label class="form-label" style="margin-top:12px;">Description</label>
                <textarea id="resDescription" class="auth__input auth__textarea" rows="2"></textarea>
                <label class="form-label" style="margin-top:12px;">Suitability</label>
                <input id="resSuitability" class="auth__input" placeholder="e.g. Beginner to Intermediate" />
                <label class="form-label" style="margin-top:12px;">External URL (optional)</label>
                <input id="resUrl" class="auth__input" placeholder="https://" />
                <label class="form-label" style="margin-top:12px;">Faculty note</label>
                <textarea id="resNote" class="auth__input auth__textarea" rows="2"></textarea>
                <label class="form-label" style="margin-top:12px;">Who can see this?</label>
                <select id="resScope" class="auth__input" onchange="Admin.toggleResourceScope()">
                    <option value="all">All active students</option>
                    <option value="programme">Students on a specific instrument / course</option>
                    <option value="level">Students at a specific level</option>
                    <option value="students">Only specific student(s)</option>
                </select>
                <div id="resProgrammeWrap" style="display:none">
                    <label class="form-label" style="margin-top:12px;">Instrument / course id</label>
                    <input id="resProgramme" class="auth__input" placeholder="piano, guitar, ukulele…" />
                </div>
                <div id="resLevelWrap" style="display:none">
                    <label class="form-label" style="margin-top:12px;">Level</label>
                    <select id="resLevel" class="auth__input">
                        <option value="beginner">Beginner</option>
                        <option value="intermediate">Intermediate</option>
                        <option value="advanced">Advanced</option>
                    </select>
                </div>
                <div id="resStudentsWrap" style="display:none">
                    <label class="form-label" style="margin-top:12px;">Students</label>
                    <select id="resStudents" class="auth__input" multiple size="5">
                        ${(students || []).map(st => `<option value="${st.id}">${escapeHtml(st.full_name)}</option>`).join('')}
                    </select>
                </div>
                <p class="form-label" style="margin-top:10px;font-size:0.78rem;color:var(--color-text-muted)">
                    Only the selected audience will see this resource — it is enforced by the API, not just hidden on screen.</p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmResource()">Add Recommendation</button>
            </div>
        `);
    }

    function toggleResourceScope() {
        const scope = (document.getElementById('resScope') || {}).value || 'all';
        const show = (id, on) => { const el = document.getElementById(id); if (el) el.style.display = on ? 'block' : 'none'; };
        show('resProgrammeWrap', scope === 'programme' || scope === 'level');
        show('resLevelWrap', scope === 'level');
        show('resStudentsWrap', scope === 'students');
    }

    async function confirmResource() {
        const name = document.getElementById('resName').value.trim();
        const resourceType = document.getElementById('resType').value;
        const scope = (document.getElementById('resScope') || {}).value || 'all';
        const programme = ((document.getElementById('resProgramme') || {}).value || '').trim() || null;
        const level = ((document.getElementById('resLevel') || {}).value || '').trim() || null;
        const targets = Array.from((document.getElementById('resStudents') || {}).selectedOptions || [])
            .map(o => o.value);
        if (!name) { alert('Name is required'); return; }
        if (scope === 'programme' && !programme) { alert('Enter the instrument / course id for this audience'); return; }
        if (scope === 'students' && !targets.length) { alert('Select at least one student'); return; }
        try {
            await apiV1Call('/learning/recommendations', {
                method: 'POST',
                body: JSON.stringify({
                    resource_type: resourceType,
                    name,
                    author_or_brand: document.getElementById('resAuthor').value.trim() || null,
                    description: document.getElementById('resDescription').value.trim() || null,
                    suitability: document.getElementById('resSuitability').value.trim() || null,
                    external_url: document.getElementById('resUrl').value.trim() || null,
                    faculty_note: document.getElementById('resNote').value.trim() || null,
                    visibility_scope: scope,
                    programme_id: scope === 'programme' || scope === 'level' ? programme : null,
                    target_student_ids: scope === 'students' ? targets : [],
                }),
            });
            closeModalDirect();
            showToast('Recommendation added — visible only to its audience.', 'success');
            renderResources();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Reports
    // ========================================
    async function renderReports() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading reports...</div>';

        try {
            const [data, students] = await Promise.all([
                apiV1Call('/learning/reports'),
                apiCall('/students'),
            ]);
            const reports = Array.isArray(data) ? data : (data.reports || []);
            const studentMap = {};
            (students || []).forEach(s => { studentMap[s.id] = s.full_name; });

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Monthly Reports</h1>
                        <p class="admin-header__subtitle">Draft → Submitted → Approved &amp; published. Approval releases a report to the family; staff notes stay private.</p>
                    </div>
                    <button class="btn btn--primary" onclick="Admin.showReportModal()">+ New Report</button>
                </div>
                <div class="admin-card">
                    <div class="admin-card__body" style="padding:0;">
                        ${reports.length > 0 ? `
                            <table class="admin-table">
                                <thead>
                                    <tr><th>Month</th><th>Student</th><th>Summary</th><th>Status</th><th>Revision</th><th>Actions</th></tr>
                                </thead>
                                <tbody>
                                    ${reports.map(r => `
                                        <tr>
                                            <td>${escapeHtml(r.report_month)}</td>
                                            <td>${escapeHtml(studentMap[r.student_id] || '—')}</td>
                                            <td>${escapeHtml((r.progress_summary || '').slice(0, 80) || '—')}</td>
                                            <td><span class="badge badge--${getStatusBadgeClass(r.status)}">${formatStatus(r.status)}</span></td>
                                            <td>${r.revision}</td>
                                            <td>
                                                ${r.status === 'published'
                                                    ? (r.published_at ? formatDate(r.published_at) : '—')
                                                    : `
                                                    <button class="btn btn--primary btn--sm" onclick="Admin.publishReport('${r.id}')"
                                                        title="Approve and release to the family">${r.status === 'submitted' ? 'Approve &amp; Publish' : 'Publish'}</button>
                                                    ${r.status === 'submitted' ? '<div style="margin-top:4px;font-size:0.72rem;color:var(--color-warning)">Submitted by faculty — awaiting approval</div>' : ''}
                                                `}
                                            </td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : `
                            <div class="admin-empty">
                                <div class="admin-empty__icon"> ${icon("reports")}</div>
                                <div class="admin-empty__title">No reports yet</div>
                                <div class="admin-empty__text">Monthly reports created by faculty appear here</div>
                            </div>
                        `}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load reports</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    async function publishReport(id) {
        try {
            await apiV1Call(`/learning/reports/${id}/publish`, { method: 'POST', body: '{}' });
            renderReports();
        } catch (e) { alert(e.message); }
    }

    async function showReportModal() {
        const enrollments = await apiV1Call('/portal/enrollments');
        if (!enrollments || !enrollments.length) { alert('No enrollments found — create an enrollment first.'); return; }
        const options = enrollments.map(e => `<option value="${e.id}">${escapeHtml(e.student_name)} — ${escapeHtml(e.programme_name)}</option>`).join('');
        const now = new Date();
        const month = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0');
        showModal(`
            <div class="admin-modal__header">
                <h2 class="admin-modal__title">Create Monthly Report</h2>
            </div>
            <div class="admin-modal__body">
                <label class="form-label">Enrollment</label>
                <select id="repEnrollment" class="auth__input">${options}</select>
                <label class="form-label" style="margin-top:12px;">Report month (YYYY-MM)</label>
                <input id="repMonth" class="auth__input" value="${month}" placeholder="YYYY-MM" />
                <label class="form-label" style="margin-top:12px;">Progress summary</label>
                <textarea id="repSummary" class="auth__input auth__textarea" rows="3"></textarea>
                <label class="form-label" style="margin-top:12px;">Topics covered</label>
                <textarea id="repTopics" class="auth__input auth__textarea" rows="2"></textarea>
                <label class="form-label" style="margin-top:12px;">Private staff notes (never shown to family)</label>
                <textarea id="repStaffNotes" class="auth__input auth__textarea" rows="2"></textarea>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmReport()">Save Draft</button>
            </div>
        `);
    }

    async function confirmReport() {
        const enrollmentId = document.getElementById('repEnrollment').value;
        const enrollments = await apiV1Call('/portal/enrollments');
        const enrollment = (enrollments || []).find(e => e.id === enrollmentId);
        const reportMonth = document.getElementById('repMonth').value.trim();
        if (!reportMonth) { alert('Report month is required'); return; }
        try {
            await apiV1Call('/learning/reports', {
                method: 'POST',
                body: JSON.stringify({
                    student_id: enrollment ? enrollment.student_id : null,
                    enrollment_id: enrollmentId,
                    report_month: reportMonth,
                    progress_summary: document.getElementById('repSummary').value.trim() || null,
                    topics_covered: document.getElementById('repTopics').value.trim() || null,
                    staff_notes: document.getElementById('repStaffNotes').value.trim() || null,
                }),
            });
            closeModalDirect();
            renderReports();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Settings (operational config + audit)
    // ========================================
    async function renderSettings() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading settings...</div>';

        try {
            const settingsData = await apiCall('/settings');
            const auditEvents = await apiCall('/audit?limit=30');

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Settings</h1>
                        <p class="admin-header__subtitle">Operational configuration and audit trail</p>
                    </div>
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px;">
                    <div class="admin-card">
                        <div class="admin-card__body">
                            <h3 style="margin:0 0 12px;">Configuration</h3>
                            <table style="width:100%;font-size:14px;">
                                <tr><td style="padding:6px 0;color:#706B60">Timezone</td><td>${escapeHtml(settingsData.timezone)}</td></tr>
                                <tr><td style="padding:6px 0;color:#706B60">Currency</td><td>${escapeHtml(settingsData.currency)}</td></tr>
                                <tr><td style="padding:6px 0;color:#706B60">Rate limiting</td><td>${settingsData.rate_limit_enabled ? 'Enabled' : 'Disabled (dev)'}</td></tr>
                                <tr><td style="padding:6px 0;color:#706B60">Email mode</td><td>${settingsData.email_test_mode ? 'Test (Web3Forms sandbox)' : 'Live'}</td></tr>
                                <tr><td style="padding:6px 0;color:#706B60">Web3Forms configured</td><td>${settingsData.web3forms_configured ? 'Yes' : 'No'}</td></tr>
                                <tr><td style="padding:6px 0;color:#706B60">Razorpay</td><td>${settingsData.razorpay.enabled ? 'Enabled (' + escapeHtml(settingsData.razorpay.mode) + ')' : 'Disabled – manual reconciliation only'}</td></tr>
                                <tr><td style="padding:6px 0;color:#706B60">Max upload size</td><td>${settingsData.max_upload_mb} MB</td></tr>
                            </table>
                        </div>
                    </div>
                    <div class="admin-card">
                        <div class="admin-card__body">
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                                <h3 style="margin:0;">Fee Packages</h3>
                                <button class="btn btn--secondary" onclick="Admin.showPackageModal()">+ Add Package</button>
                            </div>
                            <table class="admin-table">
                                <thead><tr><th>Code</th><th>Name</th><th>Classes</th><th>Fee</th><th></th></tr></thead>
                                <tbody>
                                    ${settingsData.fee_packages.map(p => `
                                        <tr>
                                            <td><code>${escapeHtml(p.code)}</code></td>
                                            <td>${escapeHtml(p.name)}${p.is_legacy ? ' <span class="badge badge--needs-info">legacy</span>' : ''}</td>
                                            <td>${p.sessions_included}</td>
                                            <td>₹${(p.fee_paise / 100).toLocaleString('en-IN')}</td>
                                            <td><button class="btn btn--secondary" onclick="Admin.showPackageModal('${escapeHtml(p.code)}')">Edit</button></td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
                <div class="admin-card" style="margin-top:16px;">
                    <div class="admin-card__body">
                        <h3 style="margin:0 0 12px;">Recent Audit Trail</h3>
                        ${auditEvents.length > 0 ? `
                            <table class="admin-table">
                                <thead><tr><th>When</th><th>Action</th><th>Entity</th><th>Summary</th><th>Actor</th></tr></thead>
                                <tbody>
                                    ${auditEvents.map(a => `
                                        <tr>
                                            <td>${formatDateTime(a.created_at)}</td>
                                            <td><code>${escapeHtml(a.action)}</code></td>
                                            <td>${escapeHtml(a.entity_type)}${a.entity_id ? ' · ' + escapeHtml(a.entity_id) : ''}</td>
                                            <td>${escapeHtml(a.summary || '')}</td>
                                            <td>${escapeHtml(a.actor_email || a.actor_role || 'system')}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        ` : '<div class="admin-empty"><div class="admin-empty__title">No audit events recorded yet</div></div>'}
                    </div>
                </div>
            `;
        } catch (error) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load settings</div>
                    <div class="admin-empty__text">${escapeHtml(error.message)}</div>
                </div>
            `;
        }
    }

    async function showPackageModal(code) {
        let pkg = null;
        if (code) {
            const settingsData = await apiCall('/settings');
            pkg = (settingsData.fee_packages || []).find(p => p.code === code) || null;
        }
        showModal(`
            <div class="admin-modal__header">
                <h2 class="admin-modal__title">${code ? 'Edit' : 'Add'} Fee Package</h2>
            </div>
            <div class="admin-modal__body">
                <label class="form-label">Code</label>
                <input id="pkgCode" class="auth__input" value="${code ? escapeHtml(code) : ''}" ${code ? 'readonly' : ''} placeholder="e.g. standard_4" />
                <label class="form-label" style="margin-top:12px;">Name</label>
                <input id="pkgName" class="auth__input" value="${pkg ? escapeHtml(pkg.name) : ''}" />
                <label class="form-label" style="margin-top:12px;">Sessions included</label>
                <input id="pkgSessions" type="number" class="auth__input" value="${pkg ? pkg.sessions_included : 4}" min="1" />
                <label class="form-label" style="margin-top:12px;">Fee (paise)</label>
                <input id="pkgFee" type="number" class="auth__input" value="${pkg ? pkg.fee_paise : 450000}" min="1" />
                <label class="form-label" style="margin-top:12px;">Session duration (minutes)</label>
                <input id="pkgDuration" type="number" class="auth__input" value="${pkg ? pkg.session_duration_minutes : 60}" min="15" />
                <label style="display:flex;gap:8px;align-items:center;margin-top:12px;">
                    <input id="pkgLegacy" type="checkbox" ${pkg && pkg.is_legacy ? 'checked' : ''} />
                    <span>Legacy (individually agreed rate)</span>
                </label>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmPackage()">Save Package</button>
            </div>
        `);
    }

    async function confirmPackage() {
        const code = document.getElementById('pkgCode').value.trim();
        const name = document.getElementById('pkgName').value.trim();
        const sessionsIncluded = parseInt(document.getElementById('pkgSessions').value, 10);
        const feePaise = parseInt(document.getElementById('pkgFee').value, 10);
        const duration = parseInt(document.getElementById('pkgDuration').value, 10);
        const isLegacy = document.getElementById('pkgLegacy').checked;
        if (!code || !name) { alert('Code and name are required'); return; }
        try {
            await apiV1Call('/billing/packages', {
                method: 'POST',
                body: JSON.stringify({
                    code, name,
                    sessions_included: sessionsIncluded,
                    fee_paise: feePaise,
                    session_duration_minutes: duration,
                    is_legacy: isLegacy,
                }),
            });
            closeModalDirect();
            renderSettings();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Student Profile Workspace
    // ========================================
    let studentWs = {
        active: false,
        studentId: null,
        student: null,
        activeTab: 'overview',
        loading: false,
        error: null,
        data: {},
        remarkEditingId: null,
        scheduleMonth: null,
        pendingSlots: [],
        scheduleConflicts: [],
        scheduleNotice: '',
    };

    const WS_TABS = [
        { id: 'overview', label: 'Overview' },
        { id: 'profile', label: 'Profile & Enrollments' },
        { id: 'classes', label: 'Classes & Rescheduling' },
        { id: 'homework', label: 'Homework & Materials' },
        { id: 'remarks', label: 'Remarks' },
        { id: 'progress', label: 'Progress & Syllabus' },
        { id: 'reports', label: 'Monthly Reports' },
        { id: 'exams', label: 'Exams & Milestones' },
        { id: 'fees', label: 'Fees & Invoices' },
        { id: 'audit', label: 'Audit History' },
    ];

    async function openStudentWorkspace(studentId) {
        studentWs.active = true;
        studentWs.studentId = studentId;
        studentWs.student = null;
        studentWs.activeTab = 'overview';
        studentWs.data = {};
        studentWs.loading = true;
        studentWs.error = null;
        render();
        try {
            studentWs.student = await apiCall(`/students/${studentId}`);
        } catch (e) {
            studentWs.error = e.message;
        }
        studentWs.loading = false;
        render();
    }

    function closeStudentWorkspace() {
        studentWs.active = false;
        studentWs.studentId = null;
        studentWs.student = null;
        studentWs.data = {};
        render();
    }

    async function setWsTab(tab) {
        studentWs.activeTab = tab;
        studentWs.remarkEditingId = null;
        render();
        if (!studentWs.data[tab]) {
            await loadWsTab(tab);
        }
    }

    async function loadWsTab(tab) {
        const sid = studentWs.studentId;
        try {
            switch (tab) {
                case 'classes': {
                    if (!studentWs.scheduleMonth) {
                        studentWs.scheduleMonth = new Date().toISOString().slice(0, 7);
                    }
                    const [sessions, allSchedules, requests, monthly, instructors] = await Promise.all([
                        apiV1Call(`/sessions?student_id=${sid}&limit=300`),
                        apiCall('/schedules'),
                        apiV1Call(`/sessions/reschedule-requests`),
                        apiCall(`/students/${sid}/monthly-schedule?month=${studentWs.scheduleMonth}`).catch(() => null),
                        apiCall('/instructors').catch(() => []),
                    ]);
                    const todayIso = new Date().toISOString().slice(0, 10);
                    studentWs.data.classes = {
                        sessions: sessions || [],
                        schedules: (allSchedules.schedules || allSchedules || []).filter(x => x.student_id === sid),
                        requests: (requests || []).filter(r => r.student_id === sid),
                        upcoming: (sessions || []).filter(x =>
                            x.scheduled_date >= todayIso &&
                            ['scheduled', 'rescheduling_required'].includes(x.status)),
                        monthly: monthly,
                        instructors: (instructors || []).filter(i => i.is_active !== false),
                        month: studentWs.scheduleMonth,
                    };
                    break;
                }
                case 'homework': {
                    const [assignments, materials] = await Promise.all([
                        apiV1Call(`/learning/assignments?student_id=${sid}`),
                        apiV1Call(`/learning/materials?student_id=${sid}`),
                    ]);
                    studentWs.data.homework = { assignments: assignments || [], materials: materials || [] };
                    break;
                }
                case 'remarks':
                    studentWs.data.remarks = await apiV1Call(`/remarks?student_id=${sid}&include_staff_only=true`);
                    break;
                case 'progress':
                    studentWs.data.progress = await apiV1Call(`/learning/syllabus-progress?student_id=${sid}`);
                    break;
                case 'reports':
                    studentWs.data.reports = await apiV1Call(`/learning/reports?student_id=${sid}`);
                    break;
                case 'exams': {
                    const [exams, milestones] = await Promise.all([
                        apiV1Call(`/learning/exams?student_id=${sid}`),
                        apiV1Call(`/learning/milestones?student_id=${sid}`),
                    ]);
                    studentWs.data.exams = { exams: exams || [], milestones: milestones || [] };
                    break;
                }
                case 'fees': {
                    const [invoices, ledger] = await Promise.all([
                        apiV1Call(`/billing/invoices?student_id=${sid}`),
                        apiV1Call(`/billing/ledger?student_id=${sid}`),
                    ]);
                    studentWs.data.fees = { invoices: invoices || [], ledger: ledger || { entries: [], outstanding_paise: 0 } };
                    break;
                }
                case 'audit':
                    studentWs.data.audit = await apiCall(`/audit?limit=100`);
                    break;
            }
        } catch (e) {
            console.error('WS tab load error', tab, e);
        }
        render();
    }

    function renderStudentWorkspace() {
        const container = document.getElementById('adminContent');
        const s = studentWs.student;
        if (studentWs.loading) {
            container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading student profile...</div>';
            return;
        }
        if (studentWs.error || !s) {
            container.innerHTML = `
                <div class="admin-empty">
                    <div class="admin-empty__icon"> ${icon("warn")}</div>
                    <div class="admin-empty__title">Unable to load student</div>
                    <div class="admin-empty__text">${studentWs.error || 'Not found'}</div>
                    <button class="btn btn--secondary" onclick="Admin.closeStudentWorkspace()">Back to Students</button>
                </div>`;
            return;
        }

        const tabsHtml = WS_TABS.map(t => `
            <button class="ws-tab ${studentWs.activeTab === t.id ? 'ws-tab--active' : ''}"
                    onclick="Admin.setWsTab('${t.id}')">${t.label}</button>
        `).join('');

        container.innerHTML = `
            <div class="admin-header">
                <div>
                    <button class="btn btn--secondary btn--sm" onclick="Admin.closeStudentWorkspace()" style="margin-bottom:8px;">← Back to Students</button>
                    <h1 class="admin-header__title">${escapeHtml(s.full_name)}</h1>
                    <p class="admin-header__subtitle">${s.cma_registration_id}${s.login_id ? ' · Login ' + escapeHtml(s.login_id) : ''} · ${formatStatus(s.status)} · Age ${calculateAge(s.date_of_birth)}</p>
                    ${s.must_change_pin ? '<p style="font-size:0.8rem;color:var(--color-warning);margin-top:4px">⚠ Temporary PIN change pending — student must set a new PIN at next sign-in.</p>' : ''}
                </div>
                <div class="admin-actions" style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start;">
                    <button class="btn btn--secondary btn--sm" onclick="Admin.editStudentModal('${s.id}')">Edit Details</button>
                    <button class="btn btn--secondary btn--sm" onclick="Admin.resetPin('${s.id}')">Reset PIN</button>
                    ${s.status === 'active'
                        ? `<button class="btn btn--secondary btn--sm" onclick="Admin.wsSetStatus('${s.id}','suspended')">Suspend</button>`
                        : `<button class="btn btn--secondary btn--sm" onclick="Admin.wsSetStatus('${s.id}','active')">Reactivate</button>`}
                    <button class="btn btn--secondary btn--sm" onclick="Admin.archiveStudent('${s.id}')">Archive</button>
                    <button class="btn btn--secondary btn--sm" onclick="Admin.deleteStudentPermanently('${s.id}')">Delete permanently</button>
                </div>
            </div>
            <div class="ws-tabs">${tabsHtml}</div>
            <div class="admin-card"><div class="admin-card__body" id="wsTabContent">
                <div class="admin-loading"><div class="admin-loading__spinner"></div>Loading...</div>
            </div></div>
        `;

        renderWsTabContent();
    }

    function renderWsTabContent() {
        const el = document.getElementById('wsTabContent');
        if (!el) return;
        const tab = studentWs.activeTab;
        const s = studentWs.student;
        const data = studentWs.data[tab];

        if (tab === 'overview') {
            const enrollments = (s.enrollments || []);
            const guardians = (s.guardians || []);
            el.innerHTML = `
                <div class="ws-grid">
                    <div class="ws-stat"><div class="ws-stat__label">Full Name</div><div class="ws-stat__value">${escapeHtml(s.full_name)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">CMA ID</div><div class="ws-stat__value">${s.cma_registration_id}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Status</div><div class="ws-stat__value"><span class="badge badge--${s.status}">${formatStatus(s.status)}</span></div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Skill Level</div><div class="ws-stat__value">${s.skill_level || '-'}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Phone</div><div class="ws-stat__value">${s.phone || '-'}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Date of Birth</div><div class="ws-stat__value">${formatDate(s.date_of_birth)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Enrollments</div><div class="ws-stat__value">${enrollments.length}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Guardians</div><div class="ws-stat__value">${guardians.length}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Registered</div><div class="ws-stat__value">${formatDate(s.created_at)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Login ID</div><div class="ws-stat__value">${escapeHtml(s.login_id || '-')}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">PIN Security</div><div class="ws-stat__value">${s.must_change_pin ? '<span style="color:var(--color-warning)">Change pending</span>' : 'Set'}</div></div>
                </div>
            `;
            return;
        }

        if (tab === 'profile') {
            const enrollments = (s.enrollments || []);
            const guardians = (s.guardians || []);
            el.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                    <h3 style="margin:0;">Personal Information</h3>
                    <button class="btn btn--secondary btn--sm" onclick="Admin.editStudentModal('${s.id}')">Edit Details</button>
                </div>
                <div class="ws-grid" style="margin-bottom:24px;">
                    <div class="ws-stat"><div class="ws-stat__label">First Name</div><div class="ws-stat__value">${escapeHtml(s.first_name)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Last Name</div><div class="ws-stat__value">${escapeHtml(s.last_name)}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Phone</div><div class="ws-stat__value">${s.phone || '-'}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Address</div><div class="ws-stat__value">${escapeHtml(s.address) || '-'}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Profile Complete</div><div class="ws-stat__value">${s.profile_complete ? 'Yes' : 'No'}</div></div>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                    <h3 style="margin:0;">Enrollments</h3>
                    <button class="btn btn--primary btn--sm" onclick="Admin.wsAddEnrollment('${s.id}')">+ Add Enrolment</button>
                </div>
                ${enrollments.length ? `<table class="admin-table"><thead><tr><th>Programme</th><th>Fee Plan</th><th>Fee</th><th>Instructor</th><th>Status</th><th></th></tr></thead><tbody>
                    ${enrollments.map(e => `<tr>
                        <td>${escapeHtml(e.programme_name)}</td>
                        <td>${e.fee_plan ? (e.fee_plan === '4_classes' ? '4 classes (₹4,500)' : '8 classes (₹8,000)') : '<span style="color:var(--color-warning)">Not assigned</span>'}</td>
                        <td>${e.fee_amount ? '₹' + Number(e.fee_amount).toLocaleString('en-IN') : '-'}</td>
                        <td>${e.instructor_name ? escapeHtml(e.instructor_name) : '<span style="color:var(--color-warning)">Unassigned</span>'}</td>
                        <td><span class="badge badge--${e.status}">${e.status}</span></td>
                        <td style="white-space:nowrap;">
                            <button class="btn btn--secondary btn--sm" onclick="Admin.wsEditEnrollment('${e.id}')">Edit</button>
                            <button class="btn btn--secondary btn--sm" onclick="Admin.assignInstructorForEnrollment('${e.id}')">${e.instructor_name ? 'Change' : 'Assign'} Instructor</button>
                        </td>
                    </tr>`).join('')}
                </tbody></table>` : '<p class="admin-empty__text">No enrollments</p>'}
                <h3 style="margin:24px 0 12px;">Guardians</h3>
                ${guardians.length ? `<table class="admin-table"><thead><tr><th>Name</th><th>Relationship</th><th>Phone</th><th>Email</th></tr></thead><tbody>
                    ${guardians.map(g => `<tr><td>${escapeHtml(g.first_name)} ${escapeHtml(g.last_name)}</td><td>${escapeHtml(g.relationship)}</td><td>${g.phone || '-'}</td><td>${g.email || '-'}</td></tr>`).join('')}
                </tbody></table>` : '<p class="admin-empty__text">No guardians on file</p>'}
            `;
            return;
        }

        if (!data && tab !== 'overview' && tab !== 'profile') {
            el.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading tab data...</div>';
            loadWsTab(tab);
            return;
        }

        switch (tab) {
            case 'classes': renderWsClasses(el, data || []); break;
            case 'homework': renderWsHomework(el, data); break;
            case 'remarks': renderWsRemarks(el, data || []); break;
            case 'progress': renderWsProgress(el, data || []); break;
            case 'reports': renderWsReports(el, data || []); break;
            case 'exams': renderWsExams(el, data); break;
            case 'fees': renderWsFees(el, data); break;
            case 'audit': renderWsAudit(el, data || []); break;
        }
    }

    function renderWsClasses(el, data) {
        const sessions = (data && data.sessions) || [];
        const schedules = (data && data.schedules) || [];
        const requests = (data && data.requests) || [];
        const upcoming = (data && data.upcoming) || sessions || [];
        const dayLabel = d => d ? d.charAt(0).toUpperCase() + d.slice(1) : '-';

        const schedRows = schedules.map(sc => `
            <tr>
                <td>${dayLabel(sc.day_of_week)}</td>
                <td>${(sc.start_time || '').slice(0,5)}–${(sc.end_time || '').slice(0,5)}</td>
                <td>${escapeHtml(sc.instrument || '-')}</td>
                <td>${sc.instructor_name ? escapeHtml(sc.instructor_name) : '<span style="color:var(--color-warning)">Unassigned</span>'}</td>
                <td>${sc.is_active ? 'Active' : 'Inactive'}</td>
                <td><button class="btn btn--secondary btn--sm" onclick="Admin.assignInstructor('${sc.enrollment_id}','${sc.day_of_week}','${sc.start_time.slice(0,5)}','${sc.end_time.slice(0,5)}')">${sc.instructor_name ? 'Change' : 'Assign'}</button></td>
            </tr>`).join('');

        const reqRows = requests.map(r => `
            <tr>
                <td>${formatDate(r.scheduled_date)} ${(r.scheduled_start || '').slice(0,5)}</td>
                <td style="max-width:180px">${escapeHtml(r.reschedule_reason || '—')}${r.has_proposed_slot ? `<div style="font-size:0.78rem;color:var(--color-accent)">Proposed: ${escapeHtml(r.preferred_date)} ${(r.preferred_start || '').slice(0,5)}</div>` : ''}</td>
                <td>${r.replacement ? 'Moved to ' + formatDate(r.replacement.scheduled_date) : 'Awaiting decision'}</td>
                <td><button class="btn btn--primary btn--sm" onclick="Admin.approveReschedule('${r.id}')">Approve…</button>
                    <button class="btn btn--secondary btn--sm" onclick="Admin.rejectReschedule('${r.id}')">Reject</button></td>
            </tr>`).join('');

        const sessRows = sessions.map(x => `
            <tr>
                <td>${formatDate(x.scheduled_date)}</td>
                <td>${(x.scheduled_start || '').slice(0,5)}–${(x.scheduled_end || '').slice(0,5)}</td>
                <td><span class="badge badge--${getStatusBadgeClass(x.status)}">${formatStatus(x.status)}</span></td>
                <td>${escapeHtml(x.topics_covered || '-')}</td>
                <td>${x.status === 'scheduled'
                    ? `<button class="btn btn--secondary btn--sm" onclick="Admin.moveSession('${x.id}')">Move…</button>`
                    : (x.status === 'rescheduling_required' ? 'in queue' : '—')}</td>
            </tr>`).join('');

        const monthly = (data && data.monthly) || null;
        const instructors = (data && data.instructors) || [];
        const month = (studentWs.scheduleMonth || new Date().toISOString().slice(0, 7));
        const exp = monthly && monthly.plan ? monthly.plan.classes_expected : null;
        const counts = (monthly && monthly.counts) || {};
        const monthSessions = (monthly && monthly.sessions) || [];
        const remaining = monthly ? monthly.remaining : null;
        const pending = studentWs.pendingSlots || [];
        const conflicts = studentWs.scheduleConflicts || [];
        const instDefault = monthly && monthly.enrollments && monthly.enrollments.find(e => e.instructor_id);
        el.innerHTML = `
            <h3 style="margin-bottom:12px;">Monthly Schedule</h3>
            <div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin-bottom:10px;font-size:0.9rem;">
                <label>Month <input type="month" id="wsMonthInput" value="${month}" onchange="Admin.wsChangeMonth(this.value)" style="margin-left:6px"></label>
                <span>Plan: <b>${(monthly && monthly.plan && monthly.plan.label) || 'not set (4 or 8 classes)'}</b></span>
                <span>Expected: <b>${exp != null ? exp : '—'}</b></span>
                <span>Scheduled: <b>${(counts.scheduled || 0) + (counts.needs_reschedule || 0)}</b></span>
                <span>Completed: <b>${counts.completed || 0}</b></span>
                <span>Remaining: <b>${remaining != null ? remaining : '—'}</b></span>
                <button class="btn btn--secondary btn--sm" onclick="Admin.wsMonthlyReload()">Refresh</button>
            </div>
            ${monthly && monthly.existing_conflicts && monthly.existing_conflicts.length
                ? `<div style="color:var(--color-warning);font-size:0.85rem;margin-bottom:8px">${monthly.existing_conflicts.map(c => '⚠ ' + escapeHtml(c.message)).join('<br>')}</div>` : ''}
            ${monthSessions.length ? `<table class="admin-table" style="margin-bottom:14px"><thead><tr><th>Date</th><th>Time</th><th>Status</th><th>Counts</th></tr></thead><tbody>
                ${monthSessions.map(x => `<tr style="${x.status === 'completed' ? 'opacity:0.65' : ''}">
                    <td>${formatDate(x.date)}</td><td>${(x.start || '').slice(0,5)}–${(x.end || '').slice(0,5)}</td>
                    <td><span class="badge badge--${getStatusBadgeClass(x.status)}">${formatStatus(x.status)}</span></td>
                    <td>${x.counts ? '✓' : '—'}</td></tr>`).join('')}
                </tbody></table>`
                : '<p class="admin-empty__text" style="margin-bottom:10px">No classes scheduled for this month yet</p>'}
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0">
                <label>Instructor
                    <select id="wsInstSelect" style="margin-left:6px">
                        ${instructors.map(i => `<option value="${i.id}" ${instDefault && instDefault.instructor_id === i.id ? 'selected' : ''}>${escapeHtml(i.full_name || i.first_name || i.username || i.id)}</option>`).join('')}
                    </select>
                </label>
                <button class="btn btn--secondary btn--sm" onclick="Admin.wsAddSlot()">+ Add class slot</button>
                <span style="display:inline-flex;gap:6px;align-items:center">
                    <select id="wsGenDay">${['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map((d, ix) => `<option value="${ix}">${d.charAt(0).toUpperCase()+d.slice(1)}</option>`).join('')}</select>
                    <input type="time" id="wsGenStart" value="17:00">
                    <input type="time" id="wsGenEnd" value="18:00">
                    <button class="btn btn--secondary btn--sm" onclick="Admin.wsGenerateWeekly()">Generate remaining (weekly)</button>
                </span>
            </div>
            ${pending.length ? `<table class="admin-table" id="wsPendingTable" style="margin-bottom:10px"><thead><tr><th>Date</th><th>Start</th><th>End</th><th></th></tr></thead><tbody>
                ${pending.map((p, ix) => `<tr>
                    <td><input type="date" data-slot-date value="${p.date || ''}"></td>
                    <td><input type="time" data-slot-start value="${p.start || ''}"></td>
                    <td><input type="time" data-slot-end value="${p.end || ''}"></td>
                    <td><button class="btn btn--secondary btn--sm" onclick="Admin.wsRemoveSlot(${ix})">Remove</button></td>
                </tr>`).join('')}
                </tbody></table>`
                : ''}
            ${conflicts.length ? `<div style="border:1px solid var(--color-warning);border-radius:8px;padding:10px;margin-bottom:10px;color:var(--color-warning);font-size:0.85rem">
                <b>Scheduling conflicts — nothing was saved:</b><br>${conflicts.map(c => '• ' + escapeHtml(c.message)).join('<br>')}</div>` : ''}
            ${studentWs.scheduleNotice ? `<div style="color:var(--color-success, #2E7D32);font-size:0.85rem;margin-bottom:10px">${escapeHtml(studentWs.scheduleNotice)}</div>` : ''}
            <div style="margin-bottom:22px">
                <button class="btn btn--primary btn--sm" onclick="Admin.wsSaveMonthly()">Save schedule</button>
                <span style="font-size:0.78rem;color:var(--color-text-muted,#706B60);margin-left:8px">Conflicting slots block saving; completed classes are never changed.</span>
            </div>
            <h3 style="margin-bottom:12px;">Change Recurring Schedule</h3>
            <p style="font-size:0.8rem;color:var(--color-text-muted);margin-bottom:10px">
                Move an ongoing weekly class (e.g. Saturday → Sunday, or a holiday time change).
                Preview checks instructor availability, overlapping intervals and travel time between
                offline classes before anything is saved. Completed classes and history are never changed.</p>
            <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px">
                <label>New day
                    <select id="scDay" style="margin-left:6px" onchange="Admin.wsScInvalidate()">
                        ${['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(d => `<option value="${d}" ${d === 'saturday' ? 'selected' : ''}>${d.charAt(0).toUpperCase()+d.slice(1)}</option>`).join('')}
                    </select></label>
                <label>Start <input type="time" id="scStart" value="16:30" onchange="Admin.wsScInvalidate()" style="margin-left:4px"></label>
                <label>End <input type="time" id="scEnd" value="17:30" onchange="Admin.wsScInvalidate()" style="margin-left:4px"></label>
                <label>Effective from <input type="date" id="scEff" onchange="Admin.wsScInvalidate()" style="margin-left:4px"></label>
                <label>Reason <input id="scNote" placeholder="e.g. school-holiday timing" style="margin-left:4px;width:180px"></label>
                <button class="btn btn--secondary btn--sm" onclick="Admin.wsScPreview()">Preview changes</button>
                <button class="btn btn--primary btn--sm" id="scApplyBtn" disabled onclick="Admin.wsScApply()">Confirm &amp; apply</button>
            </div>
            <div id="scPreviewArea" style="margin-bottom:22px"></div>
            <h3 style="margin-bottom:12px;">Fixed Weekly Timetable</h3>
            ${schedules.length ? `<table class="admin-table"><thead><tr><th>Day</th><th>Time</th><th>Instrument</th><th>Instructor</th><th>Status</th><th></th></tr></thead>
                <tbody>${schedRows}</tbody></table>`
                : '<p class="admin-empty__text">No recurring schedule recorded for this student</p>'}
            <h3 style="margin:24px 0 12px;">Upcoming Dated Sessions (${upcoming.length})</h3>
            ${upcoming.length ? `<table class="admin-table"><thead><tr><th>Date</th><th>Time</th><th>Status</th><th>Topics</th><th></th></tr></thead>
                <tbody>${upcoming.map(x => `
                <tr>
                    <td>${formatDate(x.scheduled_date)}</td>
                    <td>${(x.scheduled_start || '').slice(0,5)}–${(x.scheduled_end || '').slice(0,5)}</td>
                    <td><span class="badge badge--${getStatusBadgeClass(x.status)}">${formatStatus(x.status)}</span></td>
                    <td>${escapeHtml(x.topics_covered || '-')}</td>
                    <td>${x.status === 'scheduled'
                        ? `<button class="btn btn--secondary btn--sm" onclick="Admin.moveSession('${x.id}')">Move…</button>`
                        : 'in queue'}</td>
                </tr>`).join('')}</tbody></table>`
                : '<p class="admin-empty__text">No upcoming dated sessions</p>'}
            <h3 style="margin:24px 0 12px;">Pending Reschedule Requests (${requests.length})</h3>
            ${requests.length ? `<table class="admin-table"><thead><tr><th>Class</th><th>Reason / proposal</th><th>Status</th><th></th></tr></thead>
                <tbody>${reqRows}</tbody></table>`
                : '<p class="admin-empty__text">No pending reschedule requests</p>'}
            <h3 style="margin:24px 0 12px;">Class History (${sessions.length})</h3>
            ${sessions.length ? `<table class="admin-table"><thead><tr><th>Date</th><th>Time</th><th>Status</th><th>Topics</th><th></th></tr></thead>
                <tbody>${sessRows}</tbody></table>`
                : '<p class="admin-empty__text">No class records yet</p>'}
        `;
    }

    function renderWsHomework(el, data) {
        const assignments = data.assignments || [];
        const materials = data.materials || [];
        el.innerHTML = `
            <h3 style="margin-bottom:12px;">Assignments</h3>
            ${assignments.length ? `<table class="admin-table"><thead><tr><th>Title</th><th>Due</th><th>Priority</th><th>Status</th><th>Submission</th></tr></thead><tbody>
                ${assignments.map(a => `<tr>
                    <td>${escapeHtml(a.title)}</td>
                    <td>${formatDate(a.due_date)}</td>
                    <td>${a.priority || '-'}</td>
                    <td><span class="badge badge--${a.status}">${a.status}</span></td>
                    <td>${a.submission ? formatDate(a.submission.submitted_at) : '—'}</td>
                </tr>`).join('')}
            </tbody></table>` : '<p class="admin-empty__text">No assignments</p>'}
            <h3 style="margin:24px 0 12px;">Study Materials</h3>
            ${materials.length ? `<table class="admin-table"><thead><tr><th>Title</th><th>Category</th><th>Type</th></tr></thead><tbody>
                ${materials.map(m => `<tr><td>${escapeHtml(m.title)}</td><td>${m.category || '-'}</td><td>${m.material_type || '-'}</td></tr>`).join('')}
            </tbody></table>` : '<p class="admin-empty__text">No materials assigned</p>'}
        `;
    }

    function renderWsRemarks(el, remarks) {
        el.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h3>Remarks (${remarks.length})</h3>
                <button class="btn btn--primary btn--sm" onclick="Admin.showRemarkModal()">+ Add Remark</button>
            </div>
            ${remarks.length ? remarks.map(r => `
                <div class="ws-remark ${r.visibility === 'staff_only' ? 'ws-remark--staff' : ''}">
                    <div class="ws-remark__meta">
                        <span class="badge badge--${r.visibility === 'staff_only' ? 'rejected' : r.visibility === 'parent_visible' ? 'accent' : 'approved'}">${formatStatus(r.visibility)}</span>
                        <span style="color:#706B60;font-size:12px;">${r.author_role} · ${formatDateTime(r.created_at)}${r.updated_at && r.updated_at !== r.created_at ? ' · edited ' + formatDateTime(r.updated_at) : ''}</span>
                    </div>
                    <div class="ws-remark__body">${escapeHtml(r.body)}</div>
                    <div class="ws-remark__actions">
                        <button class="btn btn--secondary btn--sm" onclick="Admin.showRemarkModal('${r.id}')">Edit</button>
                        <button class="btn btn--secondary btn--sm" onclick="Admin.showRemarkHistory('${r.id}')">History</button>
                    </div>
                </div>
            `).join('') : '<p class="admin-empty__text">No remarks yet</p>'}
        `;
    }

    async function showRemarkModal(remarkId) {
        const sid = studentWs.studentId;
        let existing = null;
        if (remarkId) {
            const list = studentWs.data.remarks || [];
            existing = list.find(r => r.id === remarkId);
        }
        studentWs.remarkEditingId = remarkId || null;
        showModal(`
            <div class="admin-modal__header">
                <h2 class="admin-modal__title">${existing ? 'Edit Remark' : 'Add Remark'}</h2>
            </div>
            <div class="admin-modal__body">
                <label class="form-label">Visibility</label>
                <select id="rmkVisibility" class="auth__input">
                    <option value="student_visible" ${existing && existing.visibility === 'student_visible' ? 'selected' : (!existing ? 'selected' : '')}>Student visible</option>
                    <option value="parent_visible" ${existing && existing.visibility === 'parent_visible' ? 'selected' : ''}>Parent visible</option>
                    <option value="staff_only" ${existing && existing.visibility === 'staff_only' ? 'selected' : ''}>Staff only (never shown to family)</option>
                </select>
                <label class="form-label" style="margin-top:12px;">Remark</label>
                <textarea id="rmkBody" class="auth__input auth__textarea" rows="4" maxlength="5000" placeholder="Enter remark...">${existing ? escapeHtml(existing.body) : ''}</textarea>
                <div id="rmkError" style="color:#E84141;font-size:13px;margin-top:8px;"></div>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmRemark()">${existing ? 'Save Changes' : 'Create Remark'}</button>
            </div>
        `);
    }

    async function confirmRemark() {
        const sid = studentWs.studentId;
        const visibility = document.getElementById('rmkVisibility').value;
        const body = document.getElementById('rmkBody').value.trim();
        const errEl = document.getElementById('rmkError');
        if (!body) { errEl.textContent = 'Remark body is required'; return; }
        if (body.length > 5000) { errEl.textContent = 'Remark too long (max 5000 characters)'; return; }
        try {
            if (studentWs.remarkEditingId) {
                await apiV1Call(`/remarks/${studentWs.remarkEditingId}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ visibility, body }),
                });
            } else {
                await apiV1Call('/remarks', {
                    method: 'POST',
                    body: JSON.stringify({ student_id: sid, visibility, body }),
                });
            }
            closeModalDirect();
            studentWs.data.remarks = await apiV1Call(`/remarks?student_id=${sid}&include_staff_only=true`);
            renderWsTabContent();
        } catch (e) {
            errEl.textContent = e.message;
        }
    }

    async function showRemarkHistory(remarkId) {
        try {
            const history = await apiV1Call(`/remarks/${remarkId}/history`);
            showModal(`
                <div class="admin-modal__header">
                    <h2 class="admin-modal__title">Remark Audit History</h2>
                </div>
                <div class="admin-modal__body">
                    ${(history || []).length ? history.map(h => `
                        <div style="border-left:3px solid #B58A35;padding-left:12px;margin-bottom:16px;">
                            <div style="font-weight:600;">${h.action}</div>
                            <div style="font-size:12px;color:#706B60;">${h.actor_role} · ${formatDateTime(h.created_at)}</div>
                            ${h.summary ? `<div style="font-size:13px;margin-top:4px;">${escapeHtml(h.summary)}</div>` : ''}
                            ${h.after_data && h.after_data.body ? `<div style="font-size:13px;margin-top:4px;color:#706B60;">“${escapeHtml(h.after_data.body).substring(0, 120)}${h.after_data.body.length > 120 ? '…' : ''}”</div>` : ''}
                        </div>
                    `).join('') : '<p class="admin-empty__text">No history entries</p>'}
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Close</button>
                </div>
            `);
        } catch (e) { alert(e.message); }
    }

    function renderWsProgress(el, items) {
        if (!items.length) { el.innerHTML = '<div class="admin-empty__text">No syllabus progress recorded</div>'; return; }
        el.innerHTML = `
            <table class="admin-table"><thead><tr><th>Syllabus</th><th>Item</th><th>Status</th><th>Faculty Notes</th><th>Updated</th></tr></thead>
            <tbody>${items.map(p => `
                <tr>
                    <td>${escapeHtml(p.syllabus_title || '-')}</td>
                    <td>${escapeHtml(p.item_title || p.item_id)}</td>
                    <td><span class="badge badge--${getStatusBadgeClass(p.status)}">${formatStatus(p.status)}</span></td>
                    <td>${escapeHtml(p.faculty_notes) || '-'}</td>
                    <td>${formatDateTime(p.updated_at)}</td>
                </tr>`).join('')}
            </tbody></table>`;
    }

    function renderWsReports(el, reports) {
        if (!reports.length) { el.innerHTML = '<div class="admin-empty__text">No reports</div>'; return; }
        el.innerHTML = `
            <table class="admin-table"><thead><tr><th>Month</th><th>Rev</th><th>Status</th><th>Progress Summary</th><th>Published</th></tr></thead>
            <tbody>${reports.map(r => `
                <tr>
                    <td>${r.report_month}</td>
                    <td>${r.revision}</td>
                    <td><span class="badge badge--${r.status === 'published' ? 'approved' : 'pending'}">${r.status}</span></td>
                    <td>${escapeHtml(r.progress_summary) || '-'}</td>
                    <td>${r.published_at ? formatDateTime(r.published_at) : '—'}</td>
                </tr>`).join('')}
            </tbody></table>`;
    }

    function renderWsExams(el, data) {
        const exams = data.exams || [];
        const milestones = data.milestones || [];
        el.innerHTML = `
            <h3 style="margin-bottom:12px;">Exams</h3>
            ${exams.length ? `<table class="admin-table"><thead><tr><th>Board</th><th>Instrument</th><th>Grade</th><th>Application</th><th>Readiness</th><th>Result</th></tr></thead><tbody>
                ${exams.map(x => `<tr>
                    <td>${escapeHtml(x.board)}</td><td>${escapeHtml(x.instrument)}</td><td>${x.grade || '-'}</td>
                    <td><span class="badge badge--${x.application_status}">${x.application_status}</span></td>
                    <td>${x.readiness || '-'}</td><td>${x.result || '-'}</td>
                </tr>`).join('')}
            </tbody></table>` : '<p class="admin-empty__text">No exams</p>'}
            <h3 style="margin:24px 0 12px;">Milestones</h3>
            ${milestones.length ? `<table class="admin-table"><thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Due</th><th>Achieved</th></tr></thead><tbody>
                ${milestones.map(m => `<tr>
                    <td>${escapeHtml(m.title)}</td><td>${m.milestone_type || '-'}</td>
                    <td><span class="badge badge--${m.status === 'achieved' ? 'approved' : 'pending'}">${m.status}</span></td>
                    <td>${formatDate(m.due_date)}</td><td>${m.achieved_at ? formatDateTime(m.achieved_at) : '—'}</td>
                </tr>`).join('')}
            </tbody></table>` : '<p class="admin-empty__text">No milestones</p>'}
        `;
    }

    function renderWsFees(el, data) {
        const invoices = data.invoices || [];
        const outstanding = data.ledger ? data.ledger.outstanding_paise : 0;
        el.innerHTML = `
            <div class="ws-grid" style="margin-bottom:16px;">
                <div class="ws-stat"><div class="ws-stat__label">Outstanding</div><div class="ws-stat__value">₹${(outstanding / 100).toFixed(0)}</div></div>
                <div class="ws-stat"><div class="ws-stat__label">Invoices</div><div class="ws-stat__value">${invoices.length}</div></div>
            </div>
            ${invoices.length ? `<table class="admin-table"><thead><tr><th>Invoice #</th><th>Month</th><th>Amount</th><th>Paid</th><th>Status</th></tr></thead><tbody>
                ${invoices.map(i => `<tr>
                    <td>${i.invoice_number}</td><td>${i.billing_month}</td>
                    <td>₹${(i.amount_paise / 100).toFixed(0)}</td><td>₹${(i.amount_paid_paise / 100).toFixed(0)}</td>
                    <td><span class="badge badge--${i.status === 'paid' ? 'approved' : i.status === 'partially_paid' ? 'needs-info' : 'pending'}">${i.status}</span></td>
                </tr>`).join('')}
            </tbody></table>` : '<p class="admin-empty__text">No invoices</p>'}
        `;
    }

    function renderWsAudit(el, events) {
        if (!events.length) { el.innerHTML = '<div class="admin-empty__text">No audit events</div>'; return; }
        el.innerHTML = `
            <table class="admin-table"><thead><tr><th>When</th><th>Action</th><th>Entity</th><th>Actor</th><th>Summary</th></tr></thead>
            <tbody>${events.slice(0, 100).map(e => `
                <tr>
                    <td>${formatDateTime(e.created_at)}</td>
                    <td>${e.action}</td>
                    <td>${e.entity_type}</td>
                    <td>${e.actor_email || e.actor_role || '-'}</td>
                    <td>${escapeHtml(e.summary) || '-'}</td>
                </tr>`).join('')}
            </tbody></table>`;
    }

    // ========================================
    // Utility Functions
    // ========================================
    function formatStatus(status) {
        const map = {
            'pending_email_verification': 'Pending Email Verification',
            'email_verified': 'Email Verified',
            'pending_review': 'Pending Approval',
            'needs_information': 'Needs Information',
            'approved': 'Approved',
            'rejected': 'Rejected',
            'active': 'Active',
            'inactive': 'Inactive',
            'paid': 'Paid',
            'pending': 'Pending',
            'partial': 'Partially Paid',
            'scheduled': 'Scheduled',
            'completed': 'Completed',
            'rescheduled': 'Rescheduled',
            'rescheduling_required': 'Reschedule Pending',
            'absent': 'Absent',
            'draft': 'Draft',
            'submitted': 'Submitted for Review',
            'published': 'Approved & Published',
            'cancelled': 'Cancelled',
            'waiting_payment': 'Waiting for Payment',
            'upcoming': 'Upcoming',
            'achieved': 'Achieved',
            'not_assessed': 'Not Assessed',
            'developing': 'Developing',
            'ready': 'Ready',
            'exam_ready': 'Exam Ready',
            'not_started': 'Not Started',
            'preparing': 'Preparing',
            'applied': 'Applied',
            'confirmed': 'Confirmed',
            'book': 'Book',
            'instrument': 'Instrument',
            'accessory': 'Accessory',
            'stand_notebook': 'Stand / Notebook',
            'metronome_tuner': 'Metronome / Tuner',
            'online_link': 'Online Link',
        };
        return map[status] || status;
    }

    function getStatusBadgeClass(status) {
        const map = {
            'pending_email_verification': 'pending',
            'email_verified': 'accent',
            'pending_review': 'pending',
            'needs_information': 'needs-info',
            'approved': 'approved',
            'rejected': 'rejected',
            'active': 'active',
            'inactive': 'inactive',
            'paid': 'paid',
            'completed': 'approved',
            'submitted': 'needs-info',
            'rescheduled': 'needs-info',
            'scheduled': 'accent',
            'rescheduling_required': 'rejected',
            'cancelled': 'inactive',
            'partial': 'needs-info',
            'pending': 'pending',
            'upcoming': 'pending',
            'achieved': 'approved',
            'not_assessed': 'pending',
            'developing': 'needs-info',
            'ready': 'accent',
            'exam_ready': 'approved',
            'not_started': 'pending',
            'preparing': 'needs-info',
            'applied': 'accent',
            'confirmed': 'approved',
        };
        return map[status] || 'pending';
    }

    function formatDate(dateStr) {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        });
    }

    function formatDateTime(dateStr) {
        if (!dateStr) return '-';
        return new Date(dateStr).toLocaleDateString('en-IN', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    function calculateAge(dob) {
        if (!dob) return '-';
        const today = new Date();
        const birth = new Date(dob);
        let age = today.getFullYear() - birth.getFullYear();
        const m = today.getMonth() - birth.getMonth();
        if (m < 0 || (m === 0 && today.getDate() < birth.getDate())) age--;
        return age;
    }

    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ========================================
    // Reschedule Requests queue (admin approves/rejects)
    // ========================================
    // 24-hour rescheduling notice policy — same wording as the portals
    const RESCHEDULE_POLICY_TEXT = 'Rescheduling requests must be made at least 24 hours before the class ' +
        'start time. Inside 24 hours, please contact the academy directly.';

    function hoursUntilSession(s) {
        const startMs = Date.parse(s.scheduled_date + 'T' + s.scheduled_start + ':00+05:30');
        return (startMs - Date.now()) / 3600000;
    }

    async function renderRescheduleQueue() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading reschedule requests...</div>';
        try {
            const reqs = await apiV1Call('/sessions/reschedule-requests');
            const rows = reqs.map(r => `
                <tr>
                    <td><strong>${escapeHtml(r.student_name || '-')}</strong><div style="font-size:0.75rem;color:var(--color-text-muted)">${escapeHtml(r.student_cma || '')}</div></td>
                    <td>${escapeHtml(r.programme || '-')}</td>
                    <td>${formatDate(r.scheduled_date)}<div style="font-size:0.75rem;color:var(--color-text-muted)">${(r.scheduled_start || '').slice(0,5)}–${(r.scheduled_end || '').slice(0,5)}</div></td>
                    <td>${escapeHtml(r.instructor_name || 'Not assigned')}</td>
                    <td style="max-width:220px">${escapeHtml(r.reschedule_reason || '—')}${r.has_proposed_slot ? `<div style="margin-top:4px;font-size:0.78rem;color:var(--color-accent)">Proposed: ${escapeHtml(r.preferred_date)} ${(r.preferred_start || '').slice(0,5)}${r.preferred_end ? '–' + r.preferred_end.slice(0,5) : ''}</div>` : ''}</td>
                    <td><button class="btn btn--primary btn--sm" onclick="Admin.approveReschedule('${r.id}')">Approve…</button>
                        <button class="btn btn--secondary btn--sm" onclick="Admin.rejectReschedule('${r.id}')">Reject</button></td>
                </tr>`).join('');
            container.innerHTML = `
                <div class="admin-header"><div>
                    <h1 class="admin-header__title">Reschedule Requests</h1>
                    <p class="admin-header__subtitle">Student &amp; faculty proposals — you approve or reject each change</p>
                </div></div>
                <div class="admin-card" style="margin-bottom:12px"><div class="admin-card__body" style="padding:12px 16px;font-size:0.85rem;color:var(--color-text-secondary)">
                    ${escapeHtml(RESCHEDULE_POLICY_TEXT)} These requests were submitted in time and can be approved normally.
                    A change inside 24 hours of the class must go through the administrator exception workflow
                    (Move class &rarr; policy exception, with a recorded reason).
                </div></div>
                <div class="admin-card"><div class="admin-card__body" style="padding:0">
                ${reqs.length ? `<table class="admin-table"><thead><tr>
                    <th>Student</th><th>Instrument</th><th>Original class</th><th>Instructor</th><th>Reason / proposal</th><th></th>
                </tr></thead><tbody>${rows}</tbody></table>` : `
                    <div class="admin-empty">
                        <div class="admin-empty__icon">${icon("clock")}</div>
                        <div class="admin-empty__title">No reschedule requests</div>
                        <div class="admin-empty__text">Student and faculty requests will appear here</div>
                    </div>`}
                </div></div>`;
        } catch (e) {
            container.innerHTML = `<div class="admin-empty"><div class="admin-empty__icon">${icon("warn")}</div><div class="admin-empty__title">Unable to load reschedule requests</div><div class="admin-empty__text">${escapeHtml(e.message)}</div></div>`;
        }
    }

    function approveReschedule(id) {
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Approve Reschedule</h3></div>
            <div class="admin-modal__body">
                <p>Move this single class to a new slot. The recurring weekly timetable is never changed.</p>
                <div class="admin-modal__field"><label class="auth__label">New date</label>
                    <input class="auth__input" type="date" id="rsNewDate"></div>
                <div class="admin-modal__field"><label class="auth__label">New start</label>
                    <input class="auth__input" type="time" id="rsNewStart"></div>
                <div class="admin-modal__field"><label class="auth__label">New end</label>
                    <input class="auth__input" type="time" id="rsNewEnd"></div>
                <div class="admin-modal__field"><label class="auth__label">Notes (recorded in history)</label>
                    <textarea class="auth__input" id="rsReason" rows="2">Approved by academy</textarea></div>
                <p id="rsError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" id="rsConfirmBtn" onclick="Admin.confirmApproveReschedule('${id}')">Confirm &amp; Move Class</button>
            </div>
        `);
    }

    async function confirmApproveReschedule(id) {
        const err = document.getElementById('rsError');
        const btn = document.getElementById('rsConfirmBtn');
        const isException = window.__rsExceptionId === id;
        const reasonRaw = ((document.getElementById('rsReason') || {}).value || '').trim();
        const payload = {
            new_date: (document.getElementById('rsNewDate') || {}).value,
            new_start: (document.getElementById('rsNewStart') || {}).value,
            new_end: (document.getElementById('rsNewEnd') || {}).value,
            reason: reasonRaw || 'Approved by academy',
        };
        if (!payload.new_date || !payload.new_start || !payload.new_end) {
            err.textContent = 'New date, start and end are required.';
            err.style.display = 'block';
            return;
        }
        if (isException) {
            if (reasonRaw.length < 8) {
                err.textContent = 'A policy exception requires a clear reason (at least 8 characters).';
                err.style.display = 'block';
                return;
            }
            payload.reason = reasonRaw;
        }
        try {
            btn.disabled = true; btn.textContent = 'Saving…';
            const path = isException ? `/sessions/${id}/reschedule-exception` : `/sessions/${id}/reschedule`;
            await apiV1Call(path, { method: 'POST', body: JSON.stringify(payload) });
            window.__rsExceptionId = null;
            closeModalDirect();
            showToast(isException
                ? 'Class moved under the late-change exception — recorded in the audit trail.'
                : 'Class rescheduled — student and instructor notified.', 'success');
            renderRescheduleQueue();
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
            btn.disabled = false;
            btn.textContent = isException ? 'Record Exception & Move Class' : 'Confirm & Move Class';
        }
    }

    function rejectReschedule(id) {
        showModal(`
            <div class="admin-modal__header admin-modal__header--danger"><h3 class="admin-modal__title">Reject Reschedule</h3></div>
            <div class="admin-modal__body">
                <p>The class stays at its original date and time. The requester will be notified.</p>
                <div class="admin-modal__field"><label class="auth__label">Reason (required)</label>
                    <textarea class="auth__input" id="rjReason" rows="3"></textarea></div>
                <p id="rjError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" id="rjConfirmBtn" onclick="Admin.confirmRejectReschedule('${id}')">Reject Request</button>
            </div>
        `);
    }

    async function confirmRejectReschedule(id) {
        const err = document.getElementById('rjError');
        const reason = (document.getElementById('rjReason') || {}).value || '';
        if (!reason.trim()) {
            err.textContent = 'A reason is required.';
            err.style.display = 'block';
            return;
        }
        try {
            await apiV1Call(`/sessions/${id}/reject-reschedule`, { method: 'POST', body: JSON.stringify({ reason: reason.trim() }) });
            closeModalDirect();
            showToast('Request rejected — class unchanged.', 'success');
            renderRescheduleQueue();
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
        }
    }

    // ========================================
    // PIN Reset Requests queue
    // ========================================
    async function renderPinResets() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading PIN reset requests...</div>';
        try {
            const reqs = await apiCall('/pin-reset-requests');
            const rows = reqs.map(r => `
                <tr>
                    <td><strong>${escapeHtml(r.request_id)}</strong></td>
                    <td>${escapeHtml(r.account_name || '—')}<div style="font-size:0.75rem;color:var(--color-text-muted)">${escapeHtml(r.account_login_id || r.username_submitted)}</div></td>
                    <td>${escapeHtml(r.contact || '—')}</td>
                    <td style="max-width:240px">${escapeHtml(r.details || '—')}</td>
                    <td>${formatDate(r.created_at)}</td>
                    <td><span class="badge badge--${r.status === 'pending' ? 'pending' : r.status === 'approved' ? 'approved' : 'rejected'}">${escapeHtml(r.status)}</span></td>
                    <td style="white-space:nowrap">
                    ${r.status === 'pending' ? `
                        <button class="btn btn--primary btn--sm" onclick="Admin.approvePinReset('${r.id}')">Issue temp PIN</button>
                        <button class="btn btn--secondary btn--sm" onclick="Admin.rejectPinReset('${r.id}')">Reject</button>
                    ` : `<span style="font-size:0.78rem;color:var(--color-text-muted)">${escapeHtml(r.review_notes || '')}</span>`}
                    </td>
                </tr>`).join('');
            container.innerHTML = `
                <div class="admin-header"><div>
                    <h1 class="admin-header__title">PIN Reset Requests</h1>
                    <p class="admin-header__subtitle">Admin-managed PIN recovery — temporary PINs are issued in person, never emailed</p>
                </div></div>
                <div class="admin-card"><div class="admin-card__body" style="padding:0">
                ${reqs.length ? `<table class="admin-table"><thead><tr>
                    <th>Request</th><th>Student</th><th>Contact</th><th>Details</th><th>Requested</th><th>Status</th><th></th>
                </tr></thead><tbody>${rows}</tbody></table>` : `
                    <div class="admin-empty">
                        <div class="admin-empty__icon">${icon("key")}</div>
                        <div class="admin-empty__title">No PIN reset requests</div>
                        <div class="admin-empty__text">Requests from students who forgot their PIN appear here</div>
                    </div>`}
                </div></div>`;
        } catch (e) {
            container.innerHTML = `<div class="admin-empty"><div class="admin-empty__icon">${icon("warn")}</div><div class="admin-empty__title">Unable to load PIN reset requests</div><div class="admin-empty__text">${escapeHtml(e.message)}</div></div>`;
        }
    }

    async function approvePinReset(id) {
        try {
            const res = await apiCall(`/pin-reset-requests/${id}/approve`, { method: 'POST' });
            showModal(`
                <div class="admin-modal__header admin-modal__header--warning">
                    <h3 class="admin-modal__title">Temporary PIN issued</h3>
                </div>
                <div class="admin-modal__body">
                    <p>Login ID: <strong>${escapeHtml(res.login_id)}</strong></p>
                    <p style="font-size:2rem;font-weight:700;letter-spacing:0.35em;text-align:center;margin:16px 0;
                              padding:14px;background:rgba(201,169,110,0.12);border-radius:10px;">${escapeHtml(res.new_pin)}</p>
                    <p style="color:var(--color-error);font-size:0.85rem;">
                        Shown once only — share it privately. Stored as a hash; the student must
                        choose a new PIN at their next sign-in.</p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--primary" onclick="Admin.closeModalDirect();Admin.renderPinResets()">Done</button>
                </div>
            `);
        } catch (e) {
            showToast('Failed: ' + e.message, 'error');
        }
    }

    function rejectPinReset(id) {
        showModal(`
            <div class="admin-modal__header admin-modal__header--danger"><h3 class="admin-modal__title">Reject PIN Request</h3></div>
            <div class="admin-modal__body">
                <div class="admin-modal__field"><label class="auth__label">Reason (required)</label>
                    <textarea class="auth__input" id="prReason" rows="3"></textarea></div>
                <p id="prError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmRejectPinReset('${id}')">Reject</button>
            </div>
        `);
    }

    async function confirmRejectPinReset(id) {
        const err = document.getElementById('prError');
        const reason = (document.getElementById('prReason') || {}).value || '';
        if (!reason.trim()) {
            err.textContent = 'A reason is required.';
            err.style.display = 'block';
            return;
        }
        try {
            await apiCall(`/pin-reset-requests/${id}/reject`, { method: 'POST', body: JSON.stringify({ notes: reason.trim() }) });
            closeModalDirect();
            showToast('Request rejected.', 'success');
            renderPinResets();
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
        }
    }

    async function provisionStudent(id) {
        try {
            const res = await apiCall(`/registration-requests/${id}/provision`, { method: 'POST' });
            closeModalDirect();
            showModal(`
                <div class="admin-modal__header admin-modal__header--success">
                    <h3 class="admin-modal__title">Student provisioned</h3>
                </div>
                <div class="admin-modal__body">
                    <p>Student: <strong>${escapeHtml(res.full_name)}</strong></p>
                    <p>Login ID / Roll No.: <strong>${escapeHtml(res.login_id)}</strong></p>
                    <p>CMA Registration ID: <strong>${escapeHtml(res.cma_registration_id)}</strong></p>
                    <p style="font-size:2rem;font-weight:700;letter-spacing:0.35em;text-align:center;margin:16px 0;
                              padding:14px;background:rgba(201,169,110,0.12);border-radius:10px;">${escapeHtml(res.temp_pin)}</p>
                    <p style="color:var(--color-error);font-size:0.85rem;">
                        Temporary PIN shown once only. Enrolments: ${escapeHtml((res.enrolments || []).join(', ') || 'none')}.
                        The student must choose a new PIN at first sign-in.</p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--primary" onclick="Admin.closeModalDirect()">Done</button>
                </div>
            `);
        } catch (e) {
            showToast('Failed: ' + e.message, 'error');
        }
    }

    // ========================================
    // Student account management
    // ========================================
    function createStudentModal() {
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Add Student</h3></div>
            <div class="admin-modal__body">
                <div class="admin-modal__field"><label class="auth__label">Login ID (auto-generated)</label>
                    <input class="auth__input" id="nsUserPreview" readonly tabindex="-1"
                        style="background:rgba(255,255,255,0.04);color:var(--color-text-muted)"
                        value="(auto from generated roll)">
                    <p style="font-size:0.75rem;color:var(--color-text-muted);margin-top:4px">
                        Derived from the CMA Roll Number — rule: <code>CMA-2026-0015 → CMA-015</code>. The Login ID stays with the account.</p></div>
                <div class="admin-modal__field"><label class="auth__label">CMA Roll Number (auto if blank)</label>
                    <input class="auth__input" id="nsCma" placeholder="CMA-2026-0015" oninput="Admin.previewLoginId()"></div>
                <div class="admin-modal__field"><label class="auth__label">First name *</label>
                    <input class="auth__input" id="nsFirst"></div>
                <div class="admin-modal__field"><label class="auth__label">Last name</label>
                    <input class="auth__input" id="nsLast"></div>
                <div class="admin-modal__field"><label class="auth__label">Phone</label>
                    <input class="auth__input" id="nsPhone"></div>
                <div class="admin-modal__field"><label class="auth__label">Date of birth</label>
                    <input class="auth__input" type="date" id="nsDob"></div>
                <div class="admin-modal__field"><label class="auth__label">Instrument / programme</label>
                    <input class="auth__input" id="nsProgramme" placeholder="e.g. Piano"></div>
                <div class="admin-modal__field"><label class="auth__label">Monthly package</label>
                    <select class="auth__input" id="nsFee">
                        <option value="">Not assigned</option>
                        <option value="4_classes">4 classes — ₹4,500</option>
                        <option value="8_classes">8 classes — ₹8,000</option>
                    </select></div>
                <p id="nsError" class="auth__error" style="display:none"></p>
                <p style="font-size:0.8rem;color:var(--color-text-muted)">A secure temporary PIN is generated and shown once after saving.</p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" id="nsBtn" onclick="Admin.submitCreateStudent()">Create Student</button>
            </div>
        `);
    }

    // Mirror of backend _login_id_from_roll — display only; the backend
    // generates the authoritative Login ID on save.
    function previewLoginId() {
        const roll = ((document.getElementById('nsCma') || {}).value || '').trim();
        const out = (document.getElementById('nsUserPreview') || {});
        const m = /^CMA-\d{4}-(\d+)$/.exec(roll);
        if (m) out.value = 'CMA-' + String(parseInt(m[1], 10)).padStart(3, '0');
        else if (roll) out.value = '(derived from roll on save)';
        else out.value = '(auto from generated roll)';
    }

    async function submitCreateStudent() {
        const err = document.getElementById('nsError');
        const fee = (document.getElementById('nsFee') || {}).value;
        const body = {
            first_name: (document.getElementById('nsFirst') || {}).value.trim(),
            last_name: (document.getElementById('nsLast') || {}).value.trim(),
            cma_registration_id: (document.getElementById('nsCma') || {}).value.trim() || null,
            phone: (document.getElementById('nsPhone') || {}).value.trim() || null,
            date_of_birth: (document.getElementById('nsDob') || {}).value || null,
            programme_id: (document.getElementById('nsProgramme') || {}).value.trim() || null,
            programme_name: (document.getElementById('nsProgramme') || {}).value.trim() || null,
            fee_plan: fee || null,
            fee_amount: fee === '4_classes' ? 4500 : fee === '8_classes' ? 8000 : null,
        };
        if (!body.first_name) {
            err.textContent = 'First name is required.';
            err.style.display = 'block';
            return;
        }
        try {
            const btn = document.getElementById('nsBtn');
            btn.disabled = true; btn.textContent = 'Creating…';
            const res = await apiCall('/students', { method: 'POST', body: JSON.stringify(body) });
            closeModalDirect();
            showModal(`
                <div class="admin-modal__header admin-modal__header--success"><h3 class="admin-modal__title">Student created</h3></div>
                <div class="admin-modal__body">
                    <p>Student: <strong>${escapeHtml(res.full_name)}</strong></p>
                    <p>Roll No. / Login ID: <strong>${escapeHtml(res.login_id)}</strong></p>
                    <p>CMA Registration ID: <strong>${escapeHtml(res.cma_registration_id)}</strong></p>
                    <p style="font-size:2rem;font-weight:700;letter-spacing:0.35em;text-align:center;margin:16px 0;
                              padding:14px;background:rgba(201,169,110,0.12);border-radius:10px;">${escapeHtml(res.temp_pin)}</p>
                    <p style="color:var(--color-error);font-size:0.85rem;">Temporary PIN shown once only — share privately. Student must change it at first login.</p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--primary" onclick="Admin.closeModalDirect();Admin.navigateTo('students')">Done</button>
                </div>
            `);
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
            const btn = document.getElementById('nsBtn');
            if (btn) { btn.disabled = false; btn.textContent = 'Create Student'; }
        }
    }

    async function editStudentModal(id) {
        try {
            const students = await apiCall('/students');
            const s = students.find(x => x.id === id);
            if (!s) { showToast('Student not found', 'error'); return; }
            showModal(`
                <div class="admin-modal__header"><h3 class="admin-modal__title">Edit Student</h3></div>
                <div class="admin-modal__body">
                    <div class="admin-modal__field"><label class="auth__label">First name</label>
                        <input class="auth__input" id="esFirst" value="${escapeHtml(s.first_name || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Last name</label>
                        <input class="auth__input" id="esLast" value="${escapeHtml(s.last_name || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Phone</label>
                        <input class="auth__input" id="esPhone" value="${escapeHtml(s.phone || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Email</label>
                        <input class="auth__input" id="esEmail" value="${escapeHtml(s.email || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Date of birth</label>
                        <input class="auth__input" type="date" id="esDob" value="${s.date_of_birth || ''}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Status</label>
                        <select class="auth__input" id="esStatus">
                            <option value="active" ${s.status === 'active' ? 'selected' : ''}>Active</option>
                            <option value="suspended" ${s.status === 'suspended' ? 'selected' : ''}>Suspended</option>
                            <option value="archived" ${s.status === 'archived' ? 'selected' : ''}>Archived</option>
                        </select></div>
                    <p id="esError" class="auth__error" style="display:none"></p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                    <button class="btn btn--primary" id="esBtn" onclick="Admin.submitEditStudent('${id}')">Save Changes</button>
                </div>
            `);
        } catch (e) { showToast(e.message, 'error'); }
    }

    async function submitEditStudent(id) {
        const err = document.getElementById('esError');
        const body = {
            first_name: (document.getElementById('esFirst') || {}).value,
            last_name: (document.getElementById('esLast') || {}).value,
            phone: (document.getElementById('esPhone') || {}).value,
            email: (document.getElementById('esEmail') || {}).value,
            date_of_birth: (document.getElementById('esDob') || {}).value || null,
            status: (document.getElementById('esStatus') || {}).value,
        };
        try {
            const btn = document.getElementById('esBtn');
            btn.disabled = true; btn.textContent = 'Saving…';
            await apiCall(`/students/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
            closeModalDirect();
            showToast('Student updated', 'success');
            renderStudents();
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
            const btn = document.getElementById('esBtn');
            if (btn) { btn.disabled = false; btn.textContent = 'Save Changes'; }
        }
    }

    async function setStudentStatus(id, status) {
        const label = status === 'active' ? 'reactivate' : 'suspend';
        if (!window.confirm(`Confirm: ${label} this student?`)) return;
        try {
            await apiCall(`/students/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });
            showToast(`Student ${label}d`, 'success');
            renderStudents();
        } catch (e) { showToast(e.message, 'error'); }
    }

    async function archiveStudent(id) {
        if (!window.confirm('Archive this student? All history is preserved; the account is deactivated.')) return;
        try {
            await apiCall(`/students/${id}`, { method: 'PATCH', body: JSON.stringify({ status: 'archived' }) });
            showToast('Student archived (history preserved)', 'success');
            renderStudents();
        } catch (e) { showToast(e.message, 'error'); }
    }

    async function deleteStudentPermanently(id) {
        let impact;
        try {
            impact = await apiCall(`/students/${id}/delete-impact`);
        } catch (e) { showToast(e.message, 'error'); return; }
        if (!impact) return;

        const s = impact.student || {};
        const remove = impact.remove || {};
        const retain = impact.retain_unlinked || {};
        const removedLines = Object.entries(remove)
            .filter(([, n]) => n > 0)
            .map(([k, n]) => `  • ${k.replaceAll('_', ' ')}: ${n}`)
            .join('\n');
        const retainedFinancial = Object.entries(retain)
            .filter(([k, n]) => n > 0 && ['invoices', 'fee_records', 'payment_allocations', 'credit_ledger', 'exam_fees'].includes(k))
            .map(([k, n]) => `  • ${k.replaceAll('_', ' ')}: ${n} (kept for accounting, student link removed)`)
            .join('\n');

        let msg = `PERMANENTLY DELETE ${s.full_name || 'this student'} (${s.cma_registration_id || ''})?\n\n`;
        msg += 'This cannot be undone. The login username and CMA registration ID will be freed for reuse.\n';
        if (removedLines) msg += `\nRecords that will be REMOVED:\n${removedLines}\n`;
        if (retainedFinancial) msg += `\nRecords RETAINED (unlinked):\n${retainedFinancial}\n`;
        if (impact.archive_recommended) {
            msg += '\nRecommendation: ARCHIVING is safer — it keeps this history without deleting anything (Archive button). ';
            msg += 'Choose permanent deletion only for incorrect, duplicate or test profiles.\n';
        }
        msg += '\nPress OK to delete PERMANENTLY, or Cancel to keep the student.';
        if (!window.confirm(msg)) return;

        try {
            const res = await apiCall(`/students/${id}`, { method: 'DELETE' });
            if (res && res.deleted) {
                const freed = (res.released && res.released.username) || '';
                showToast(`Student permanently deleted${freed ? ` — login "${freed}" freed` : ''}`, 'success');
                if (typeof renderStudents === 'function') renderStudents();
                else if (typeof loadStudents === 'function') loadStudents();
            }
        } catch (e) { showToast(e.message, 'error'); }
    }

    // ========================================
    // Monthly class scheduling (4 / 8 classes per month)
    // ========================================
    async function wsChangeMonth(v) {
        studentWs.scheduleMonth = v;
        studentWs.pendingSlots = [];
        studentWs.scheduleConflicts = [];
        studentWs.scheduleNotice = '';
        delete studentWs.data.classes;
        await loadWsTab('classes');
        render();
    }

    async function wsMonthlyReload() {
        await wsChangeMonth(studentWs.scheduleMonth);
    }

    function wsCollectSlots() {
        const rows = document.querySelectorAll('#wsPendingTable tbody tr');
        if (!rows.length) return;
        const out = [];
        rows.forEach(tr => {
            out.push({
                date: (tr.querySelector('[data-slot-date]') || {}).value || '',
                start: (tr.querySelector('[data-slot-start]') || {}).value || '',
                end: (tr.querySelector('[data-slot-end]') || {}).value || '',
            });
        });
        studentWs.pendingSlots = out;
    }

    function wsAddSlot() {
        wsCollectSlots();
        studentWs.pendingSlots.push({ date: '', start: '17:00', end: '18:00' });
        render();
    }

    function wsRemoveSlot(ix) {
        wsCollectSlots();
        studentWs.pendingSlots.splice(ix, 1);
        render();
    }

    function wsGenerateWeekly() {
        wsCollectSlots();
        const monthly = (studentWs.data.classes || {}).monthly;
        const count = monthly && monthly.remaining != null ? monthly.remaining : 4;
        const month = studentWs.scheduleMonth;
        const dayIx = parseInt((document.getElementById('wsGenDay') || {}).value || '0', 10);
        const start = (document.getElementById('wsGenStart') || {}).value || '17:00';
        const end = (document.getElementById('wsGenEnd') || {}).value || '18:00';
        const today = new Date().toISOString().slice(0, 10);
        const gen = [];
        const [y, m] = month.split('-').map(Number);
        const lastDay = new Date(y, m, 0).getDate();
        const want = (dayIx + 1) % 7; // select Monday=0 → JS getDay()
        for (let d = 1; d <= lastDay && gen.length < count; d++) {
            const iso = `${month}-${String(d).padStart(2, '0')}`;
            if (new Date(iso + 'T12:00:00').getDay() === want && iso >= today) {
                gen.push({ date: iso, start, end });
            }
        }
        if (!gen.length) {
            showToast(`No future ${['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][dayIx]}s left in ${month}`, 'error');
            return;
        }
        studentWs.pendingSlots = studentWs.pendingSlots.concat(gen);
        render();
    }

    async function wsSaveMonthly() {
        wsCollectSlots();
        const sid = studentWs.studentId;
        const slots = (studentWs.pendingSlots || []).filter(p => p.date && p.start && p.end);
        studentWs.scheduleConflicts = [];
        studentWs.scheduleNotice = '';
        if (!slots.length) {
            showToast('Add at least one class slot first', 'error');
            return;
        }
        const instSel = document.getElementById('wsInstSelect');
        const body = {
            month: studentWs.scheduleMonth,
            instructor_id: instSel && instSel.value ? instSel.value : undefined,
            classes: slots.map(p => ({ date: p.date, start_time: p.start, end_time: p.end })),
        };
        try {
            const token = localStorage.getItem('academy_token');
            const resp = await fetch(apiOrigin() + `/api/v1/admin/students/${sid}/monthly-schedule`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
                },
                body: JSON.stringify(body),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                if (data.detail && data.detail.conflicts) {
                    studentWs.scheduleConflicts = data.detail.conflicts;
                    render(); // keep pending slots for editing
                    return;
                }
                showToast((data.detail && data.detail.message) || (typeof data.detail === 'string' ? data.detail : 'Save failed'), 'error');
                return;
            }
            studentWs.pendingSlots = [];
            studentWs.scheduleNotice = `Saved ${data.scheduled.length} class(es) for ${body.month}` +
                (data.skipped_duplicates ? ` (${data.skipped_duplicates} already existed — skipped)` : '') +
                (data.remaining != null ? `. Remaining to schedule: ${data.remaining}` : '.');
            delete studentWs.data.classes;
            await loadWsTab('classes');
            render();
        } catch (e) {
            showToast(e.message || 'Save failed', 'error');
        }
    }

    // ========================================
    // Recurring schedule change (availability + travel preview)
    // ========================================
    function wsScFields() {
        return {
            day: (document.getElementById('scDay') || {}).value || 'saturday',
            start_time: (document.getElementById('scStart') || {}).value || '',
            end_time: (document.getElementById('scEnd') || {}).value || '',
            effective_date: (document.getElementById('scEff') || {}).value || '',
            reason: ((document.getElementById('scNote') || {}).value || '').trim(),
        };
    }

    function wsScInvalidate() {
        const btn = document.getElementById('scApplyBtn');
        if (btn) btn.disabled = true;
        const area = document.getElementById('scPreviewArea');
        if (area) area.innerHTML = '';
    }

    function _scStatusBadge(st) {
        const map = { available: 'approved', ok: 'approved', conflict: 'rejected',
                      travel_insufficient: 'rejected', duplicate_target: 'rejected',
                      needs_clarification: 'pending' };
        const label = { available: 'Available', ok: 'Available', conflict: 'Class conflict',
                        travel_insufficient: 'Travel time insufficient', duplicate_target: 'Already scheduled',
                        needs_clarification: 'Travel data missing — clarification' }[st] || st;
        return `<span class="badge badge--${map[st] || 'pending'}">${label}</span>`;
    }

    function _scRenderPreview(data, opts) {
        const area = document.getElementById('scPreviewArea');
        if (!area) return;
        const props = (data.proposed || []).map(pr => `
            <tr><td>${pr.day.charAt(0).toUpperCase()+pr.day.slice(1)}s ${pr.start_time}–${pr.end_time}
                <div style="font-size:0.72rem;color:var(--color-text-muted)">first from ${formatDate(pr.first_occurrence)}</div></td>
                <td>${_scStatusBadge(pr.status)}${pr.message ? `<div style="font-size:0.75rem">${escapeHtml(pr.message)}</div>` : ''}
                ${(pr.alternatives && pr.alternatives.length) ? `<div style="font-size:0.75rem;color:var(--color-accent)">Alternatives: ${pr.alternatives.map(a => a.start + '–' + a.end).join(', ')}</div>` : ''}</td></tr>`).join('');
        const aff = (data.affected_sessions || []).map(a => `
            <tr><td>${formatDate(a.old_date)} ${a.old_start}–${a.old_end}</td>
                <td>→ ${formatDate(a.new_date)} ${a.new_start}–${a.new_end}</td>
                <td>${_scStatusBadge(a.status)}${a.message ? `<div style="font-size:0.75rem">${escapeHtml(a.message)}</div>` : ''}</td></tr>`).join('');
        const warns = (data.warnings && data.warnings.length)
            ? `<div style="border:1px solid var(--color-warning);border-radius:8px;padding:8px10px;margin:8px 0;color:var(--color-warning);font-size:0.8rem">
                 <b>Travel could not be confirmed:</b><br>${data.warnings.map(w => '• ' + escapeHtml(w)).join('<br>')}
                 ${data.requires_travel_ack ? `<label style="display:block;margin-top:6px"><input type="checkbox" id="scAck"> I acknowledge the travel-data warnings and want to proceed</label>` : ''}</div>`
            : '';
        const conflictBox = (data.conflicts && data.conflicts.length)
            ? `<div style="border:1px solid var(--color-warning);border-radius:8px;padding:8px 10px;margin:8px 0;color:var(--color-warning);font-size:0.8rem">
                 <b>Conflicts — nothing was applied:</b><br>${data.conflicts.map(c => '• ' + escapeHtml(c.message)).join('<br>')}</div>`
            : '';
        area.innerHTML = `
            ${conflictBox}
            ${warns}
            <table class="admin-table" style="margin-bottom:8px"><thead><tr><th>Proposed pattern (from ${escapeHtml(data.effective_date || '')})</th><th>Availability</th></tr></thead><tbody>${props}</tbody></table>
            ${(data.affected_sessions && data.affected_sessions.length) ? `
                <div style="font-size:0.8rem;font-weight:600;margin:6px 0">Future classes that will change (${data.affected_sessions.length}):</div>
                <table class="admin-table"><thead><tr><th>Current</th><th>New slot</th><th>Check</th></tr></thead><tbody>${aff}</tbody></table>`
                : `<p style="font-size:0.8rem;color:var(--color-text-muted)">No eligible future classes to move yet (only the recurring pattern will change).</p>`}
            ${opts && opts.applied ? `<div style="color:var(--color-success,#2E7D32);font-size:0.85rem;margin-top:6px">Applied — ${escapeHtml(opts.applied)}</div>` : ''}
        `;
    }

    async function wsScPreview() {
        const f = wsScFields();
        if (!f.effective_date) { showToast('Choose the effective date first', 'error'); return; }
        const sid = studentWs.studentId;
        try {
            const token = localStorage.getItem('academy_token');
            const resp = await fetch(apiOrigin() + `/api/v1/admin/students/${sid}/recurring-schedule-change`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
                body: JSON.stringify({ ...f, new_days: [{ day: f.day, start_time: f.start_time, end_time: f.end_time }], confirm: false }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                const detail = data.detail || {};
                _scRenderPreview({ ...f, proposed: [], affected_sessions: [], warnings: detail.warnings || [], requires_travel_ack: false, conflicts: typeof detail === 'object' && detail.conflicts ? detail.conflicts : [{ message: typeof detail === 'string' ? detail : 'Preview failed' }] }, {});
                return;
            }
            studentWs.schedChangePreview = data;
            _scRenderPreview(data, {});
            const btn = document.getElementById('scApplyBtn');
            if (btn) btn.disabled = false;
        } catch (e) { showToast(e.message || 'Preview failed', 'error'); }
    }

    async function wsScApply() {
        const f = wsScFields();
        if (!f.effective_date) { showToast('Choose the effective date first', 'error'); return; }
        const ackEl = document.getElementById('scAck');
        const sid = studentWs.studentId;
        try {
            const token = localStorage.getItem('academy_token');
            const resp = await fetch(apiOrigin() + `/api/v1/admin/students/${sid}/recurring-schedule-change`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...(token ? { 'Authorization': `Bearer ${token}` } : {}) },
                body: JSON.stringify({
                    ...f,
                    new_days: [{ day: f.day, start_time: f.start_time, end_time: f.end_time }],
                    confirm: true,
                    acknowledge_travel_unknown: !!(ackEl && ackEl.checked),
                }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                const detail = data.detail || {};
                _scRenderPreview({ ...f, proposed: (studentWs.schedChangePreview || {}).proposed || [],
                                   affected_sessions: (studentWs.schedChangePreview || {}).affected_sessions || [],
                                   warnings: detail.warnings || (studentWs.schedChangePreview || {}).warnings || [],
                                   requires_travel_ack: !!detail.requires_travel_ack,
                                   conflicts: detail.conflicts || (typeof detail === 'string' ? [{ message: detail }] : []) }, {});
                const btn = document.getElementById('scApplyBtn');
                if (btn) btn.disabled = true;
                showToast('Change not applied — resolve the conflicts shown', 'error');
                return;
            }
            const applied = `effective ${data.effective_date} · ${data.sessions_moved.length} future class(es) moved`;
            showToast('Recurring schedule updated', 'success');
            studentWs.schedChangePreview = null;
            delete studentWs.data.classes;
            await loadWsTab('classes');
            render();
            const area = document.getElementById('scPreviewArea');
            if (area) area.insertAdjacentHTML('afterbegin',
                `<div style="color:var(--color-success,#2E7D32);font-size:0.85rem;margin-bottom:6px">✓ Applied — ${escapeHtml(applied)}</div>`);
        } catch (e) { showToast(e.message || 'Apply failed', 'error'); }
    }

    // ========================================
    // Instructor account management
    // ========================================
    function createInstructorModal() {
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Add Instructor</h3></div>
            <div class="admin-modal__body">
                <div class="admin-modal__field"><label class="auth__label">Login ID *</label>
                    <input class="auth__input" id="niUser" placeholder="e.g. ashapiano"></div>
                <div class="admin-modal__field"><label class="auth__label">First name *</label>
                    <input class="auth__input" id="niFirst"></div>
                <div class="admin-modal__field"><label class="auth__label">Last name</label>
                    <input class="auth__input" id="niLast"></div>
                <div class="admin-modal__field"><label class="auth__label">Phone</label>
                    <input class="auth__input" id="niPhone"></div>
                <div class="admin-modal__field"><label class="auth__label">Email address</label>
                    <input class="auth__input" id="niEmail" type="email" placeholder="name@example.com"></div>
                <div class="admin-modal__field"><label class="auth__label">Specialisations</label>
                    <input class="auth__input" id="niSpec" placeholder="e.g. Piano, Western Vocals"></div>
                <div class="admin-modal__field"><label class="auth__label">Qualifications</label>
                    <input class="auth__input" id="niQual"></div>
                <div class="admin-modal__field"><label class="auth__label">Experience (years)</label>
                    <input class="auth__input" id="niExp"></div>
                <p id="niError" class="auth__error" style="display:none"></p>
                <p style="font-size:0.8rem;color:var(--color-text-muted)">A secure temporary PIN is generated and shown once after saving.</p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" id="niBtn" onclick="Admin.submitCreateInstructor()">Create Instructor</button>
            </div>
        `);
    }

    async function submitCreateInstructor() {
        const err = document.getElementById('niError');
        const body = {
            username: (document.getElementById('niUser') || {}).value.trim(),
            first_name: (document.getElementById('niFirst') || {}).value.trim(),
            last_name: (document.getElementById('niLast') || {}).value.trim(),
            phone: (document.getElementById('niPhone') || {}).value.trim() || null,
            specializations: (document.getElementById('niSpec') || {}).value.trim() || null,
            qualifications: (document.getElementById('niQual') || {}).value.trim() || null,
            experience_years: (document.getElementById('niExp') || {}).value.trim() || null,
            email: (document.getElementById('niEmail') || {}).value.trim() || null,
        };
        if (!body.username || !body.first_name) {
            err.textContent = 'Login ID and first name are required.';
            err.style.display = 'block';
            return;
        }
        try {
            const btn = document.getElementById('niBtn');
            btn.disabled = true; btn.textContent = 'Creating…';
            const res = await apiCall('/instructors', { method: 'POST', body: JSON.stringify(body) });
            closeModalDirect();
            showModal(`
                <div class="admin-modal__header admin-modal__header--success"><h3 class="admin-modal__title">Instructor created</h3></div>
                <div class="admin-modal__body">
                    <p>Instructor: <strong>${escapeHtml(res.name)}</strong></p>
                    <p>Login ID: <strong>${escapeHtml(res.login_id)}</strong></p>
                    <p style="font-size:2rem;font-weight:700;letter-spacing:0.35em;text-align:center;margin:16px 0;
                              padding:14px;background:rgba(201,169,110,0.12);border-radius:10px;">${escapeHtml(res.temp_pin)}</p>
                    <p style="color:var(--color-error);font-size:0.85rem;">Temporary PIN shown once only — share privately. Instructor must change it at first login.</p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--primary" onclick="Admin.closeModalDirect();Admin.navigateTo('instructors')">Done</button>
                </div>
            `);
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
            const btn = document.getElementById('niBtn');
            if (btn) { btn.disabled = false; btn.textContent = 'Create Instructor'; }
        }
    }

    async function editInstructorModal(id) {
        try {
            const instructors = await apiCall('/instructors');
            const i = instructors.find(x => x.id === id);
            if (!i) { showToast('Instructor not found', 'error'); return; }
            showModal(`
                <div class="admin-modal__header"><h3 class="admin-modal__title">Edit Instructor</h3></div>
                <div class="admin-modal__body">
                    <div class="admin-modal__field"><label class="auth__label">First name</label>
                        <input class="auth__input" id="eiFirst" value="${escapeHtml(i.first_name || (i.full_name || '').split(' ')[0] || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Last name</label>
                        <input class="auth__input" id="eiLast" value="${escapeHtml(i.last_name || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Phone</label>
                        <input class="auth__input" id="eiPhone" value="${escapeHtml(i.phone || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Email address</label>
                        <input class="auth__input" id="eiEmail" type="email" placeholder="name@example.com" value="${escapeHtml(i.email || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Specialisations</label>
                        <input class="auth__input" id="eiSpec" value="${escapeHtml(i.specializations || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Qualifications</label>
                        <input class="auth__input" id="eiQual" value="${escapeHtml(i.qualifications || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Experience (years)</label>
                        <input class="auth__input" id="eiExp" value="${escapeHtml(i.experience_years || '')}"></div>
                    <div class="admin-modal__field"><label class="auth__label">Travel buffer between offline classes (minutes)</label>
                        <input class="auth__input" id="eiTravel" type="number" min="0" max="600" placeholder="e.g. 30 — blank = cannot confirm travel"
                            value="${i.travel_buffer_minutes != null ? i.travel_buffer_minutes : ''}"></div>
                    <p id="eiError" class="auth__error" style="display:none"></p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                    <button class="btn btn--primary" id="eiBtn" onclick="Admin.submitEditInstructor('${id}')">Save Changes</button>
                </div>
            `);
        } catch (e) { showToast(e.message, 'error'); }
    }

    async function submitEditInstructor(id) {
        const err = document.getElementById('eiError');
        const body = {
            first_name: (document.getElementById('eiFirst') || {}).value,
            last_name: (document.getElementById('eiLast') || {}).value,
            phone: (document.getElementById('eiPhone') || {}).value,
            email: (document.getElementById('eiEmail') || {}).value.trim(),
            specializations: (document.getElementById('eiSpec') || {}).value,
            qualifications: (document.getElementById('eiQual') || {}).value,
            experience_years: (document.getElementById('eiExp') || {}).value,
        };
        const travel = (document.getElementById('eiTravel') || {}).value;
        if (travel !== '' && travel != null) body.travel_buffer_minutes = parseInt(travel, 10);
        try {
            const btn = document.getElementById('eiBtn');
            btn.disabled = true; btn.textContent = 'Saving…';
            await apiCall(`/instructors/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
            closeModalDirect();
            showToast('Instructor updated', 'success');
            renderInstructors();
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
            const btn = document.getElementById('eiBtn');
            if (btn) { btn.disabled = false; btn.textContent = 'Save Changes'; }
        }
    }

    async function deactivateInstructor(id) {
        try {
            const impact = await apiCall(`/instructors/${id}/impact`);
            const stuList = (impact.assigned_students || []).map(x => `${escapeHtml(x.name)} (${escapeHtml(x.cma_registration_id)})`).join(', ') || 'none';
            showModal(`
                <div class="admin-modal__header admin-modal__header--warning">
                    <h3 class="admin-modal__title">Deactivate Instructor</h3>
                </div>
                <div class="admin-modal__body">
                    <p><strong>Affected students (${impact.assigned_student_count}):</strong> ${stuList}</p>
                    <p style="margin-top:8px"><strong>Future classes:</strong> ${impact.future_class_count} · <strong>Weekly timetable rows:</strong> ${impact.recurring_schedule_rows}</p>
                    ${(impact.future_classes || []).length ? `<ul style="margin:10px 0 0 18px;font-size:0.85rem;color:var(--color-text-secondary)">${impact.future_classes.slice(0, 10).map(f => `<li>${escapeHtml(f.date)} ${escapeHtml(f.start)}–${escapeHtml(f.end)}</li>`).join('')}</ul>` : ''}
                    <label style="display:flex;gap:8px;align-items:center;margin-top:16px;font-size:0.85rem">
                        <input type="checkbox" id="deAck"> I have reassigned or explicitly resolved these students and classes.
                    </label>
                    <p id="deError" class="auth__error" style="display:none"></p>
                </div>
                <div class="admin-modal__footer">
                    <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                    <button class="btn btn--primary" onclick="Admin.confirmDeactivateInstructor('${id}')">Deactivate</button>
                </div>
            `);
        } catch (e) { showToast(e.message, 'error'); }
    }

    async function confirmDeactivateInstructor(id) {
        const ack = document.getElementById('deAck');
        const err = document.getElementById('deError');
        if (ack && !ack.checked) {
            err.textContent = 'Please confirm the students and classes have been resolved or acknowledged.';
            err.style.display = 'block';
            return;
        }
        try {
            await apiCall(`/instructors/${id}`, {
                method: 'PATCH',
                body: JSON.stringify({ is_active: false, acknowledge_future_classes: true }),
            });
            closeModalDirect();
            showToast('Instructor deactivated', 'success');
            renderInstructors();
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
        }
    }

    async function setInstructorActive(id, active) {
        if (active && !window.confirm('Reactivate this instructor?')) return;
        try {
            await apiCall(`/instructors/${id}`, { method: 'PATCH', body: JSON.stringify({ is_active: active }) });
            showToast(active ? 'Instructor reactivated' : 'Instructor updated', 'success');
            renderInstructors();
        } catch (e) { showToast(e.message, 'error'); }
    }

    // ========================================
    // Assign instructor to a recurring class
    // ========================================
    function assignInstructor(enrollmentId, day, start, end) {
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Assign Instructor</h3></div>
            <div class="admin-modal__body">
                ${day ? '<p style="font-size:0.85rem;color:var(--color-text-secondary)">Class slot: <strong>' + escapeHtml(day) + ' ' + escapeHtml(start) + '–' + escapeHtml(end) + '</strong></p>' : '<p style="font-size:0.85rem;color:var(--color-text-secondary)">This enrolment has no fixed weekly slot yet — conflict check applies from the first scheduled class.</p>'}
                <div class="admin-modal__field"><label class="auth__label">Instructor</label>
                    <select class="auth__input" id="aiInstructor">
                        <option value="">Loading…</option>
                    </select></div>
                <p id="aiInfo" style="font-size:0.82rem;color:var(--color-text-secondary)"></p>
                <div id="aiConflicts"></div>
                <label style="display:flex;gap:8px;align-items:center;margin-top:12px;font-size:0.85rem;display:none" id="aiAckWrap">
                    <input type="checkbox" id="aiAck"> I confirm: assign anyway (no existing class will be moved or deleted).
                </label>
                <p id="aiError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--secondary" onclick="Admin.confirmAssignInstructor()" id="aiUnassign">Unassign</button>
                <button class="btn btn--primary" id="aiBtn" onclick="Admin.confirmAssignInstructor()">Assign</button>
            </div>
        `);
        // load instructors
        apiCall('/instructors').then(list => {
            const sel = document.getElementById('aiInstructor');
            sel.innerHTML = '<option value="">— select —</option>' +
                list.filter(i => i.is_active).map(i => {
                    const label = `${escapeHtml(i.full_name)}${i.specializations ? ' — ' + escapeHtml(i.specializations) : ''}`;
                    return `<option value="${i.id}" data-spec="${escapeHtml(i.specializations || '')}" data-name="${escapeHtml(i.full_name)}">${label}</option>`;
                }).join('');
            sel.addEventListener('change', () => {
                const opt = sel.options[sel.selectedIndex];
                document.getElementById('aiInfo').textContent = opt && opt.value
                    ? `Selected: ${opt.getAttribute('data-name')} — ${opt.getAttribute('data-spec') || 'no specialisations listed'}`
                    : '';
            });
        }).catch(e => {
            document.getElementById('aiError').textContent = e.message;
            document.getElementById('aiError').style.display = 'block';
        });
        // stash context
        window.__assignCtx = { enrollmentId, day, start, end };
    }

    async function checkAssignAvailability() {
        const ctx = window.__assignCtx;
        const sel = document.getElementById('aiInstructor');
        const err = document.getElementById('aiError');
        if (!ctx || !sel || !sel.value) {
            err.textContent = 'Select an instructor first.';
            err.style.display = 'block';
            return null;
        }
        if (!ctx.day) {
            document.getElementById('aiConflicts').innerHTML = '<div style="margin-top:12px;font-size:0.85rem;color:var(--color-text-muted)">No fixed slot yet — conflicts will apply once classes are scheduled.</div>';
            return { conflicts: [] };
        }
        const data = await apiCall(`/instructors/${sel.value}/availability?day=${encodeURIComponent(ctx.day)}&start=${encodeURIComponent(ctx.start)}&end=${encodeURIComponent(ctx.end)}&exclude_enrollment_id=${encodeURIComponent(ctx.enrollmentId)}`);
        const box = document.getElementById('aiConflicts');
        if (data.conflicts.length) {
            box.innerHTML = `<div class="reg-deadline-banner reg-deadline-banner--overdue" style="margin-top:12px">
                <div class="reg-deadline-banner__text"><strong>Time conflict warning</strong>
                <span>${data.conflicts.map(c => escapeHtml(`${c.kind}: ${c.day || c.date} ${c.start}–${c.end} with ${c.student}`)).join('<br>')}</span>
                <span style="display:block;margin-top:4px">The instructor also teaches ${data.instructor.specializations ? escapeHtml(data.instructor.specializations) : 'other subjects'} — confirm the subject matches your needs.</span>
                </div></div>`;
            document.getElementById('aiAckWrap').style.display = 'flex';
        } else {
            box.innerHTML = `<div style="margin-top:12px;font-size:0.85rem;color:var(--success)">No scheduling conflicts for this slot.</div>`;
            document.getElementById('aiAckWrap').style.display = 'none';
        }
        return data;
    }

    async function confirmAssignInstructor() {
        const ctx = window.__assignCtx;
        const sel = document.getElementById('aiInstructor');
        const err = document.getElementById('aiError');
        const btn = document.getElementById('aiBtn');
        if (!ctx) return;
        if (sel && !sel.value) {
            err.textContent = 'Select an instructor first (or use Unassign).';
            err.style.display = 'block';
            return;
        }
        try {
            btn.disabled = true; btn.textContent = 'Checking…';
            const check = await checkAssignAvailability();
            if (check && check.conflicts.length) {
                const ack = document.getElementById('aiAck');
                if (!ack || !ack.checked) {
                    err.textContent = 'This slot conflicts with existing classes — tick the confirmation box to assign anyway.';
                    err.style.display = 'block';
                    btn.disabled = false; btn.textContent = 'Assign';
                    return;
                }
            }
            btn.textContent = 'Assigning…';
            const conflictsConfirmed = document.getElementById('aiAck') && document.getElementById('aiAck').checked;
            await apiCall(`/enrollments/${ctx.enrollmentId}/instructor`, {
                method: 'POST',
                body: JSON.stringify({ instructor_id: sel.value, confirm_conflicts: !!conflictsConfirmed }),
            });
            closeModalDirect();
            showToast('Instructor assigned (and recurring timetable updated)', 'success');
            navigateTo('classes');
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
            btn.disabled = false; btn.textContent = 'Assign';
        }
    }

    // ========================================
    // Student workspace actions
    // ========================================
    async function wsSetStatus(id, status) {
        const label = status === 'active' ? 'reactivate' : 'suspend';
        if (!window.confirm('Confirm: ' + label + ' this student?')) return;
        try {
            await apiCall('/students/' + id, { method: 'PATCH', body: JSON.stringify({ status: status }) });
            showToast('Student ' + label + 'd', 'success');
            studentWs.student = await apiCall('/students/' + id);
            render();
        } catch (e) { showToast(e.message, 'error'); }
    }

    async function moveSession(id) {
        // Late (inside 24h) admin-initiated moves need the explicit exception
        // workflow with a recorded reason — never a silent bypass.
        let sess = null;
        try {
            const all = await apiV1Call('/sessions?limit=400');
            sess = all.find(x => x.id === id) || null;
        } catch (e) { /* modal still opens; backend enforces the cutoff */ }
        const isLate = sess && sess.status === 'scheduled' && hoursUntilSession(sess) < 24;
        window.__rsExceptionId = isLate ? id : null;

        showModal('MOVE_SESSION_MODAL');
        const modal = document.querySelector('.admin-modal');
        const policyBlock = '<div class="admin-modal__field"><p style="font-size:0.82rem;color:var(--color-text-secondary);margin:0 0 6px">'
            + escapeHtml(RESCHEDULE_POLICY_TEXT) + '</p></div>';
        const lateBlock = isLate
            ? '<div class="admin-modal__field"><p style="font-size:0.85rem;color:var(--color-warning);margin:0 0 6px">'
              + '<strong>Late change — policy exception.</strong> This class starts inside 24 hours, so the normal '
              + 'reschedule path is closed. A reason of at least 8 characters is required and the action is '
              + 'recorded in the audit trail as a policy exception.</p></div>'
            : '';
        modal.innerHTML = ''
            + '<div class="admin-modal__header"><h3 class="admin-modal__title">'
            + (isLate ? 'Move Class — Late Change (Policy Exception)' : 'Move / Reschedule Class') + '</h3></div>'
            + '<div class="admin-modal__body">'
            + '<p>Moves only this one dated class. The recurring weekly timetable and all other occurrences stay untouched; the original record keeps its history.</p>'
            + policyBlock + lateBlock
            + '<div class="admin-modal__field"><label class="auth__label">New date</label><input class="auth__input" type="date" id="rsNewDate"></div>'
            + '<div class="admin-modal__field"><label class="auth__label">New start</label><input class="auth__input" type="time" id="rsNewStart"></div>'
            + '<div class="admin-modal__field"><label class="auth__label">New end</label><input class="auth__input" type="time" id="rsNewEnd"></div>'
            + '<div class="admin-modal__field"><label class="auth__label">Reason (recorded in history)'
            + (isLate ? ' — required, min 8 characters' : '') + '</label><textarea class="auth__input" id="rsReason" rows="2"></textarea></div>'
            + '<p id="rsError" class="auth__error" style="display:none"></p>'
            + '</div>'
            + '<div class="admin-modal__footer">'
            + '<button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>'
            + '<button class="btn btn--primary" id="rsConfirmBtn" onclick="Admin.confirmApproveReschedule(\'' + id + '\')">'
            + (isLate ? 'Record Exception &amp; Move Class' : 'Confirm &amp; Move Class') + '</button>'
            + '</div>';
    }

    async function wsEditEnrollment(enrollmentId) {
        try {
            const students = await apiCall('/students');
            let enrol = null;
            for (const st of students) {
                const e = (st.enrollments || []).find(x => x.id === enrollmentId);
                if (e) { enrol = e; break; }
            }
            if (!enrol) {
                const detail = await apiCall('/students/' + studentWs.studentId);
                enrol = (detail.enrollments || []).find(x => x.id === enrollmentId);
            }
            if (!enrol) { showToast('Enrollment not found', 'error'); return; }
            showModal('EDIT_ENROLMENT_MODAL');
            const modal = document.querySelector('.admin-modal');
            modal.innerHTML = ''
                + '<div class="admin-modal__header"><h3 class="admin-modal__title">Edit Enrolment</h3></div>'
                + '<div class="admin-modal__body">'
                + '<div class="admin-modal__field"><label class="auth__label">Programme name</label><input class="auth__input" id="enName" value="' + escapeHtml(enrol.programme_name || '') + '"></div>'
                + '<div class="admin-modal__field"><label class="auth__label">Fee plan</label><select class="auth__input" id="enFee">'
                + '<option value=""' + (!enrol.fee_plan ? ' selected' : '') + '>Not assigned</option>'
                + '<option value="4_classes"' + (enrol.fee_plan === '4_classes' ? ' selected' : '') + '>4 classes — Rs.4,500</option>'
                + '<option value="8_classes"' + (enrol.fee_plan === '8_classes' ? ' selected' : '') + '>8 classes — Rs.8,000</option>'
                + '</select></div>'
                + '<div class="admin-modal__field"><label class="auth__label">Fee amount</label><input class="auth__input" type="number" id="enAmount" value="' + (enrol.fee_amount || '') + '"></div>'
                + '<div class="admin-modal__field"><label class="auth__label">Status</label><select class="auth__input" id="enStatus">'
                + '<option value="active"' + (enrol.status === 'active' ? ' selected' : '') + '>Active</option>'
                + '<option value="completed"' + (enrol.status === 'completed' ? ' selected' : '') + '>Completed</option>'
                + '<option value="cancelled"' + (enrol.status === 'cancelled' ? ' selected' : '') + '>Cancelled</option>'
                + '</select></div>'
                + '<p id="enError" class="auth__error" style="display:none"></p>'
                + '</div>'
                + '<div class="admin-modal__footer">'
                + '<button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>'
                + '<button class="btn btn--primary" id="enBtn" onclick="Admin.wsSaveEnrollment(\'' + enrollmentId + '\')">Save Changes</button>'
                + '</div>';
        } catch (e) { showToast(e.message, 'error'); }
    }

    async function wsSaveEnrollment(enrollmentId) {
        const err = document.getElementById('enError');
        const body = {
            programme_name: (document.getElementById('enName') || {}).value,
            fee_plan: (document.getElementById('enFee') || {}).value,
            fee_amount: parseFloat((document.getElementById('enAmount') || {}).value || '0') || 0,
            status: (document.getElementById('enStatus') || {}).value,
        };
        try {
            const btn = document.getElementById('enBtn');
            btn.disabled = true; btn.textContent = 'Saving...';
            await apiCall('/enrollments/' + enrollmentId, { method: 'PATCH', body: JSON.stringify(body) });
            closeModalDirect();
            showToast('Enrollment updated', 'success');
            studentWs.student = await apiCall('/students/' + studentWs.studentId);
            render();
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
            const btn = document.getElementById('enBtn');
            if (btn) { btn.disabled = false; btn.textContent = 'Save Changes'; }
        }
    }

    function wsAddEnrollment(studentId) {
        showModal('ADD_ENROLMENT_MODAL');
        const modal = document.querySelector('.admin-modal');
        modal.innerHTML = ''
            + '<div class="admin-modal__header"><h3 class="admin-modal__title">Add Enrolment</h3></div>'
            + '<div class="admin-modal__body">'
            + '<div class="admin-modal__field"><label class="auth__label">Programme name *</label><input class="auth__input" id="neName" placeholder="e.g. Piano"></div>'
            + '<div class="admin-modal__field"><label class="auth__label">Programme id</label><input class="auth__input" id="neId" placeholder="e.g. piano"></div>'
            + '<div class="admin-modal__field"><label class="auth__label">Fee plan</label><select class="auth__input" id="neFee">'
            + '<option value="">Not assigned</option>'
            + '<option value="4_classes">4 classes — Rs.4,500</option>'
            + '<option value="8_classes">8 classes — Rs.8,000</option>'
            + '</select></div>'
            + '<p id="neError" class="auth__error" style="display:none"></p>'
            + '</div>'
            + '<div class="admin-modal__footer">'
            + '<button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>'
            + '<button class="btn btn--primary" id="neBtn" onclick="Admin.wsSaveNewEnrollment(\'' + studentId + '\')">Add Enrolment</button>'
            + '</div>';
    }

    async function wsSaveNewEnrollment(studentId) {
        const err = document.getElementById('neError');
        const name = ((document.getElementById('neName') || {}).value || '').trim();
        const id = ((document.getElementById('neId') || {}).value || '').trim();
        const fee = (document.getElementById('neFee') || {}).value;
        if (!name) {
            err.textContent = 'Programme name is required.';
            err.style.display = 'block';
            return;
        }
        try {
            const btn = document.getElementById('neBtn');
            btn.disabled = true; btn.textContent = 'Adding...';
            await apiCall('/enrollments', {
                method: 'POST',
                body: JSON.stringify({
                    student_id: studentId,
                    programme_id: id || name.toLowerCase().replace(/[^a-z0-9]+/g, '_'),
                    programme_name: name,
                    fee_plan: fee || null,
                    fee_amount: fee === '4_classes' ? 4500 : fee === '8_classes' ? 8000 : null,
                }),
            });
            closeModalDirect();
            showToast('Enrollment added', 'success');
            studentWs.student = await apiCall('/students/' + studentId);
            render();
        } catch (e) {
            err.textContent = e.message;
            err.style.display = 'block';
            const btn = document.getElementById('neBtn');
            if (btn) { btn.disabled = false; btn.textContent = 'Add Enrolment'; }
        }
    }

    async function assignInstructorForEnrollment(enrollmentId) {
        // find the enrolment's first weekly slot so the conflict check is meaningful
        try {
            const all = await apiCall('/schedules');
            const rows = (all.schedules || all || []).filter(x => x.enrollment_id === enrollmentId);
            if (rows.length) {
                const r = rows[0];
                assignInstructor(enrollmentId, r.day_of_week, r.start_time.slice(0, 5), r.end_time.slice(0, 5));
            } else {
                assignInstructor(enrollmentId);
            }
        } catch (e) {
            showToast(e.message, 'error');
        }
    }

    // ========================================
    // Class completion / instructor reports
    // ========================================
    let classReportFilters = {
        instructor_id: '', student_id: '', programme: '', date_from: '', date_to: '', status: '',
    };

    async function renderClassReports() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading class reports...</div>';
        try {
            const params = new URLSearchParams();
            Object.entries(classReportFilters).forEach(([k, v]) => { if (v) params.set(k, v); });
            const qs = params.toString() ? '?' + params.toString() : '';
            const [report, instructors, students] = await Promise.all([
                apiCall('/reports/class-completion' + qs),
                apiCall('/instructors'),
                apiCall('/students'),
            ]);
            const f = classReportFilters;
            const t = report.totals;

            const filterHtml = `
                <div class="admin-card" style="margin-bottom:16px"><div class="admin-card__body">
                <div class="admin-filters" style="margin:0">
                    <select class="admin-filter" id="crInstructor">
                        <option value="">All instructors</option>
                        ${instructors.map(i => `<option value="${i.id}" ${f.instructor_id === i.id ? 'selected' : ''}>${escapeHtml(i.full_name || (i.first_name + ' ' + i.last_name))}</option>`).join('')}
                    </select>
                    <select class="admin-filter" id="crStudent">
                        <option value="">All students</option>
                        ${students.map(x => `<option value="${x.id}" ${f.student_id === x.id ? 'selected' : ''}>${escapeHtml(x.full_name)}</option>`).join('')}
                    </select>
                    <input class="admin-filter" id="crProgramme" placeholder="Instrument / course" value="${escapeHtml(f.programme)}">
                    <input class="admin-filter" type="date" id="crFrom" value="${f.date_from}">
                    <input class="admin-filter" type="date" id="crTo" value="${f.date_to}">
                    <select class="admin-filter" id="crStatus">
                        <option value="">All statuses</option>
                        ${['scheduled', 'completed', 'rescheduled', 'rescheduling_required', 'cancelled'].map(st =>
                            `<option value="${st}" ${f.status === st ? 'selected' : ''}>${formatStatus(st)}</option>`).join('')}
                    </select>
                    <button class="btn btn--primary btn--sm" onclick="Admin.applyClassReportFilters()">Apply</button>
                    <button class="btn btn--secondary btn--sm" onclick="Admin.clearClassReportFilters()">Clear</button>
                </div></div></div>`;

            const rate = t.completion_rate_pct === null ? '—' : t.completion_rate_pct + '%';
            const totalsHtml = `
                <div class="ws-grid" style="margin-bottom:16px">
                    <div class="ws-stat"><div class="ws-stat__label">Total classes</div><div class="ws-stat__value">${t.total}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Completed</div><div class="ws-stat__value">${t.completed}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Awaiting update (past)</div><div class="ws-stat__value">${t.awaiting_update}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Future scheduled</div><div class="ws-stat__value">${t.scheduled_upcoming}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Cancelled</div><div class="ws-stat__value">${t.cancelled}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Rescheduled</div><div class="ws-stat__value">${t.rescheduled}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Reschedule requested</div><div class="ws-stat__value">${t.reschedule_requested}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Completion rate (past)</div><div class="ws-stat__value">${rate}</div></div>
                    <div class="ws-stat"><div class="ws-stat__label">Last completion update</div><div class="ws-stat__value">${t.last_completion_update ? formatDate(t.last_completion_update) : '—'}</div></div>
                </div>`;

            const instrRows = report.by_instructor.map(ig => {
                const past = ig.completed + ig.awaiting_update;
                const igRate = past ? Math.round(100 * ig.completed / past) + '%' : '—';
                return `<tr>
                    <td><strong>${escapeHtml(ig.instructor_name)}</strong><div style="font-size:0.75rem;color:var(--color-text-muted)">${escapeHtml(ig.login_id || '')}</div></td>
                    <td>${ig.completed}</td>
                    <td>${ig.awaiting_update}</td>
                    <td>${ig.scheduled_upcoming}</td>
                    <td>${ig.rescheduled + ig.reschedule_requested}</td>
                    <td>${ig.cancelled}</td>
                    <td>${igRate}</td>
                    <td>${ig.last_completion ? formatDate(ig.last_completion) : '—'}</td>
                </tr>` + (ig.lesson_notes && ig.lesson_notes.length ? `<tr><td colspan="8" style="font-size:0.8rem;color:var(--color-text-secondary)">
                    ${ig.lesson_notes.slice(0, 5).map(n => `• ${formatDate(n.date)} — ${escapeHtml(n.student)}: ${escapeHtml(n.notes)}`).join('<br>')}
                </td></tr>` : '');
            }).join('');

            const sessRows = report.sessions.map(x => `<tr>
                <td>${formatDate(x.scheduled_date)}</td>
                <td>${x.scheduled_start}–${x.scheduled_end}</td>
                <td>${escapeHtml(x.student_name)}</td>
                <td>${escapeHtml(x.programme || '—')}</td>
                <td>${escapeHtml(x.instructor_name || '—')}</td>
                <td><span class="badge badge--${getStatusBadgeClass(x.status)}">${formatStatus(x.status)}</span>
                    ${x.bucket === 'awaiting_update' ? '<div style="font-size:0.72rem;color:var(--color-warning)">past — awaiting update</div>' : ''}</td>
                <td style="max-width:220px">${escapeHtml(x.topics_covered || x.faculty_remarks || '—')}</td>
            </tr>`).join('');

            container.innerHTML = `
                <div class="admin-header"><div>
                    <h1 class="admin-header__title">Instructor &amp; Class Completion Reports</h1>
                    <p class="admin-header__subtitle">Are scheduled lessons actually being delivered?</p>
                </div></div>
                ${filterHtml}
                ${totalsHtml}
                <div class="admin-card" style="margin-bottom:16px"><div class="admin-card__body" style="padding:0">
                    <div style="padding:14px 16px 0"><h3 class="admin-card__title">Per-instructor breakdown</h3></div>
                    ${report.by_instructor.length ? `<table class="admin-table"><thead><tr>
                        <th>Instructor</th><th>Completed</th><th>Awaiting update</th><th>Future</th><th>Reschedule</th><th>Cancelled</th><th>Rate</th><th>Last completion</th>
                    </tr></thead><tbody>${instrRows}</tbody></table>`
                    : '<div class="admin-empty"><div class="admin-empty__text">No classes match the selected filters</div></div>'}
                </div></div>
                <div class="admin-card"><div class="admin-card__body" style="padding:0">
                    <div style="padding:14px 16px 0"><h3 class="admin-card__title">Underlying class records (${report.sessions.length})</h3></div>
                    ${report.sessions.length ? `<table class="admin-table"><thead><tr>
                        <th>Date</th><th>Time</th><th>Student</th><th>Course</th><th>Instructor</th><th>Status</th><th>Topics / notes</th>
                    </tr></thead><tbody>${sessRows}</tbody></table>`
                    : '<div class="admin-empty"><div class="admin-empty__text">No class records match the selected filters</div></div>'}
                </div></div>`;
        } catch (e) {
            container.innerHTML = '<div class="admin-empty"><div class="admin-empty__icon">' + icon('warn') + '</div><div class="admin-empty__title">Unable to load class reports</div><div class="admin-empty__text">' + escapeHtml(e.message) + '</div></div>';
        }
    }

    function applyClassReportFilters() {
        classReportFilters = {
            instructor_id: (document.getElementById('crInstructor') || {}).value || '',
            student_id: (document.getElementById('crStudent') || {}).value || '',
            programme: (document.getElementById('crProgramme') || {}).value || '',
            date_from: (document.getElementById('crFrom') || {}).value || '',
            date_to: (document.getElementById('crTo') || {}).value || '',
            status: (document.getElementById('crStatus') || {}).value || '',
        };
        renderClassReports();
    }

    function clearClassReportFilters() {
        classReportFilters = { instructor_id: '', student_id: '', programme: '', date_from: '', date_to: '', status: '' };
        renderClassReports();
    }

    // ========================================
    // Syllabi — admin catalogue + per-student assignment
    // ========================================
    async function renderSyllabiAdmin() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading syllabi...</div>';
        try {
            const [syllabi, students] = await Promise.all([
                apiV1Call('/learning/syllabi'),
                apiCall('/students'),
            ]);
            const nameOf = {};
            (students || []).forEach(st => { nameOf[st.id] = st.full_name; });

            const cards = (syllabi || []).map(syl => {
                const assigns = (syl.assignments || []).map(a => `
                    <tr>
                        <td>${escapeHtml(nameOf[a.student_id] || a.student_id)}</td>
                        <td>${a.status === 'active'
                            ? '<span class="badge badge--approved">Active</span>'
                            : '<span class="badge badge--cancelled">Archived</span>'}</td>
                        <td>
                            ${a.status === 'active'
                                ? `<button class="btn btn--secondary btn--sm" onclick="Admin.setSyllabusAssignment('${syl.id}','${a.id}','archived')">Archive</button>`
                                : `<button class="btn btn--secondary btn--sm" onclick="Admin.setSyllabusAssignment('${syl.id}','${a.id}','active')">Reopen</button>`}
                        </td>
                    </tr>`).join('');
                return `
                <div class="admin-card" style="margin-bottom:16px">
                    <div class="admin-card__header" style="display:flex;justify-content:space-between;align-items:center">
                        <div>
                            <h3 class="admin-card__title">${escapeHtml(syl.title)}</h3>
                            <div style="font-size:0.8rem;color:var(--color-text-muted)">
                                ${escapeHtml(syl.board || 'academy')} · ${escapeHtml(syl.programme_id || '')} · ${escapeHtml(syl.grade || '—')} · ${(syl.items || []).length} item(s)
                            </div>
                        </div>
                        <div style="display:flex;gap:8px">
                            <button class="btn btn--secondary btn--sm" onclick="Admin.addSyllabusItem('${syl.id}')">+ Item</button>
                            <button class="btn btn--primary btn--sm" onclick="Admin.assignSyllabus('${syl.id}')">Assign to Student</button>
                        </div>
                    </div>
                    <div class="admin-card__body" style="padding:0">
                        ${(syl.items || []).length ? `<table class="admin-table"><thead><tr><th>Topic / unit</th><th>Type</th><th>Objective</th></tr></thead><tbody>
                            ${syl.items.map(i => `<tr><td>${escapeHtml(i.title)}</td><td>${escapeHtml(i.item_type || 'topic')}</td><td>${escapeHtml(i.learning_objective || '—')}</td></tr>`).join('')}
                        </tbody></table>` : '<div class="admin-empty"><div class="admin-empty__text">No items yet — add topics, units or milestones</div></div>'}
                        ${(syl.assignments || []).length ? `
                        <div style="padding:12px 16px 0"><h4 style="font-size:0.85rem;margin:0 0 6px">Assigned students</h4></div>
                        <table class="admin-table"><thead><tr><th>Student</th><th>Status</th><th></th></tr></thead><tbody>${assigns}</tbody></table>`
                        : '<div style="padding:12px 16px;font-size:0.8rem;color:var(--color-text-muted)">Not assigned to any student yet — this syllabus is visible to administrators only.</div>'}
                    </div>
                </div>`;
            }).join('');

            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Syllabi</h1>
                        <p class="admin-header__subtitle">Syllabi are student-specific — assign each one to the students whose plan includes it</p>
                    </div>
                    <button class="btn btn--primary" onclick="Admin.newSyllabus()">+ New Syllabus</button>
                </div>
                ${cards || `<div class="admin-empty"><div class="admin-empty__icon">${icon('reports')}</div>
                    <div class="admin-empty__title">No syllabi yet</div>
                    <div class="admin-empty__text">Create a syllabus, add its topics, then assign it to a student</div></div>`}
            `;
        } catch (e) {
            container.innerHTML = `<div class="admin-empty"><div class="admin-empty__icon">${icon('warn')}</div><div class="admin-empty__title">Unable to load syllabi</div><div class="admin-empty__text">${escapeHtml(e.message)}</div></div>`;
        }
    }

    function newSyllabus() {
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">New Syllabus</h3></div>
            <div class="admin-modal__body">
                <div class="admin-modal__field"><label class="auth__label">Title</label><input class="auth__input" id="syTitle"></div>
                <div class="admin-modal__field"><label class="auth__label">Exam board / pathway</label>
                    <input class="auth__input" id="syBoard" placeholder="academy, Trinity, Rockschool…" value="academy"></div>
                <div class="admin-modal__field"><label class="auth__label">Instrument / course id</label><input class="auth__input" id="syProgramme" placeholder="piano, guitar…"></div>
                <div class="admin-modal__field"><label class="auth__label">Grade / level</label><input class="auth__input" id="syGrade" placeholder="Grade 1, Intermediate…"></div>
                <div class="admin-modal__field"><label class="auth__label">Description</label><textarea class="auth__input" id="syDescription" rows="2"></textarea></div>
                <p id="syError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.saveSyllabus()">Create Syllabus</button>
            </div>`);
    }

    async function saveSyllabus() {
        const err = document.getElementById('syError');
        const payload = {
            title: (document.getElementById('syTitle').value || '').trim(),
            board: (document.getElementById('syBoard').value || '').trim() || 'academy',
            programme_id: (document.getElementById('syProgramme').value || '').trim(),
            grade: (document.getElementById('syGrade').value || '').trim() || null,
            description: (document.getElementById('syDescription').value || '').trim() || null,
        };
        if (!payload.title || !payload.programme_id) {
            err.textContent = 'Title and instrument / course id are required.';
            err.style.display = 'block';
            return;
        }
        try {
            await apiV1Call('/learning/syllabi', { method: 'POST', body: JSON.stringify(payload) });
            closeModalDirect();
            showToast('Syllabus created — add items, then assign it to students.', 'success');
            renderSyllabiAdmin();
        } catch (e) {
            err.textContent = e.message; err.style.display = 'block';
        }
    }

    function addSyllabusItem(syllabusId) {
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Add Syllabus Item</h3></div>
            <div class="admin-modal__body">
                <div class="admin-modal__field"><label class="auth__label">Title (topic, unit or milestone)</label><input class="auth__input" id="siTitle"></div>
                <div class="admin-modal__field"><label class="auth__label">Type</label><select class="auth__input" id="siType">
                    <option value="topic">Topic</option><option value="technical_work">Technical work</option>
                    <option value="repertoire">Repertoire</option><option value="theory">Theory</option>
                    <option value="milestone">Milestone</option></select></div>
                <div class="admin-modal__field"><label class="auth__label">Learning objective</label><textarea class="auth__input" id="siObjective" rows="2"></textarea></div>
                <div class="admin-modal__field"><label class="auth__label">Practice instructions</label><textarea class="auth__input" id="siPractice" rows="2"></textarea></div>
                <p id="siError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.saveSyllabusItem('${syllabusId}')">Add Item</button>
            </div>`);
    }

    async function saveSyllabusItem(syllabusId) {
        const err = document.getElementById('siError');
        const payload = {
            title: (document.getElementById('siTitle').value || '').trim(),
            item_type: (document.getElementById('siType').value || 'topic'),
            learning_objective: (document.getElementById('siObjective').value || '').trim() || null,
            practice_instructions: (document.getElementById('siPractice').value || '').trim() || null,
        };
        if (!payload.title) { err.textContent = 'A title is required.'; err.style.display = 'block'; return; }
        try {
            await apiV1Call(`/learning/syllabi/${syllabusId}/items`, { method: 'POST', body: JSON.stringify(payload) });
            closeModalDirect();
            showToast('Item added.', 'success');
            renderSyllabiAdmin();
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
    }

    async function assignSyllabus(syllabusId) {
        const students = await apiCall('/students');
        const rows = [];
        for (const st of (students || [])) {
            const detail = await apiCall('/students/' + st.id);
            for (const en of (detail.enrollments || [])) {
                if (en.status === 'active') {
                    rows.push({ student_id: st.id, name: st.full_name, enrollment_id: en.id,
                                programme: en.programme_name, instructor: en.instructor || '' });
                }
            }
        }
        if (!rows.length) { showToast('No active enrolments found.', 'error'); return; }
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Assign Syllabus to a Student</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.85rem;color:var(--color-text-secondary)">The syllabus becomes visible only to this student
                (and their linked parents and assigned instructor). Other students never see it.</p>
                <div class="admin-modal__field"><label class="auth__label">Student / enrolment</label>
                    <select class="auth__input" id="asEnrol">
                    ${rows.map(r => `<option value="${r.student_id}|${r.enrollment_id}">${escapeHtml(r.name)} — ${escapeHtml(r.programme)}</option>`).join('')}
                    </select></div>
                <p id="asError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.confirmAssignSyllabus('${syllabusId}')">Assign</button>
            </div>`);
    }

    async function confirmAssignSyllabus(syllabusId) {
        const err = document.getElementById('asError');
        const [student_id, enrollment_id] = (document.getElementById('asEnrol').value || '').split('|');
        try {
            await apiV1Call(`/learning/syllabi/${syllabusId}/assign`, {
                method: 'POST', body: JSON.stringify({ student_id, enrollment_id }),
            });
            closeModalDirect();
            showToast('Syllabus assigned to the student.', 'success');
            renderSyllabiAdmin();
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
    }

    async function setSyllabusAssignment(syllabusId, assignmentId, status) {
        try {
            await apiV1Call(`/learning/syllabi/${syllabusId}/assignments/${assignmentId}`, {
                method: 'PATCH', body: JSON.stringify({ status }),
            });
            showToast(status === 'archived' ? 'Assignment archived.' : 'Assignment reopened.', 'success');
            renderSyllabiAdmin();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Support inbox — two-way communication with the academy
    // ========================================
    const SUPPORT_STATUS_LABEL = { open: 'Awaiting reply', replied: 'Replied', resolved: 'Resolved' };

    async function renderSupportInbox() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading inbox...</div>';
        try {
            const reqs = await apiV1Call('/admin/support');
            const rows = (reqs || []).map(r => `
                <tr style="cursor:pointer" onclick="Admin.openSupportThread('${r.id}')">
                    <td><strong>${escapeHtml(r.sender_name || '—')}</strong>
                        <div style="font-size:0.75rem;color:var(--color-text-muted)">${escapeHtml(r.sender_role || '')}</div></td>
                    <td>${escapeHtml(r.subject)}</td>
                    <td>${escapeHtml(r.related_student_name || '—')}</td>
                    <td>${formatDateTime(r.updated_at || r.created_at)}</td>
                    <td><span class="badge badge--${r.status === 'resolved' ? 'approved' : (r.status === 'replied' ? 'needs-info' : 'pending')}">${SUPPORT_STATUS_LABEL[r.status] || r.status}</span></td>
                    <td>${r.reply_count || 0}</td>
                </tr>`).join('');
            container.innerHTML = `
                <div class="admin-header"><div>
                    <h1 class="admin-header__title">Support Inbox</h1>
                    <p class="admin-header__subtitle">Messages from students, parents and faculty — replies appear in their portal</p>
                </div></div>
                <div class="admin-card"><div class="admin-card__body" style="padding:0">
                ${rows ? `<table class="admin-table"><thead><tr>
                    <th>From</th><th>Subject</th><th>Related student</th><th>Updated</th><th>Status</th><th>Replies</th>
                </tr></thead><tbody>${rows}</tbody></table>` : `
                    <div class="admin-empty"><div class="admin-empty__icon">${icon('inbox')}</div>
                    <div class="admin-empty__title">Inbox is empty</div>
                    <div class="admin-empty__text">Messages sent through Contact Academy Administration appear here</div></div>`}
                </div></div>`;
        } catch (e) {
            container.innerHTML = `<div class="admin-empty"><div class="admin-empty__icon">${icon('warn')}</div><div class="admin-empty__title">Unable to load inbox</div><div class="admin-empty__text">${escapeHtml(e.message)}</div></div>`;
        }
    }

    async function openSupportThread(id) {
        let t;
        try {
            t = await apiV1Call('/admin/support/' + id);
        } catch (e) { alert(e.message); return; }
        const replies = (t.replies || []).map(r => `
            <div style="margin:8px 0;padding:10px 12px;border-radius:8px;border:1px solid var(--color-border);
                 background:${r.author_role === 'admin' ? 'var(--color-bg-muted)' : 'var(--color-bg)'}">
                <div style="font-size:0.72rem;color:var(--color-text-muted);margin-bottom:4px">
                    ${r.author_role === 'admin' ? 'Academy Administration' : escapeHtml(t.sender_name || 'Sender')}
                    · ${formatDateTime(r.created_at)}</div>
                <div style="font-size:0.9rem;line-height:1.6;white-space:pre-wrap">${escapeHtml(r.body)}</div>
            </div>`).join('');
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">${escapeHtml(t.subject)}</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.82rem;color:var(--color-text-secondary)">
                    From <strong>${escapeHtml(t.sender_name || '—')}</strong> (${escapeHtml(t.sender_role || '')})
                    · ${formatDateTime(t.created_at)}
                    ${t.related_student_name ? ' · Student: ' + escapeHtml(t.related_student_name) + ' (' + escapeHtml(t.related_student_cma || '') + ')' : ''}
                    · ${SUPPORT_STATUS_LABEL[t.status] || t.status}</p>
                <div style="margin:10px 0;padding:10px 12px;border-radius:8px;border:1px solid var(--color-border)">
                    <div style="font-size:0.9rem;line-height:1.6;white-space:pre-wrap">${escapeHtml(t.message)}</div></div>
                <div style="max-height:32vh;overflow:auto">${replies}</div>
                <div class="admin-modal__field"><label class="auth__label">Reply (appears in the sender's portal)</label>
                    <textarea class="auth__input" id="sppReply" rows="3"></textarea></div>
                <p id="sppError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Close</button>
                ${t.status !== 'resolved' ? `<button class="btn btn--secondary" onclick="Admin.setSupportStatus('${id}','resolved')">Mark Resolved</button>` : ''}
                <button class="btn btn--primary" onclick="Admin.replySupport('${id}')">Send Reply</button>
            </div>`);
    }

    async function replySupport(id) {
        const err = document.getElementById('sppError');
        const body = ((document.getElementById('sppReply') || {}).value || '').trim();
        if (!body) {
            if (err) { err.textContent = 'Write a reply first.'; err.style.display = 'block'; }
            return;
        }
        try {
            await apiV1Call(`/admin/support/${id}/reply`, { method: 'POST', body: JSON.stringify({ body }) });
            closeModalDirect();
            showToast('Reply sent — the sender has been notified.', 'success');
            openSupportThread(id);
            renderSupportInbox();
        } catch (e) { if (err) { err.textContent = e.message; err.style.display = 'block'; } }
    }

    async function setSupportStatus(id, status) {
        try {
            await apiV1Call(`/admin/support/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) });
            closeModalDirect();
            showToast('Conversation marked resolved.', 'success');
            renderSupportInbox();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Achievements — verified showcase records
    // ========================================
    const ACH_CATEGORIES = ['exam', 'recital', 'competition', 'certification', 'award', 'milestone'];

    async function renderAchievementsAdmin() {
        const container = document.getElementById('adminContent');
        container.innerHTML = '<div class="admin-loading"><div class="admin-loading__spinner"></div>Loading achievements...</div>';
        try {
            const rows = await apiV1Call('/admin/achievements');
            const trs = (rows || []).map(a => `
                <tr>
                    <td><strong>${escapeHtml(a.student_name || '—')}</strong></td>
                    <td>${escapeHtml(a.title)}
                        <div style="font-size:0.75rem;color:var(--color-text-muted)">${escapeHtml([a.awarding_body, a.programme_id, a.grade_level].filter(Boolean).join(' · '))}</div></td>
                    <td>${escapeHtml(a.category)}</td>
                    <td>${escapeHtml(a.result || '—')}</td>
                    <td>${a.achieved_on ? formatDate(a.achieved_on) : '—'}</td>
                    <td>${a.is_verified
                        ? '<span class="badge badge--approved">Verified</span>'
                        : '<span class="badge badge--pending">Awaiting verification</span>'}
                        ${a.is_archived ? '<span class="badge badge--cancelled">Archived</span>' : ''}</td>
                    <td>
                        ${!a.is_verified ? `<button class="btn btn--primary btn--sm" onclick="Admin.verifyAchievement('${a.id}', true)">Verify</button>` : ''}
                        ${a.is_verified ? `<button class="btn btn--secondary btn--sm" onclick="Admin.verifyAchievement('${a.id}', false)">Unpublish</button>` : ''}
                        <button class="btn btn--secondary btn--sm" onclick="Admin.archiveAchievement('${a.id}', ${a.is_archived ? 'false' : 'true'})">${a.is_archived ? 'Restore' : 'Archive'}</button>
                    </td>
                </tr>`).join('');
            container.innerHTML = `
                <div class="admin-header">
                    <div>
                        <h1 class="admin-header__title">Achievements</h1>
                        <p class="admin-header__subtitle">Verified exams, distinctions, recitals and awards — shown on the student's profile once verified</p>
                    </div>
                    <button class="btn btn--primary" onclick="Admin.newAchievement()">+ Add Achievement</button>
                </div>
                <div class="admin-card"><div class="admin-card__body" style="padding:0">
                ${trs ? `<table class="admin-table"><thead><tr>
                    <th>Student</th><th>Achievement</th><th>Category</th><th>Result</th><th>Date</th><th>Status</th><th></th>
                </tr></thead><tbody>${trs}</tbody></table>` : `
                    <div class="admin-empty"><div class="admin-empty__icon">${icon('medal')}</div>
                    <div class="admin-empty__title">No achievements recorded</div>
                    <div class="admin-empty__text">Add verified examination results, distinctions, recitals or awards</div></div>`}
                </div></div>`;
        } catch (e) {
            container.innerHTML = `<div class="admin-empty"><div class="admin-empty__icon">${icon('warn')}</div><div class="admin-empty__title">Unable to load achievements</div><div class="admin-empty__text">${escapeHtml(e.message)}</div></div>`;
        }
    }

    async function newAchievement() {
        const students = await apiCall('/students');
        showModal(`
            <div class="admin-modal__header"><h3 class="admin-modal__title">Add Achievement</h3></div>
            <div class="admin-modal__body">
                <p style="font-size:0.82rem;color:var(--color-text-secondary)">Only enter results the academy has verified — never estimated or assumed outcomes.
                Historical achievements from earlier cohorts can be entered when reliable records exist.</p>
                <div class="admin-modal__field"><label class="auth__label">Student</label>
                    <select class="auth__input" id="acStudent">
                    ${(students || []).map(st => `<option value="${st.id}">${escapeHtml(st.full_name)}</option>`).join('')}
                    </select></div>
                <div class="admin-modal__field"><label class="auth__label">Title</label><input class="auth__input" id="acTitle" placeholder="Trinity Grade 2 Piano"></div>
                <div class="admin-modal__field"><label class="auth__label">Category</label>
                    <select class="auth__input" id="acCategory">${ACH_CATEGORIES.map(c => `<option value="${c}">${c}</option>`).join('')}</select></div>
                <div class="admin-modal__field"><label class="auth__label">Exam board / awarding body</label><input class="auth__input" id="acBoard" placeholder="Trinity, Rockschool…"></div>
                <div class="admin-modal__field"><label class="auth__label">Instrument / course</label><input class="auth__input" id="acProgramme" placeholder="piano"></div>
                <div class="admin-modal__field"><label class="auth__label">Grade / level</label><input class="auth__input" id="acGrade" placeholder="Grade 2"></div>
                <div class="admin-modal__field"><label class="auth__label">Result / award</label><input class="auth__input" id="acResult" placeholder="Distinction, Merit, Winner…"></div>
                <div class="admin-modal__field"><label class="auth__label">Date achieved</label><input class="auth__input" type="date" id="acDate"></div>
                <div class="admin-modal__field"><label class="auth__label">Description (optional)</label><textarea class="auth__input" id="acDescription" rows="2"></textarea></div>
                <p id="acError" class="auth__error" style="display:none"></p>
            </div>
            <div class="admin-modal__footer">
                <button class="btn btn--secondary" onclick="Admin.closeModalDirect()">Cancel</button>
                <button class="btn btn--primary" onclick="Admin.saveAchievement()">Save (unverified)</button>
            </div>`);
    }

    async function saveAchievement() {
        const err = document.getElementById('acError');
        const payload = {
            student_id: (document.getElementById('acStudent').value || '').trim(),
            title: (document.getElementById('acTitle').value || '').trim(),
            category: document.getElementById('acCategory').value,
            awarding_body: (document.getElementById('acBoard').value || '').trim() || null,
            programme_id: (document.getElementById('acProgramme').value || '').trim() || null,
            grade_level: (document.getElementById('acGrade').value || '').trim() || null,
            result: (document.getElementById('acResult').value || '').trim() || null,
            achieved_on: (document.getElementById('acDate').value || '') || null,
            description: (document.getElementById('acDescription').value || '').trim() || null,
        };
        if (!payload.student_id || payload.title.length < 2) {
            err.textContent = 'Student and title are required.'; err.style.display = 'block'; return;
        }
        try {
            await apiV1Call('/admin/achievements', { method: 'POST', body: JSON.stringify(payload) });
            closeModalDirect();
            showToast('Achievement saved — verify it to publish it to the student.', 'success');
            renderAchievementsAdmin();
        } catch (e) { err.textContent = e.message; err.style.display = 'block'; }
    }

    async function verifyAchievement(id, is_verified) {
        try {
            await apiV1Call(`/admin/achievements/${id}`, { method: 'PATCH', body: JSON.stringify({ is_verified }) });
            showToast(is_verified ? 'Achievement verified — now visible to the family.' : 'Achievement unpublished.', 'success');
            renderAchievementsAdmin();
        } catch (e) { alert(e.message); }
    }

    async function archiveAchievement(id, is_archived) {
        try {
            await apiV1Call(`/admin/achievements/${id}`, { method: 'PATCH', body: JSON.stringify({ is_archived }) });
            showToast(is_archived ? 'Achievement archived.' : 'Achievement restored.', 'success');
            renderAchievementsAdmin();
        } catch (e) { alert(e.message); }
    }

    // ========================================
    // Render
    // ========================================
    function render() {
        const layout = document.getElementById('adminLayout');
        if (!layout) return;

        layout.innerHTML = `
            ${renderSidebar()}
            <main class="admin-main" id="adminContent"></main>
            <button class="admin-sidebar__toggle" id="adminSidebarToggle" aria-label="Toggle navigation">${icon("menu")}</button>
        `;

        bindSidebarEvents();

        switch (currentSection) {
            case 'dashboard': renderDashboard(); break;
            case 'registrations':
                if (regState.currentView === 'detail' && regState.selectedRequest) {
                    renderRegDetail();
                } else {
                    loadRegistrations();
                }
                break;
            case 'students': renderStudents(); break;
            case 'enrollments': renderEnrollments(); break;
            case 'instructors': renderInstructors(); break;
            case 'classes': renderClasses(); break;
            case 'fees': renderFees(); break;
            case 'attendance': renderAttendance(); break;
            case 'progress': renderProgress(); break;
            case 'exams': renderExams(); break;
            case 'assignments': renderAssignments(); break;
            case 'resources': renderResources(); break;
            case 'reports': renderReports(); break;
            case 'achievements': renderAchievementsAdmin(); break;
            case 'support': renderSupportInbox(); break;
            case 'syllabi': renderSyllabiAdmin(); break;
            case 'class-reports': renderClassReports(); break;
            case 'reschedule-requests': renderRescheduleQueue(); break;
            case 'pin-resets': renderPinResets(); break;
            case 'settings': renderSettings(); break;
            default: renderDashboard();
        }
    }

    // ========================================
    // Public API
    // ========================================
    return {
        init() {
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') closeModalDirect();
            });
            render();
        },
        navigateTo(section) {
            navigateTo(section);
        },
        viewRegistration(id) {
            viewRegistration(id);
        },
        loadRegistrations() {
            loadRegistrations();
        },
        backToList() {
            backToList();
        },
        filterByStatus(status) {
            filterByStatus(status);
        },
        clearRegFilters() {
            clearRegFilters();
        },
        showApproveModal(id) {
            showApproveModal(id);
        },
        confirmApprove(id) {
            confirmApprove(id);
        },
        showRejectModal(id) {
            showRejectModal(id);
        },
        confirmReject(id) {
            confirmReject(id);
        },
        showRequestInfoModal(id) {
            showRequestInfoModal(id);
        },
        filterClasses(status) {
            filterClasses(status);
        },
        filterFees(status) {
            filterFees(status);
        },
        selectAttendanceStudent(id) {
            selectAttendanceStudent(id);
        },
        showExamModal() {
            showExamModal();
        },
        confirmExam() {
            confirmExam();
        },
        editExam(id) {
            editExam(id);
        },
        confirmExamUpdate(id) {
            confirmExamUpdate(id);
        },
        showMilestoneModal() {
            showMilestoneModal();
        },
        confirmMilestone() {
            confirmMilestone();
        },
        showAssignmentModal() {
            showAssignmentModal();
        },
        confirmAssignment() {
            confirmAssignment();
        },
        showResourceModal() {
            showResourceModal();
        },
        confirmResource() {
            confirmResource();
        },
        showReportModal() {
            showReportModal();
        },
        confirmReport() {
            confirmReport();
        },
        publishReport(id) {
            publishReport(id);
        },
        showPackageModal(code) {
            showPackageModal(code);
        },
        confirmPackage() {
            confirmPackage();
        },
        confirmRequestInfo(id) {
            confirmRequestInfo(id);
        },
        openStudentWorkspace(id) {
            openStudentWorkspace(id);
        },
        resetPin(studentId) {
            resetPin(studentId);
        },
        renderRescheduleQueue() {
            renderRescheduleQueue();
        },
        renderClassReports() {
            renderClassReports();
        },
        renderSyllabiAdmin() {
            renderSyllabiAdmin();
        },
        toggleResourceScope() {
            toggleResourceScope();
        },
        shiftFeeMonth(d) {
            shiftFeeMonth(d);
        },
        setFeeFilter(k, v) {
            setFeeFilter(k, v);
        },
        feeRecordPayment(id) {
            feeRecordPayment(id);
        },
        confirmFeePayment() {
            confirmFeePayment();
        },
        feeCreateCharge() {
            feeCreateCharge();
        },
        confirmFeeCharge() {
            confirmFeeCharge();
        },
        feeAdvance() {
            feeAdvance();
        },
        confirmFeeAdvance() {
            confirmFeeAdvance();
        },
        feeApplyCredit() {
            feeApplyCredit();
        },
        feeCreditInvoiceRefresh() {
            feeCreditInvoiceRefresh();
        },
        confirmFeeCredit() {
            confirmFeeCredit();
        },
        feeInvoiceDetail(id) {
            feeInvoiceDetail(id);
        },
        feeConfirmPayment(id) {
            feeConfirmPayment(id);
        },
        feeRejectPayment(id) { feeRejectPayment(id); },
        feeRejectSubmit(id) { feeRejectSubmit(id); },
        feeClarifyPayment(id) { feeClarifyPayment(id); },
        feeClarifySubmit(id) { feeClarifySubmit(id); },
        claimReasonChanged() { claimReasonChanged(); },
        confirmFeePaymentSubmit(id) {
            confirmFeePaymentSubmit(id);
        },
        feeReverseAllocation(id) {
            feeReverseAllocation(id);
        },
        feeVoidInvoice(id) {
            feeVoidInvoice(id);
        },
        feeViewReceipt(id) {
            feeViewReceipt(id);
        },
        feeExport() {
            feeExport();
        },
        feeGenerateCharges() {
            feeGenerateCharges();
        },
        examFeeCreate() {
            examFeeCreate();
        },
        confirmExamFee() {
            confirmExamFee();
        },
        examFeeAcademyPayment(id) {
            examFeeAcademyPayment(id);
        },
        examFeeReimburse(id) {
            examFeeReimburse(id);
        },
        renderSupportInbox() {
            renderSupportInbox();
        },
        renderAchievementsAdmin() {
            renderAchievementsAdmin();
        },
        newAchievement() {
            newAchievement();
        },
        saveAchievement() {
            saveAchievement();
        },
        verifyAchievement(id, flag) {
            verifyAchievement(id, flag);
        },
        archiveAchievement(id, flag) {
            archiveAchievement(id, flag);
        },
        openSupportThread(id) {
            openSupportThread(id);
        },
        replySupport(id) {
            replySupport(id);
        },
        setSupportStatus(id, status) {
            setSupportStatus(id, status);
        },
        newSyllabus() {
            newSyllabus();
        },
        saveSyllabus() {
            saveSyllabus();
        },
        addSyllabusItem(id) {
            addSyllabusItem(id);
        },
        saveSyllabusItem(id) {
            saveSyllabusItem(id);
        },
        assignSyllabus(id) {
            assignSyllabus(id);
        },
        confirmAssignSyllabus(id) {
            confirmAssignSyllabus(id);
        },
        setSyllabusAssignment(sid, aid, status) {
            setSyllabusAssignment(sid, aid, status);
        },
        applyClassReportFilters() {
            applyClassReportFilters();
        },
        clearClassReportFilters() {
            clearClassReportFilters();
        },
        approveReschedule(id) {
            approveReschedule(id);
        },
        confirmApproveReschedule(id) {
            confirmApproveReschedule(id);
        },
        rejectReschedule(id) {
            rejectReschedule(id);
        },
        confirmRejectReschedule(id) {
            confirmRejectReschedule(id);
        },
        renderPinResets() {
            renderPinResets();
        },
        approvePinReset(id) {
            approvePinReset(id);
        },
        rejectPinReset(id) {
            rejectPinReset(id);
        },
        confirmRejectPinReset(id) {
            confirmRejectPinReset(id);
        },
        provisionStudent(id) {
            provisionStudent(id);
        },
        createStudentModal() {
            createStudentModal();
        },
        submitCreateStudent() {
            submitCreateStudent();
        },
        editStudentModal(id) {
            editStudentModal(id);
        },
        submitEditStudent(id) {
            submitEditStudent(id);
        },
        setStudentStatus(id, st) {
            setStudentStatus(id, st);
        },
        archiveStudent(id) {
            archiveStudent(id);
        },
        deleteStudentPermanently(id) {
            deleteStudentPermanently(id);
        },
        previewLoginId() { previewLoginId(); },
        wsScPreview() { wsScPreview(); },
        wsScApply() { wsScApply(); },
        wsScInvalidate() { wsScInvalidate(); },
        wsChangeMonth(v) { wsChangeMonth(v); },
        wsMonthlyReload() { wsMonthlyReload(); },
        wsAddSlot() { wsAddSlot(); },
        wsRemoveSlot(ix) { wsRemoveSlot(ix); },
        wsGenerateWeekly() { wsGenerateWeekly(); },
        wsSaveMonthly() { wsSaveMonthly(); },
        createInstructorModal() {
            createInstructorModal();
        },
        submitCreateInstructor() {
            submitCreateInstructor();
        },
        editInstructorModal(id) {
            editInstructorModal(id);
        },
        submitEditInstructor(id) {
            submitEditInstructor(id);
        },
        deactivateInstructor(id) {
            deactivateInstructor(id);
        },
        confirmDeactivateInstructor(id) {
            confirmDeactivateInstructor(id);
        },
        setInstructorActive(id, active) {
            setInstructorActive(id, active);
        },
        assignInstructor(enrollmentId, day, start, end) {
            assignInstructor(enrollmentId, day, start, end);
        },
        assignInstructorForEnrollment(enrollmentId) {
            assignInstructorForEnrollment(enrollmentId);
        },
        wsSetStatus(id, status) {
            wsSetStatus(id, status);
        },
        moveSession(id) {
            moveSession(id);
        },
        wsEditEnrollment(enrollmentId) {
            wsEditEnrollment(enrollmentId);
        },
        wsSaveEnrollment(enrollmentId) {
            wsSaveEnrollment(enrollmentId);
        },
        wsAddEnrollment(studentId) {
            wsAddEnrollment(studentId);
        },
        wsSaveNewEnrollment(studentId) {
            wsSaveNewEnrollment(studentId);
        },
        checkAssignAvailability() {
            checkAssignAvailability();
        },
        confirmAssignInstructor() {
            confirmAssignInstructor();
        },
        closeStudentWorkspace() {
            closeStudentWorkspace();
        },
        setWsTab(tab) {
            setWsTab(tab);
        },
        showRemarkModal(id) {
            showRemarkModal(id);
        },
        confirmRemark() {
            confirmRemark();
        },
        showRemarkHistory(id) {
            showRemarkHistory(id);
        },
        closeModal(e) {
            closeModal(e);
        },
        closeModalDirect() {
            closeModalDirect();
        },
    };
})();
