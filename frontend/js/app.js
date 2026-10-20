/* ============================================
   ChankArts Music Academy - Application
   Learn. Create. Perform.
   ============================================ */

(function() {
    'use strict';

    // ========================================
    // Course Catalogue (Data-driven)
    // ========================================
    const COURSE_CATALOGUE = [
        {
            category: 'Piano / Keyboard',
            programmes: [
                { id: 'piano', name: 'Piano' },
                { id: 'electronic_keyboard', name: 'Electronic Keyboard' }
            ]
        },
        {
            category: 'Guitar',
            programmes: [
                { id: 'acoustic_guitar', name: 'Acoustic Guitar' },
                { id: 'electric_guitar', name: 'Electric Guitar' },
                { id: 'bass_guitar', name: 'Bass Guitar' }
            ]
        },
        {
            category: 'Indian Classical',
            programmes: [
                { id: 'indian_bansuri', name: 'Indian Bansuri' }
            ]
        },
        {
            category: 'Other Programmes',
            programmes: [
                { id: 'ukulele', name: 'Ukulele' },
                { id: 'western_vocals', name: 'Western Vocals' },
                { id: 'music_theory', name: 'Music Theory / Foundation Music Theory' }
            ]
        }
    ];

    // ========================================
    // Configuration
    // ========================================
    // window.CHANKARTS_API_BASE overrides everything (set in index.html when
    // the API lives on a different origin); otherwise local dev hits
    // localhost:8000 and production uses same-origin /api/* (proxied).
    const API_BASE = window.CHANKARTS_API_BASE !== undefined
        ? window.CHANKARTS_API_BASE
        : (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
            ? 'http://localhost:8000'
            : '');  // Production: same origin (reverse proxy routes /api/* to the API)

    // Base path: '/academy' in production, '/chankarts-academy' on GitHub Pages,
    // '' when served at the domain root. Set by the inline script in index.html
    // (before stylesheets); fall back to the same detection if absent.
    const BASE_PATH = (function () {
        if (typeof window.__APP_BASE === 'string') return window.__APP_BASE;
        const segments = ['login', 'register', 'forgot-password', 'admin',
            'registration-success', 'verify-email', 'portal'];
        const seg = window.location.pathname.split('/')[1] || '';
        return (!seg || segments.indexOf(seg) >= 0) ? '' : '/' + seg;
    })();

    // Canonical internal route keys always use the '/academy' prefix so that
    // existing links, redirects and templates keep working. These two helpers
    // translate between the canonical key and the real mounted URL.
    function toCanonical(path) {
        const rest = BASE_PATH && path.indexOf(BASE_PATH) === 0 ? path.slice(BASE_PATH.length) : path;
        return '/academy' + (rest === '' ? '/' : rest);
    }

    function toReal(canonical) {
        const rest = canonical.indexOf('/academy') === 0 ? canonical.slice('/academy'.length) : canonical;
        return (BASE_PATH + (rest === '' ? '/' : rest)) || '/';
    }

    // Shared with admin.js / portal.js for hard redirects and pathname reads.
    window.AppPath = toReal;
    window.AppCanonical = toCanonical;

    const CONFIG = {
        apiBase: API_BASE,
        routes: {
            '/academy/': 'home',
            '/academy/login': 'login',
            '/academy/register': 'register',
            '/academy/forgot-password': 'forgot-password',
            '/academy/admin': 'admin',
            '/academy/admin/': 'admin',
            '/academy/registration-success': 'registration-success',
            '/academy/verify-email': 'verify-email',
            '/academy/portal': 'portal',
            '/academy/portal/': 'portal',
            '/academy/portal/dashboard': 'portal',
            '/academy/portal/classes': 'portal',
            '/academy/portal/billing': 'portal',
            '/academy/portal/assignments': 'portal',
            '/academy/portal/materials': 'portal',
            '/academy/portal/reports': 'portal',
            '/academy/portal/syllabus': 'portal',
            '/academy/portal/exams': 'portal',
            '/academy/portal/resources': 'portal',
            '/academy/portal/profile': 'portal',
            '/academy/portal/help': 'portal',
        },
        defaultRoute: '/academy/'
    };

    // ========================================
    // Registration State
    // ========================================
    const registrationState = {
        currentStep: 1,
        totalSteps: 4,
        submitting: false,
        data: {
            // Step 1: Account
            fullName: '',
            email: '',
            mobile: '',
            // Step 2: Student Details
            dateOfBirth: '',
            isMinor: false,
            address: '',
            // Guardian fields
            guardianName: '',
            guardianRelationship: '',
            guardianEmail: '',
            guardianMobile: '',
            // Step 3: Programmes
            selectedProgrammes: []
        }
    };

    // ========================================
    // State
    // ========================================
    const state = {
        currentRoute: null,
        isAuthenticated: false,
        user: null
    };

    // ========================================
    // Router
    // ========================================
    const Router = {
        init() {
            window.addEventListener('popstate', () => this.handleRoute());
            document.addEventListener('click', (e) => {
                const link = e.target.closest('a');
                if (!link) return;
                const href = link.getAttribute('href') || '';
                if (href.indexOf('/academy') !== 0) return;
                // portal's own logo link has a dedicated handler (portal.go)
                if (link.hasAttribute('data-portal-home')) return;
                e.preventDefault();
                this.navigate(href);
            });
            this.handleRoute();
        },

        navigate(route) {
            window.history.pushState({}, '', toReal(route));
            this.handleRoute();
        },

        handleRoute() {
            const path = toCanonical(window.location.pathname);
            const page = CONFIG.routes[path] || 'home';
            
            if (state.currentRoute === page) return;
            
            state.currentRoute = page;
            this.render(page);
            this.updateActiveLinks(page);
        },

        render(page) {
            const main = document.getElementById('mainContent');
            main.innerHTML = '';
            document.body.classList.toggle('body--portal', page === 'portal');
            document.body.classList.toggle('body--admin', page === 'admin');
            
            const content = Pages[page]();
            if (content) {
                main.appendChild(content);
            }
        },

        updateActiveLinks(page) {
            document.querySelectorAll('[data-route]').forEach(link => {
                const route = link.dataset.route;
                link.classList.toggle('header__nav-link--active', route === page);
            });
        }
    };

    // ========================================
    // Utility Functions
    // ========================================
    function calculateAge(dateOfBirth) {
        const today = new Date();
        const birthDate = new Date(dateOfBirth);
        let age = today.getFullYear() - birthDate.getFullYear();
        const monthDiff = today.getMonth() - birthDate.getMonth();
        if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birthDate.getDate())) {
            age--;
        }
        return age;
    }

    function showError(id) {
        const el = document.getElementById(id);
        if (el) el.classList.add('auth__error--visible');
    }

    function hideError(id) {
        const el = document.getElementById(id);
        if (el) el.classList.remove('auth__error--visible');
    }

    function clearAllErrors() {
        document.querySelectorAll('.auth__error').forEach(el => {
            el.classList.remove('auth__error--visible');
        });
    }

    // ========================================
    // Registration Step Renderers
    // ========================================
    function renderStep1() {
        return `
            <div class="reg__step" data-step="1">
                <div class="reg__step-header">
                    <h2 class="reg__step-title">Account Details</h2>
                    <p class="reg__step-subtitle">Create your Academy account credentials</p>
                </div>
                <div class="reg__fields">
                    <div class="auth__field">
                        <label class="auth__label" for="regFullName">Full Name <span class="reg__required">*</span></label>
                        <input 
                            type="text" 
                            id="regFullName" 
                            class="auth__input" 
                            placeholder="Enter your full name"
                            autocomplete="name"
                            value="${registrationState.data.fullName}"
                        >
                        <span class="auth__error" id="regFullNameError">Please enter your full name</span>
                    </div>
                    <div class="auth__field">
                        <label class="auth__label" for="regEmail">Email Address <span class="reg__required">*</span></label>
                        <input 
                            type="email" 
                            id="regEmail" 
                            class="auth__input" 
                            placeholder="you@example.com"
                            autocomplete="email"
                            value="${registrationState.data.email}"
                        >
                        <span class="auth__error" id="regEmailError">Please enter a valid email</span>
                    </div>
                    <div class="auth__field">
                        <label class="auth__label" for="regMobile">Mobile Number <span class="reg__required">*</span></label>
                        <input 
                            type="tel" 
                            id="regMobile" 
                            class="auth__input" 
                            placeholder="+91 XXXXX XXXXX"
                            autocomplete="tel"
                            value="${registrationState.data.mobile}"
                        >
                        <span class="auth__error" id="regMobileError">Please enter a valid mobile number</span>
                    </div>
                    <div class="auth__field">
                        <p style="font-size:13px;color:var(--muted);line-height:1.6">
                            No password is needed here. This is an application only — after the academy
                            confirms your enrolment, you will receive your Roll Number and a temporary
                            PIN, and choose your own PIN at first sign-in.
                        </p>
                    </div>
                </div>
            </div>
        `;
    }

    function renderStep2() {
        const isMinor = registrationState.data.isMinor;
        return `
            <div class="reg__step" data-step="2">
                <div class="reg__step-header">
                    <h2 class="reg__step-title">Student Details</h2>
                    <p class="reg__step-subtitle">Tell us about the student</p>
                </div>
                <div class="reg__fields">
                    <div class="auth__field">
                        <label class="auth__label" for="regDOB">Date of Birth <span class="reg__required">*</span></label>
                        <input 
                            type="date" 
                            id="regDOB" 
                            class="auth__input" 
                            value="${registrationState.data.dateOfBirth}"
                        >
                        <span class="auth__error" id="regDOBError">Please enter a valid date of birth</span>
                    </div>
                    <div class="auth__field">
                        <label class="auth__label" for="regAddress">Address</label>
                        <textarea 
                            id="regAddress" 
                            class="auth__input auth__textarea" 
                            placeholder="Enter your address (optional)"
                            rows="3"
                        >${registrationState.data.address}</textarea>
                    </div>
                    
                    <div class="reg__guardian-section" id="guardianSection" style="display: ${isMinor ? 'block' : 'none'}">
                        <div class="reg__guardian-header">
                            <h3 class="reg__guardian-title">Parent/Guardian Information</h3>
                            <p class="reg__guardian-subtitle">Required for students under 18 years</p>
                        </div>
                        <div class="auth__field">
                            <label class="auth__label" for="regGuardianName">Parent/Guardian Name <span class="reg__required">*</span></label>
                            <input 
                                type="text" 
                                id="regGuardianName" 
                                class="auth__input" 
                                placeholder="Enter parent/guardian name"
                                value="${registrationState.data.guardianName}"
                            >
                            <span class="auth__error" id="regGuardianNameError">Parent/guardian name is required for minors</span>
                        </div>
                        <div class="auth__field">
                            <label class="auth__label" for="regGuardianRelationship">Relationship <span class="reg__required">*</span></label>
                            <select id="regGuardianRelationship" class="auth__input auth__select">
                                <option value="">Select relationship</option>
                                <option value="parent" ${registrationState.data.guardianRelationship === 'parent' ? 'selected' : ''}>Parent</option>
                                <option value="guardian" ${registrationState.data.guardianRelationship === 'guardian' ? 'selected' : ''}>Guardian</option>
                                <option value="other" ${registrationState.data.guardianRelationship === 'other' ? 'selected' : ''}>Other</option>
                            </select>
                            <span class="auth__error" id="regGuardianRelError">Please select a relationship</span>
                        </div>
                        <div class="auth__field">
                            <label class="auth__label" for="regGuardianEmail">Parent/Guardian Email</label>
                            <input 
                                type="email" 
                                id="regGuardianEmail" 
                                class="auth__input" 
                                placeholder="guardian@example.com"
                                value="${registrationState.data.guardianEmail}"
                            >
                            <span class="auth__error" id="regGuardianEmailError">Please enter a valid email</span>
                        </div>
                        <div class="auth__field">
                            <label class="auth__label" for="regGuardianMobile">Parent/Guardian Mobile <span class="reg__required">*</span></label>
                            <input 
                                type="tel" 
                                id="regGuardianMobile" 
                                class="auth__input" 
                                placeholder="+91 XXXXX XXXXX"
                                value="${registrationState.data.guardianMobile}"
                            >
                            <span class="auth__error" id="regGuardianMobileError">Parent/guardian mobile is required for minors</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    function renderStep3() {
        const selected = registrationState.data.selectedProgrammes;
        return `
            <div class="reg__step" data-step="3">
                <div class="reg__step-header">
                    <h2 class="reg__step-title">What Would You Like to Learn?</h2>
                    <p class="reg__step-subtitle">Select one or more programmes</p>
                </div>
                <div class="reg__programmes">
                    <p class="reg__programmes-note">
                        You can choose more than one programme. Your Academy account and CMA Registration ID will remain the same.
                    </p>
                    
                    ${selected.length > 0 ? `
                        <div class="reg__selected">
                            <h4 class="reg__selected-title">Selected Programmes</h4>
                            <div class="reg__selected-list">
                                ${selected.map(p => `
                                    <span class="reg__selected-item">
                                        ${p.name}
                                        <button type="button" class="reg__selected-remove" data-id="${p.id}" aria-label="Remove ${p.name}">×</button>
                                    </span>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="reg__categories">
                        ${COURSE_CATALOGUE.map(cat => `
                            <div class="reg__category">
                                <h3 class="reg__category-title">${cat.category}</h3>
                                <div class="reg__category-programmes">
                                    ${cat.programmes.map(prog => {
                                        const isSelected = selected.some(p => p.id === prog.id);
                                        return `
                                            <button type="button" class="reg__programme ${isSelected ? 'reg__programme--selected' : ''}" data-id="${prog.id}" data-name="${prog.name}">
                                                <span class="reg__programme-check">${isSelected ? '✓' : ''}</span>
                                                <span class="reg__programme-name">${prog.name}</span>
                                            </button>
                                        `;
                                    }).join('')}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    <span class="auth__error" id="regProgrammeError">Please select at least one programme</span>
                </div>
            </div>
        `;
    }

    function renderStep4() {
        const { data } = registrationState;
        const programmes = data.selectedProgrammes.map(p => p.name).join(', ');
        return `
            <div class="reg__step" data-step="4">
                <div class="reg__step-header">
                    <h2 class="reg__step-title">Review Your Details</h2>
                    <p class="reg__step-subtitle">Please confirm your information before creating your account</p>
                </div>
                <div class="reg__review">
                    <div class="reg__review-section">
                        <h3 class="reg__review-title">Account Information</h3>
                        <div class="reg__review-row">
                            <span class="reg__review-label">Name</span>
                            <span class="reg__review-value">${data.fullName}</span>
                        </div>
                        <div class="reg__review-row">
                            <span class="reg__review-label">Email</span>
                            <span class="reg__review-value">${data.email}</span>
                        </div>
                        <div class="reg__review-row">
                            <span class="reg__review-label">Mobile</span>
                            <span class="reg__review-value">${data.mobile}</span>
                        </div>
                    </div>
                    
                    <div class="reg__review-section">
                        <h3 class="reg__review-title">Student Details</h3>
                        <div class="reg__review-row">
                            <span class="reg__review-label">Date of Birth</span>
                            <span class="reg__review-value">${new Date(data.dateOfBirth).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}</span>
                        </div>
                        <div class="reg__review-row">
                            <span class="reg__review-label">Age</span>
                            <span class="reg__review-value">${calculateAge(data.dateOfBirth)} years</span>
                        </div>
                        ${data.address ? `
                            <div class="reg__review-row">
                                <span class="reg__review-label">Address</span>
                                <span class="reg__review-value">${data.address}</span>
                            </div>
                        ` : ''}
                        ${data.isMinor ? `
                            <div class="reg__review-section reg__review-section--nested">
                                <h4 class="reg__review-title reg__review-title--sub">Parent/Guardian</h4>
                                <div class="reg__review-row">
                                    <span class="reg__review-label">Name</span>
                                    <span class="reg__review-value">${data.guardianName}</span>
                                </div>
                                <div class="reg__review-row">
                                    <span class="reg__review-label">Relationship</span>
                                    <span class="reg__review-value">${data.guardianRelationship}</span>
                                </div>
                                ${data.guardianEmail ? `
                                    <div class="reg__review-row">
                                        <span class="reg__review-label">Email</span>
                                        <span class="reg__review-value">${data.guardianEmail}</span>
                                    </div>
                                ` : ''}
                                <div class="reg__review-row">
                                    <span class="reg__review-label">Mobile</span>
                                    <span class="reg__review-value">${data.guardianMobile}</span>
                                </div>
                            </div>
                        ` : ''}
                    </div>
                    
                    <div class="reg__review-section">
                        <h3 class="reg__review-title">Selected Programmes</h3>
                        <div class="reg__review-programmes">
                            ${data.selectedProgrammes.map(p => `
                                <span class="reg__review-programme">✓ ${p.name}</span>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    // ========================================
    // Pages
    // ========================================
    const Pages = {
        home() {
            const div = document.createElement('div');
            div.className = 'page';
            div.innerHTML = `
                <section class="hero">
                    <div class="hero__bg"></div>
                    <div class="hero__content">
                        <img src="assets/ChankArts Music Academy.png" alt="ChankArts Music Academy" class="hero__logo">
                        <div class="hero__badge">
                            <span class="hero__badge-dot"></span>
                            Now Enrolling
                        </div>
                        <h1 class="hero__title">
                            Welcome to
                            <span class="hero__title-accent">ChankArts Music Academy</span>
                        </h1>
                        <p class="hero__tagline">Learn. Create. Perform.</p>
                        <p class="hero__description">
                            Your digital learning space for music education. Access courses, track your progress,
                            connect with instructors, and pursue your musical journey with Trinity and Rockschool certifications.
                        </p>
                        <div class="hero__actions">
                            <a href="/academy/login" class="btn btn--primary btn--large" data-route="login">
                                Login to Academy
                            </a>
                        </div>
                        <div class="hero__features">
                            <div class="hero__feature">
                                <div class="hero__feature-icon">🎵</div>
                                <h3 class="hero__feature-title">Learn</h3>
                                <p class="hero__feature-text">Access structured courses in piano, guitar, vocals, and more</p>
                            </div>
                            <div class="hero__feature">
                                <div class="hero__feature-icon">✨</div>
                                <h3 class="hero__feature-title">Create</h3>
                                <p class="hero__feature-text">Work on projects, compose music, and develop your artistry</p>
                            </div>
                            <div class="hero__feature">
                                <div class="hero__feature-icon">🎤</div>
                                <h3 class="hero__feature-title">Perform</h3>
                                <p class="hero__feature-text">Prepare for exams, certifications, and live performances</p>
                            </div>
                        </div>
                    </div>
                </section>
            `;
            return div;
        },

        login() {
            const div = document.createElement('div');
            div.className = 'page';
            div.innerHTML = `
                <section class="auth">
                    <div class="auth__bg"></div>
                    <div class="auth__container">
                        <div class="auth__card">
                            <div class="auth__header">
                                <img src="assets/ChankArts Music Academy.png" alt="ChankArts Music Academy" class="auth__header-logo">
                                <h1 class="auth__title">Welcome Back</h1>
                                <p class="auth__subtitle">Sign in to your academy account</p>
                            </div>
                            <form class="auth__form" id="loginForm">
                                <div class="auth__field">
                                    <label class="auth__label" for="loginEmail">Roll No. / Login ID</label>
                                    <input 
                                        type="text" 
                                        id="loginEmail" 
                                        class="auth__input" 
                                        placeholder="Enter your Roll No. / Login ID"
                                        autocomplete="username"
                                        autocapitalize="off"
                                        spellcheck="false"
                                        required
                                    >
                                    <span class="auth__error" id="loginEmailError">Please enter your Roll No. / Login ID</span>
                                </div>
                                <div class="auth__field">
                                    <label class="auth__label" for="loginPassword">PIN</label>
                                    <div class="auth__password-wrapper">
                                        <input 
                                            type="password" 
                                            id="loginPassword" 
                                            class="auth__input" 
                                            placeholder="Enter your PIN"
                                            autocomplete="current-password"
                                            inputmode="numeric"
                                            required
                                        >
                                        <button type="button" class="auth__password-toggle" id="togglePassword">Show</button>
                                    </div>
                                    <span class="auth__error" id="loginPasswordError">PIN is required</span>
                                </div>
                                <div class="auth__forgot">
                                    <a href="/academy/forgot-password" class="auth__forgot-link" data-route="forgot-password">Forgot PIN?</a>
                                </div>
                                <button type="submit" class="btn btn--primary btn--full btn--large">Sign In</button>
                            </form>
                            <div class="auth__footer">
                                Accounts are created by the academy administrator.
                            </div>
                        </div>
                    </div>
                </section>
            `;
            
            setTimeout(() => {
                const form = div.querySelector('#loginForm');
                const toggleBtn = div.querySelector('#togglePassword');
                
                if (form) form.addEventListener('submit', handleLogin);
                if (toggleBtn) {
                    toggleBtn.addEventListener('click', () => {
                        const passwordInput = div.querySelector('#loginPassword');
                        const type = passwordInput.type === 'password' ? 'text' : 'password';
                        passwordInput.type = type;
                        toggleBtn.textContent = type === 'password' ? 'Show' : 'Hide';
                    });
                }
            }, 0);
            
            return div;
        },

        register() {
            // Private academy LMS: no public self-registration.
            // Student accounts are provisioned by the administrator.
            const div = document.createElement('div');
            div.className = 'page';
            div.innerHTML = `
                <section class="auth">
                    <div class="auth__bg"></div>
                    <div class="auth__container">
                        <div class="auth__card">
                            <div class="auth__header">
                                <img src="assets/ChankArts Music Academy.png" alt="ChankArts Music Academy" class="auth__header-logo">
                                <h1 class="auth__title">Registration by Invitation</h1>
                                <p class="auth__subtitle">ChankArts Music Academy is a private academy</p>
                            </div>
                            <p style="color: var(--color-text-secondary); font-size: 0.92rem; line-height: 1.65; text-align: center;">
                                Student accounts and Roll Numbers are created by the academy
                                administrator. If you are an enrolled student, sign in with your
                                Roll No. / Login ID and PIN.
                            </p>
                            <div style="margin-top: 24px;">
                                <a href="/academy/login" class="btn btn--primary btn--full btn--large" data-route="login">Go to Login</a>
                            </div>
                        </div>
                    </div>
                </section>
            `;
            return div;
        },

        'forgot-password'() {
            // Admin-managed PIN recovery — email reset links were removed by policy
            const div = document.createElement('div');
            div.className = 'page';
            div.innerHTML = `
                <section class="auth">
                    <div class="auth__bg"></div>
                    <div class="auth__container">
                        <div class="auth__card">
                            <div class="auth__header">
                                <img src="assets/ChankArts Music Academy.png" alt="ChankArts Music Academy" class="auth__header-logo">
                                <h1 class="auth__title">Request PIN Reset</h1>
                                <p class="auth__subtitle">Forgotten your PIN? The academy will help you get back in.</p>
                            </div>
                            <div id="pinResetConfirm" style="display:none">
                                <p style="color: var(--color-text-secondary); font-size: 0.95rem; line-height: 1.7; text-align:center">
                                    Your request has been received. The academy will contact you using your
                                    registered contact details.
                                </p>
                                <div style="margin-top: 20px">
                                    <a href="/academy/login" class="btn btn--primary btn--full btn--large" data-route="login">Back to Login</a>
                                </div>
                            </div>
                            <form class="auth__form" id="pinResetForm">
                                <div class="auth__field">
                                    <label class="auth__label" for="pinResetUser">Roll No. / Login ID</label>
                                    <input
                                        type="text"
                                        id="pinResetUser"
                                        class="auth__input"
                                        placeholder="Enter your Roll No. / Login ID"
                                        autocomplete="username"
                                        autocapitalize="off"
                                        spellcheck="false"
                                        required
                                    >
                                    <span class="auth__error" id="pinResetUserError">Please enter your Roll No. / Login ID</span>
                                </div>
                                <div class="auth__field">
                                    <label class="auth__label" for="pinResetContact">Registered contact</label>
                                    <input
                                        type="text"
                                        id="pinResetContact"
                                        class="auth__input"
                                        placeholder="Phone number or email registered with the academy"
                                        required
                                    >
                                    <span class="auth__error" id="pinResetContactError">Please provide a contact the academy can reply to</span>
                                </div>
                                <div class="auth__field">
                                    <label class="auth__label" for="pinResetDetails">Details (optional)</label>
                                    <textarea
                                        id="pinResetDetails"
                                        class="auth__input"
                                        rows="3"
                                        placeholder="Anything that helps us verify your request"
                                    ></textarea>
                                </div>
                                <button type="submit" class="btn btn--primary btn--full btn--large">Submit Request</button>
                            </form>
                            <div class="auth__footer">
                                Remember your PIN?
                                <a href="/academy/login" class="auth__footer-link" data-route="login">Sign in</a>
                            </div>
                        </div>
                    </div>
                </section>
            `;

            setTimeout(() => {
                const form = div.querySelector('#pinResetForm');
                if (form) form.addEventListener('submit', handlePinResetRequest);
            }, 0);

            return div;
        },

        admin() {
            // Check authentication
            const token = localStorage.getItem('academy_token');
            const user = JSON.parse(localStorage.getItem('academy_user') || '{}');
            
            if (!token || user.role !== 'admin') {
                // Redirect to login
                window.location.href = window.AppPath('/academy/login');
                return document.createElement('div');
            }
            
            const div = document.createElement('div');
            div.className = 'page admin-page';
            div.innerHTML = `
                <div class="admin-layout" id="adminLayout"></div>
            `;
            
            setTimeout(() => {
                if (needsPinChange()) {
                    renderForcedPinChange(div, () => {
                        div.innerHTML = '<div class="admin-layout" id="adminLayout"></div>';
                        if (typeof Admin !== 'undefined') Admin.init();
                    });
                    return;
                }
                if (typeof Admin !== 'undefined') {
                    Admin.init();
                }
            }, 0);
            
            return div;
        },

        portal() {
            const token = localStorage.getItem('academy_token');
            const user = JSON.parse(localStorage.getItem('academy_user') || '{}');

            if (!token || ['student', 'parent', 'instructor'].indexOf(user.role) < 0) {
                window.location.href = window.AppPath('/academy/login');
                return document.createElement('div');
            }

            const div = document.createElement('div');
            div.className = 'page portal-page';
            div.innerHTML = '<div id="portalRoot"></div>';

            setTimeout(() => {
                if (needsPinChange()) {
                    renderForcedPinChange(div, () => {
                        div.innerHTML = '<div id="portalRoot"></div>';
                        if (typeof Portal !== 'undefined') Portal.init();
                    });
                    return;
                }
                if (typeof Portal !== 'undefined') {
                    Portal.init();
                }
            }, 0);

            return div;
        },

        'verify-email'() {
            const div = document.createElement('div');
            div.className = 'page';
            
            // Get token from URL query params
            const urlParams = new URLSearchParams(window.location.search);
            const token = urlParams.get('token');
            const email = urlParams.get('email');
            
            if (!token && !email) {
                // No token or email provided - show request form
                div.innerHTML = `
                    <section class="auth">
                        <div class="auth__bg"></div>
                        <div class="auth__container" style="max-width: 480px;">
                            <div class="auth__card">
                                <div class="auth__header">
                                    <img src="assets/ChankArts Music Academy.png" alt="ChankArts Music Academy" class="auth__header-logo">
                                    <h1 class="auth__title">Verify Your Email</h1>
                                    <p class="auth__subtitle">Enter your email to receive a verification link</p>
                                </div>
                                <form class="auth__form" id="verifyRequestForm">
                                    <div class="auth__field">
                                        <label class="auth__label" for="verifyEmail">Email Address</label>
                                        <input 
                                            type="email" 
                                            id="verifyEmail" 
                                            class="auth__input" 
                                            placeholder="you@example.com"
                                            autocomplete="email"
                                            required
                                        >
                                        <span class="auth__error" id="verifyEmailError">Please enter a valid email</span>
                                    </div>
                                    <button type="submit" class="btn btn--primary btn--full btn--large">Send Verification Link</button>
                                </form>
                                <div class="auth__footer">
                                    <a href="/academy/login" class="auth__footer-link" data-route="login">Back to Login</a>
                                </div>
                            </div>
                        </div>
                    </section>
                `;
                
                setTimeout(() => {
                    const form = div.querySelector('#verifyRequestForm');
                    if (form) form.addEventListener('submit', handleVerifyRequest);
                }, 0);
                
                return div;
            }
            
            if (token) {
                // Token provided - verify the email
                div.innerHTML = `
                    <section class="auth">
                        <div class="auth__bg"></div>
                        <div class="auth__container" style="max-width: 480px;">
                            <div class="auth__card">
                                <div style="text-align: center; padding: 40px 20px;">
                                    <div style="width: 64px; height: 64px; background: rgba(74, 222, 128, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;">
                                        <span style="font-size: 28px; color: var(--color-success);">⟳</span>
                                    </div>
                                    <h2 style="font-family: var(--font-display); font-size: 1.25rem; margin: 0 0 12px; color: var(--color-text-primary);">Verifying Your Email...</h2>
                                    <p style="color: var(--color-text-secondary); font-size: 0.9rem;">Please wait while we verify your email address.</p>
                                </div>
                            </div>
                        </div>
                    </section>
                `;
                
                setTimeout(() => {
                    verifyEmailToken(token);
                }, 100);
                
                return div;
            }
            
            // Email provided but no token - show message to check inbox
            div.innerHTML = `
                <section class="auth">
                    <div class="auth__bg"></div>
                    <div class="auth__container" style="max-width: 480px;">
                        <div class="auth__card">
                            <div style="text-align: center; padding: 40px 20px;">
                                <div style="width: 64px; height: 64px; background: rgba(201, 169, 110, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;">
                                    <span style="font-size: 28px; color: var(--color-accent);">✉</span>
                                </div>
                                <h2 style="font-family: var(--font-display); font-size: 1.25rem; margin: 0 0 12px; color: var(--color-text-primary);">Check Your Inbox</h2>
                                <p style="color: var(--color-text-secondary); font-size: 0.9rem; line-height: 1.6; margin: 0 0 24px;">
                                    We've sent a verification link to<br>
                                    <strong style="color: var(--color-text-primary);">${escapeHtml(email)}</strong>
                                </p>
                                <p style="color: var(--color-text-muted); font-size: 0.85rem; margin: 0 0 24px;">
                                    Click the link in the email to verify your address. The link expires in 24 hours.
                                </p>
                                <a href="/academy/login" class="btn btn--primary" data-route="login" style="width: 100%; text-align: center;">Go to Login</a>
                            </div>
                        </div>
                    </div>
                </section>
            `;
            
            return div;
        }
    };

    // ========================================
    // Registration Logic
    // ========================================
    function initRegistration() {
        const prevBtn = document.getElementById('regPrev');
        const nextBtn = document.getElementById('regNext');
        const form = document.getElementById('registerForm');
        
        if (prevBtn) prevBtn.addEventListener('click', goToPrevStep);
        if (nextBtn) nextBtn.addEventListener('click', goToNextStep);
        if (form) form.addEventListener('submit', handleSubmit);
        
        // DOB change handler for minor detection
        const dobInput = document.getElementById('regDOB');
        if (dobInput) {
            dobInput.addEventListener('change', (e) => {
                const age = calculateAge(e.target.value);
                registrationState.data.isMinor = age < 18;
                const guardianSection = document.getElementById('guardianSection');
                if (guardianSection) {
                    guardianSection.style.display = registrationState.data.isMinor ? 'block' : 'none';
                }
            });
        }
        
        updateProgressUI();
    }

    function goToPrevStep() {
        if (registrationState.currentStep > 1) {
            saveCurrentStepData();
            registrationState.currentStep--;
            renderCurrentStep();
            updateProgressUI();
        }
    }

    function goToNextStep() {
        if (!validateCurrentStep()) return;
        
        saveCurrentStepData();
        
        if (registrationState.currentStep < registrationState.totalSteps) {
            registrationState.currentStep++;
            renderCurrentStep();
            updateProgressUI();
        } else if (registrationState.currentStep === registrationState.totalSteps) {
            // On last step - submit the form
            handleSubmit();
        }
    }

    function renderCurrentStep() {
        const stepsContainer = document.getElementById('regSteps');
        const prevBtn = document.getElementById('regPrev');
        const nextBtn = document.getElementById('regNext');
        
        let stepHtml = '';
        switch (registrationState.currentStep) {
            case 1: stepHtml = renderStep1(); break;
            case 2: stepHtml = renderStep2(); break;
            case 3: stepHtml = renderStep3(); break;
            case 4: stepHtml = renderStep4(); break;
        }
        
        stepsContainer.innerHTML = stepHtml;
        
        // Update button visibility
        prevBtn.style.display = registrationState.currentStep > 1 ? 'inline-flex' : 'none';
        
        if (registrationState.currentStep === registrationState.totalSteps) {
            nextBtn.textContent = 'Create Academy Account';
            nextBtn.classList.add('btn--submit');
        } else {
            nextBtn.textContent = 'Continue';
            nextBtn.classList.remove('btn--submit');
        }
        
        // Re-attach event listeners for current step
        attachStepEventListeners();
    }

    function attachStepEventListeners() {
        const step = registrationState.currentStep;
        
        if (step === 2) {
            const dobInput = document.getElementById('regDOB');
            if (dobInput) {
                dobInput.addEventListener('change', (e) => {
                    const age = calculateAge(e.target.value);
                    registrationState.data.isMinor = age < 18;
                    const guardianSection = document.getElementById('guardianSection');
                    if (guardianSection) {
                        guardianSection.style.display = registrationState.data.isMinor ? 'block' : 'none';
                    }
                });
            }
        }
        
        if (step === 3) {
            // Programme selection
            document.querySelectorAll('.reg__programme').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = btn.dataset.id;
                    const name = btn.dataset.name;
                    toggleProgramme(id, name);
                    btn.classList.toggle('reg__programme--selected');
                    const check = btn.querySelector('.reg__programme-check');
                    check.textContent = btn.classList.contains('reg__programme--selected') ? '✓' : '';
                });
            });
            
            // Remove programme from selected list
            document.querySelectorAll('.reg__selected-remove').forEach(btn => {
                btn.addEventListener('click', () => {
                    const id = btn.dataset.id;
                    removeProgramme(id);
                    renderCurrentStep();
                });
            });
        }
    }

    function toggleProgramme(id, name) {
        const index = registrationState.data.selectedProgrammes.findIndex(p => p.id === id);
        if (index > -1) {
            registrationState.data.selectedProgrammes.splice(index, 1);
        } else {
            registrationState.data.selectedProgrammes.push({ id, name });
        }
        updateSelectedDisplay();
    }

    function removeProgramme(id) {
        registrationState.data.selectedProgrammes = registrationState.data.selectedProgrammes.filter(p => p.id !== id);
    }

    function updateSelectedDisplay() {
        const selected = registrationState.data.selectedProgrammes;
        const selectedContainer = document.querySelector('.reg__selected');
        
        if (selected.length > 0) {
            if (selectedContainer) {
                selectedContainer.querySelector('.reg__selected-list').innerHTML = selected.map(p => `
                    <span class="reg__selected-item">
                        ${p.name}
                        <button type="button" class="reg__selected-remove" data-id="${p.id}" aria-label="Remove ${p.name}">×</button>
                    </span>
                `).join('');
                
                // Re-attach remove handlers
                selectedContainer.querySelectorAll('.reg__selected-remove').forEach(btn => {
                    btn.addEventListener('click', () => {
                        removeProgramme(btn.dataset.id);
                        renderCurrentStep();
                    });
                });
            } else {
                renderCurrentStep();
            }
        }
    }

    function saveCurrentStepData() {
        const step = registrationState.currentStep;
        
        if (step === 1) {
            registrationState.data.fullName = document.getElementById('regFullName')?.value || '';
            registrationState.data.email = document.getElementById('regEmail')?.value || '';
            registrationState.data.mobile = document.getElementById('regMobile')?.value || '';
        } else if (step === 2) {
            registrationState.data.dateOfBirth = document.getElementById('regDOB')?.value || '';
            registrationState.data.address = document.getElementById('regAddress')?.value || '';
            if (registrationState.data.isMinor) {
                registrationState.data.guardianName = document.getElementById('regGuardianName')?.value || '';
                registrationState.data.guardianRelationship = document.getElementById('regGuardianRelationship')?.value || '';
                registrationState.data.guardianEmail = document.getElementById('regGuardianEmail')?.value || '';
                registrationState.data.guardianMobile = document.getElementById('regGuardianMobile')?.value || '';
            }
        }
    }

    function validateCurrentStep() {
        clearAllErrors();
        const step = registrationState.currentStep;
        let isValid = true;
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        
        if (step === 1) {
            const fullName = document.getElementById('regFullName')?.value.trim();
            const email = document.getElementById('regEmail')?.value.trim();
            const mobile = document.getElementById('regMobile')?.value.trim();
            
            if (!fullName || fullName.length < 2) {
                showError('regFullNameError');
                isValid = false;
            }
            
            if (!email || !emailRegex.test(email)) {
                showError('regEmailError');
                isValid = false;
            }
            
            const mobileRegex = /^[\+]?[(]?[0-9]{10,15}$/;
            if (!mobile || !mobileRegex.test(mobile.replace(/[\s\-\(\)]/g, ''))) {
                showError('regMobileError');
                isValid = false;
            }
            
        } else if (step === 2) {
            const dob = document.getElementById('regDOB')?.value;
            
            if (!dob) {
                showError('regDOBError');
                isValid = false;
            }
            
            if (registrationState.data.isMinor) {
                const guardianName = document.getElementById('regGuardianName')?.value.trim();
                const guardianRel = document.getElementById('regGuardianRelationship')?.value;
                const guardianMobile = document.getElementById('regGuardianMobile')?.value.trim();
                
                if (!guardianName) {
                    showError('regGuardianNameError');
                    isValid = false;
                }
                
                if (!guardianRel) {
                    showError('regGuardianRelError');
                    isValid = false;
                }
                
                if (!guardianMobile) {
                    showError('regGuardianMobileError');
                    isValid = false;
                }
                
                const guardianEmail = document.getElementById('regGuardianEmail')?.value.trim();
                if (guardianEmail && !emailRegex.test(guardianEmail)) {
                    showError('regGuardianEmailError');
                    isValid = false;
                }
            }
        } else if (step === 3) {
            if (registrationState.data.selectedProgrammes.length === 0) {
                showError('regProgrammeError');
                isValid = false;
            }
        }
        
        return isValid;
    }

    function handleSubmit(e) {
        if (e) e.preventDefault();
        
        if (!validateCurrentStep()) return;
        
        saveCurrentStepData();
        
        // Prevent duplicate submissions
        if (registrationState.submitting) return;
        registrationState.submitting = true;
        
        // Disable submit button to prevent double submission
        const submitBtn = document.getElementById('regNext');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Submitting Your Application...';
            submitBtn.style.opacity = '0.7';
            submitBtn.style.cursor = 'wait';
        }
        
        // Submit to backend
        const payload = {
            fullName: registrationState.data.fullName,
            email: registrationState.data.email,
            mobile: registrationState.data.mobile,
            dateOfBirth: registrationState.data.dateOfBirth,
            isMinor: registrationState.data.isMinor,
            address: registrationState.data.address || null,
            guardianName: registrationState.data.isMinor ? registrationState.data.guardianName : null,
            guardianRelationship: registrationState.data.isMinor ? registrationState.data.guardianRelationship : null,
            guardianEmail: registrationState.data.isMinor ? registrationState.data.guardianEmail : null,
            guardianMobile: registrationState.data.isMinor ? registrationState.data.guardianMobile : null,
            selectedProgrammes: registrationState.data.selectedProgrammes,
        };
        
        fetch(CONFIG.apiBase + '/api/v1/registration-requests', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        })
        .then(res => {
            if (!res.ok) {
                return res.json().then(data => {
                    throw new Error(data.detail || 'Registration failed');
                }).catch(parseErr => {
                    if (parseErr.message && parseErr.message !== 'Registration failed') throw parseErr;
                    throw new Error('Registration failed. Please try again.');
                });
            }
            return res.json();
        })
        .then(data => {
            registrationState.submitting = false;
            showRegistrationSuccess(data);
        })
        .catch(err => {
            console.error('Registration error:', err);
            registrationState.submitting = false;
            
            // Re-enable submit button
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Create Academy Account';
                submitBtn.style.opacity = '';
                submitBtn.style.cursor = '';
            }
            
            // Show user-friendly error message
            showRegistrationError(err.message);
        });
    }

    function showRegistrationError(message) {
        const main = document.getElementById('mainContent');
        const existingError = main.querySelector('.reg-error-overlay');
        if (existingError) existingError.remove();
        
        const overlay = document.createElement('div');
        overlay.className = 'reg-error-overlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(15,15,23,0.9);display:flex;align-items:center;justify-content:center;z-index:1000;padding:20px;';
        
        overlay.innerHTML = `
            <div style="background:var(--color-bg-secondary);border-radius:var(--radius-lg);padding:40px;max-width:480px;width:100%;text-align:center;border:1px solid rgba(248,113,113,0.3);">
                <div style="width:64px;height:64px;background:rgba(248,113,113,0.15);border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 20px;font-size:28px;color:var(--color-error);">✕</div>
                <h2 style="font-family:var(--font-display);font-size:1.25rem;margin:0 0 12px;color:var(--color-text-primary);">Registration Issue</h2>
                <p style="color:var(--color-text-secondary);font-size:0.9rem;line-height:1.6;margin:0 0 24px;">${escapeHtml(message)}</p>
                <button onclick="this.closest('.reg-error-overlay').remove()" style="background:var(--color-accent);color:#0f0f17;border:none;padding:12px 32px;border-radius:var(--radius-sm);font-weight:600;cursor:pointer;font-size:0.95rem;">Try Again</button>
            </div>
        `;
        
        main.appendChild(overlay);
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function showRegistrationSuccess(data) {
        const main = document.getElementById('mainContent');
        main.innerHTML = `
            <section class="auth">
                <div class="auth__bg"></div>
                <div class="auth__container" style="max-width: 560px;">
                    <div class="auth__card">
                        <div style="text-align: center; margin-bottom: 32px;">
                            <div style="width: 80px; height: 80px; background: rgba(74, 222, 128, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 24px; font-size: 36px; color: #4ade80;">✓</div>
                            <h1 style="font-family: var(--font-display); font-size: 1.75rem; margin-bottom: 8px; color: var(--color-text-primary);">Academy Account Created</h1>
                            <p style="color: var(--color-text-secondary); font-size: 0.95rem;">Welcome to ChankArts Music Academy, <strong style="color: var(--color-text-primary);">${escapeHtml(registrationState.data.fullName)}</strong></p>
                        </div>
                        
                        <div style="background: var(--color-bg-secondary); border-radius: var(--radius-md); padding: 24px; margin-bottom: 24px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                                <span style="color: var(--color-text-muted); font-size: 0.85rem;">Application ID</span>
                                <span style="font-weight: 600; color: var(--color-accent);">${data.request_id}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                                <span style="color: var(--color-text-muted); font-size: 0.85rem;">Submitted</span>
                                <span style="font-weight: 500;">${new Date(data.submitted_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                                <span style="color: var(--color-text-muted); font-size: 0.85rem;">Status</span>
                                <span class="badge badge--pending">Pending Approval</span>
                            </div>
                            <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0;">
                                <span style="color: var(--color-text-muted); font-size: 0.85rem;">Expected Review</span>
                                <span style="font-weight: 500;">Within 72 hours</span>
                            </div>
                        </div>
                        
                        <div style="background: rgba(201, 169, 110, 0.08); border-left: 3px solid var(--color-accent); border-radius: 0 var(--radius-md) var(--radius-md) 0; padding: 16px; margin-bottom: 24px;">
                            <p style="color: var(--color-text-secondary); font-size: 0.9rem; line-height: 1.6; margin: 0;">
                                Your registration has been successfully submitted. Our Academy team will review your application within 72 hours.
                            </p>
                        </div>
                        
                        <div style="background: rgba(74, 222, 128, 0.08); border-left: 3px solid var(--color-success); border-radius: 0 var(--radius-md) var(--radius-md) 0; padding: 16px; margin-bottom: 24px;">
                            <p style="color: var(--color-text-secondary); font-size: 0.9rem; line-height: 1.6; margin: 0;">
                                We've sent a verification email to <strong style="color: var(--color-text-primary);">${escapeHtml(registrationState.data.email)}</strong>. Please check your inbox and verify your email address.
                            </p>
                        </div>
                        
                        <p style="color: var(--color-text-muted); font-size: 0.85rem; text-align: center; margin-bottom: 24px;">
                            You do not need to submit the registration form again.
                        </p>
                        
                        <div style="text-align: center; display: flex; flex-direction: column; gap: 12px;">
                            <a href="/academy/verify-email?email=${encodeURIComponent(registrationState.data.email)}" class="btn btn--primary" data-route="verify-email" style="width: 100%; text-align: center;">
                                Verify Email
                            </a>
                            <a href="/academy/login" class="btn btn--secondary" data-route="login" style="width: 100%; text-align: center;">
                                Go to Academy Login
                            </a>
                        </div>
                    </div>
                </div>
            </section>
        `;
        
        // Reset registration state
        registrationState.currentStep = 1;
        registrationState.submitting = false;
        registrationState.data = {
            fullName: '',
            email: '',
            mobile: '',
            dateOfBirth: '',
            isMinor: false,
            address: '',
            guardianName: '',
            guardianRelationship: '',
            guardianEmail: '',
            guardianMobile: '',
            selectedProgrammes: [],
        };
    }

    function updateProgressUI() {
        const steps = document.querySelectorAll('.reg__progress-step');
        const lines = document.querySelectorAll('.reg__progress-line');
        
        steps.forEach((step, index) => {
            const stepNum = index + 1;
            step.classList.remove('reg__progress-step--active', 'reg__progress-step--completed');
            
            if (stepNum === registrationState.currentStep) {
                step.classList.add('reg__progress-step--active');
            } else if (stepNum < registrationState.currentStep) {
                step.classList.add('reg__progress-step--completed');
            }
        });
        
        lines.forEach((line, index) => {
            line.classList.toggle('reg__progress-line--completed', index + 1 < registrationState.currentStep);
        });
    }

    // ========================================
    // Form Handlers
    // ========================================
    function handleLogin(e) {
        e.preventDefault();
        
        const email = document.getElementById('loginEmail').value.trim();
        const password = document.getElementById('loginPassword').value;
        
        let isValid = true;
        
        if (!email) {
            showError('loginEmailError');
            isValid = false;
        } else {
            hideError('loginEmailError');
        }
        
        if (!password) {
            showError('loginPasswordError');
            isValid = false;
        } else {
            hideError('loginPasswordError');
        }
        
        if (isValid) {
            // Try to connect to backend
            fetch(CONFIG.apiBase + '/api/v1/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password }),
            })
            .then(res => {
                if (!res.ok) throw new Error('Login failed');
                return res.json();
            })
            .then(data => {
                // Store token and user info
                localStorage.setItem('academy_token', data.access_token);
                localStorage.setItem('academy_user', JSON.stringify({
                    role: data.role,
                    user_id: data.user_id,
                    name: data.name || '',
                    email: data.email || data.username || '',
                    must_change_pin: !!data.must_change_pin,
                }));

                syncAuthNav();
                
                // Route based on role
                switch (data.role) {
                    case 'admin':
                        Router.navigate('/academy/admin');
                        break;
                    case 'instructor':
                        Router.navigate('/academy/portal');
                        break;
                    case 'parent':
                        Router.navigate('/academy/portal');
                        break;
                    default:
                        Router.navigate('/academy/portal');
                }
            })
            .catch(err => {
                console.error('Login error:', err);
                alert('Login failed. Check your Roll No. / Login ID and PIN.');
            });
        }
    }

    function handlePinResetRequest(e) {
        e.preventDefault();

        const username = document.getElementById('pinResetUser').value.trim();
        const contact = document.getElementById('pinResetContact').value.trim();
        const details = (document.getElementById('pinResetDetails') || {}).value || '';

        let valid = true;
        if (!username) { showError('pinResetUserError'); valid = false; } else hideError('pinResetUserError');
        if (!contact) { showError('pinResetContactError'); valid = false; } else hideError('pinResetContactError');
        if (!valid) return;

        fetch(CONFIG.apiBase + '/api/v1/auth/pin-reset-request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, contact, details: details.trim() }),
        })
        .then(res => res.json().catch(() => ({})))
        .then(() => {
            // Identical confirmation regardless of account existence (no enumeration)
            const form = document.getElementById('pinResetForm');
            const confirm = document.getElementById('pinResetConfirm');
            if (form) form.style.display = 'none';
            if (confirm) confirm.style.display = 'block';
        })
        .catch(() => {
            const confirm = document.getElementById('pinResetConfirm');
            const form = document.getElementById('pinResetForm');
            if (form) form.style.display = 'none';
            if (confirm) confirm.style.display = 'block';
        });
    }

    function handleVerifyRequest(e) {
        e.preventDefault();
        
        const email = document.getElementById('verifyEmail').value.trim();
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        
        if (!email || !emailRegex.test(email)) {
            showError('verifyEmailError');
            return;
        }
        
        hideError('verifyEmailError');
        
        const submitBtn = e.target.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Sending...';
        }
        
            fetch(CONFIG.apiBase + '/api/v1/verify-email/request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
        })
        .then(res => {
            if (!res.ok) throw new Error('Failed to send verification email');
            return res.json();
        })
        .then(data => {
            // Show confirmation that email was sent
            const main = document.getElementById('mainContent');
            main.innerHTML = `
                <section class="auth">
                    <div class="auth__bg"></div>
                    <div class="auth__container" style="max-width: 480px;">
                        <div class="auth__card">
                            <div style="text-align: center; padding: 40px 20px;">
                                <div style="width: 64px; height: 64px; background: rgba(74, 222, 128, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;">
                                    <span style="font-size: 28px; color: var(--color-success);">✓</span>
                                </div>
                                <h2 style="font-family: var(--font-display); font-size: 1.25rem; margin: 0 0 12px; color: var(--color-text-primary);">Email Sent</h2>
                                <p style="color: var(--color-text-secondary); font-size: 0.9rem; line-height: 1.6; margin: 0 0 24px;">
                                    We've sent a verification link to<br>
                                    <strong style="color: var(--color-text-primary);">${escapeHtml(email)}</strong>
                                </p>
                                <p style="color: var(--color-text-muted); font-size: 0.85rem; margin: 0 0 24px;">
                                    Click the link in the email to verify your address. The link expires in 24 hours.
                                </p>
                                <a href="/academy/login" class="btn btn--primary" data-route="login" style="width: 100%; text-align: center;">Go to Login</a>
                            </div>
                        </div>
                    </div>
                </section>
            `;
        })
        .catch(err => {
            console.error('Verification request error:', err);
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Send Verification Link';
            }
            alert('Failed to send verification email. Please try again.');
        });
    }

    function verifyEmailToken(token) {
            fetch(CONFIG.apiBase + '/api/v1/verify-email/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token }),
        })
        .then(res => {
            if (!res.ok) throw new Error('Verification failed');
            return res.json();
        })
        .then(data => {
            // Show success
            const main = document.getElementById('mainContent');
            main.innerHTML = `
                <section class="auth">
                    <div class="auth__bg"></div>
                    <div class="auth__container" style="max-width: 480px;">
                        <div class="auth__card">
                            <div style="text-align: center; padding: 40px 20px;">
                                <div style="width: 64px; height: 64px; background: rgba(74, 222, 128, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;">
                                    <span style="font-size: 28px; color: var(--color-success);">✓</span>
                                </div>
                                <h2 style="font-family: var(--font-display); font-size: 1.25rem; margin: 0 0 12px; color: var(--color-text-primary);">Email Verified</h2>
                                <p style="color: var(--color-text-secondary); font-size: 0.9rem; line-height: 1.6; margin: 0 0 24px;">
                                    Your email address has been successfully verified. Your registration is now pending Academy approval.
                                </p>
                                <a href="/academy/login" class="btn btn--primary" data-route="login" style="width: 100%; text-align: center;">Go to Login</a>
                            </div>
                        </div>
                    </div>
                </section>
            `;
        })
        .catch(err => {
            console.error('Verification error:', err);
            const main = document.getElementById('mainContent');
            main.innerHTML = `
                <section class="auth">
                    <div class="auth__bg"></div>
                    <div class="auth__container" style="max-width: 480px;">
                        <div class="auth__card">
                            <div style="text-align: center; padding: 40px 20px;">
                                <div style="width: 64px; height: 64px; background: rgba(248, 113, 113, 0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;">
                                    <span style="font-size: 28px; color: var(--color-error);">✕</span>
                                </div>
                                <h2 style="font-family: var(--font-display); font-size: 1.25rem; margin: 0 0 12px; color: var(--color-text-primary);">Verification Failed</h2>
                                <p style="color: var(--color-text-secondary); font-size: 0.9rem; line-height: 1.6; margin: 0 0 24px;">
                                    The verification link is invalid or has expired. Please request a new one.
                                </p>
                                <a href="/academy/verify-email" class="btn btn--primary" data-route="verify-email" style="width: 100%; text-align: center;">Request New Link</a>
                            </div>
                        </div>
                    </div>
                </section>
            `;
        });
    }

    // ========================================
    // Header
    // ========================================
    // ========================================
    // Auth-aware header
    // ========================================
    function syncAuthNav() {
        const nav = document.getElementById('mainNav');
        const mobileNav = document.querySelector('#mobileMenu .mobile-menu__nav');

        const token = localStorage.getItem('academy_token');
        let user = {};
        try { user = JSON.parse(localStorage.getItem('academy_user') || '{}'); } catch (e) { user = {}; }

        // Remove any previously injected auth block
        const existing = nav && nav.querySelector('.header__user');
        if (existing) existing.remove();

        const loginLink = nav && nav.querySelector('[data-route="login"]');
        const registerLink = nav && nav.querySelector('[data-route="register"]');
        const mLogin = mobileNav && mobileNav.querySelector('[data-route="login"]');
        const mRegister = mobileNav && mobileNav.querySelector('[data-route="register"]');

        if (token && user.role) {
            // Logged in: hide Login/Register, show user chip + logout
            [loginLink, registerLink, mLogin, mRegister].forEach(el => { if (el) el.style.display = 'none'; });

            const displayName = user.name || (user.role ? user.role.charAt(0).toUpperCase() + user.role.slice(1) : 'Account');
            const initial = (user.name || user.role || 'A').charAt(0).toUpperCase();

            if (nav) {
                const authBlock = document.createElement('div');
                authBlock.className = 'header__user';
                authBlock.innerHTML = `
                    <span class="header__user-chip">
                        <span class="header__user-avatar">${initial}</span>
                        <span>${displayName}</span>
                    </span>
                    <button type="button" class="header__logout" id="headerLogoutBtn">Log out</button>
                `;
                nav.appendChild(authBlock);

                const logoutBtn = authBlock.querySelector('#headerLogoutBtn');
                if (logoutBtn) {
                    logoutBtn.addEventListener('click', () => {
                        localStorage.removeItem('academy_token');
                        localStorage.removeItem('academy_user');
                        syncAuthNav();
                        Router.navigate('/academy/');
                    });
                }
            }

            if (mobileNav && !mobileNav.querySelector('.mobile-menu__logout')) {
                const mLogout = document.createElement('a');
                mLogout.href = '#';
                mLogout.className = 'mobile-menu__link mobile-menu__logout';
                mLogout.textContent = 'Log out';
                mLogout.addEventListener('click', (e) => {
                    e.preventDefault();
                    localStorage.removeItem('academy_token');
                    localStorage.removeItem('academy_user');
                    syncAuthNav();
                    Router.navigate('/academy/');
                });
                mobileNav.appendChild(mLogout);
            }
        } else {
            // Logged out: show Login
            [loginLink, registerLink, mLogin, mRegister].forEach(el => { if (el) el.style.display = ''; });
            const mLogout = mobileNav && mobileNav.querySelector('.mobile-menu__logout');
            if (mLogout) mLogout.remove();
        }
    }

    // ========================================
    // Forced PIN change on first login
    // ========================================
    function needsPinChange() {
        try {
            const u = JSON.parse(localStorage.getItem('academy_user') || '{}');
            return !!u.must_change_pin;
        } catch (e) { return false; }
    }

    function clearPinChangeFlag() {
        try {
            const u = JSON.parse(localStorage.getItem('academy_user') || '{}');
            u.must_change_pin = false;
            localStorage.setItem('academy_user', JSON.stringify(u));
        } catch (e) { /* ignore */ }
    }

    // Renders the change-PIN screen into `mount`; calls onDone() after a
    // successful change so the caller can initialise admin/portal.
    function renderForcedPinChange(mount, onDone) {
        mount.innerHTML = `
            <div class="auth__container" style="margin:48px auto;">
                <div class="auth__card">
                    <div class="auth__header">
                        <h1 class="auth__title">Set your PIN</h1>
                        <p class="auth__subtitle">Your temporary PIN must be changed before you can continue.</p>
                    </div>
                    <form class="auth__form" id="forcedPinForm" novalidate>
                        <div class="auth__field">
                            <label class="auth__label" for="pinCurrent">Temporary PIN</label>
                            <input class="auth__input" id="pinCurrent" type="password" inputmode="numeric"
                                   maxlength="4" autocomplete="off" placeholder="••••" required>
                        </div>
                        <div class="auth__field">
                            <label class="auth__label" for="pinNew">New 4-digit PIN</label>
                            <input class="auth__input" id="pinNew" type="password" inputmode="numeric"
                                   maxlength="4" autocomplete="off" placeholder="••••" required>
                        </div>
                        <div class="auth__field">
                            <label class="auth__label" for="pinConfirm">Confirm new PIN</label>
                            <input class="auth__input" id="pinConfirm" type="password" inputmode="numeric"
                                   maxlength="4" autocomplete="off" placeholder="••••" required>
                        </div>
                        <p class="auth__error" id="pinChangeError" style="display:none;"></p>
                        <button type="submit" class="btn btn--primary btn--full btn--large">Set new PIN</button>
                    </form>
                </div>
            </div>
        `;

        const form = mount.querySelector('#forcedPinForm');
        const err = mount.querySelector('#pinChangeError');
        const show = (msg) => { err.textContent = msg; err.style.display = 'block'; };

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            err.style.display = 'none';
            const current = form.querySelector('#pinCurrent').value.trim();
            const next = form.querySelector('#pinNew').value.trim();
            const confirm = form.querySelector('#pinConfirm').value.trim();

            if (!/^\d{4}$/.test(current) || !/^\d{4}$/.test(next) || !/^\d{4}$/.test(confirm)) {
                return show('All PINs must be exactly four digits.');
            }
            if (next !== confirm) return show('New PINs do not match.');
            if (next === current) return show('New PIN must be different from the temporary PIN.');

            try {
                const token = localStorage.getItem('academy_token');
                const res = await fetch((CONFIG.apiBase || '') + '/api/v1/auth/change-pin', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        ...(token ? { Authorization: 'Bearer ' + token } : {}),
                    },
                    body: JSON.stringify({ current_pin: current, new_pin: next }),
                });
                if (!res.ok) {
                    const body = await res.json().catch(() => ({}));
                    return show(body.detail || 'Could not change PIN.');
                }
                clearPinChangeFlag();
                if (onDone) onDone();
            } catch (e2) {
                show('Connection error. Please try again.');
            }
        });
    }

    const Header = {
        init() {
            const header = document.getElementById('header');
            const menuBtn = document.getElementById('menuBtn');
            const mobileMenu = document.getElementById('mobileMenu');

            syncAuthNav();

            window.addEventListener('scroll', () => {
                header.classList.toggle('header--scrolled', window.scrollY > 20);
            });
            
            if (menuBtn && mobileMenu) {
                menuBtn.addEventListener('click', () => {
                    const isOpen = mobileMenu.classList.contains('mobile-menu--open');
                    mobileMenu.classList.toggle('mobile-menu--open');
                    menuBtn.classList.toggle('header__menu-btn--active');
                    menuBtn.setAttribute('aria-expanded', !isOpen);
                    document.body.style.overflow = isOpen ? '' : 'hidden';
                });
                
                mobileMenu.querySelectorAll('a').forEach(link => {
                    link.addEventListener('click', () => {
                        mobileMenu.classList.remove('mobile-menu--open');
                        menuBtn.classList.remove('header__menu-btn--active');
                        menuBtn.setAttribute('aria-expanded', 'false');
                        document.body.style.overflow = '';
                    });
                });
            }
        }
    };

    // ========================================
    // Initialize
    // ========================================
    document.addEventListener('DOMContentLoaded', () => {
        Header.init();
        Router.init();
    });

})();
