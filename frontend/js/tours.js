/* ChankArts — guided tours: welcome introduction, role-specific step lists,
 * first-login auto-launch and the Help & Support tutorial centre.
 *
 * State lives on the server (GET/PUT /api/v1/onboarding) so decisions follow
 * the account across devices; localStorage is never the source of truth.
 * Loaded after tour-engine.js and portal.js.
 */
window.Tours = (function () {
    'use strict';

    var BASE = (window.CHANKARTS_API_BASE !== undefined
        ? window.CHANKARTS_API_BASE
        : (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
            ? 'http://localhost:8000'
            : '')) + '/api/v1';

    // Bump when tour content changes substantially (mirrors backend constant).
    var CONTENT_VERSION = '2026-11-09';

    var state = null;           // server-side onboarding record
    var autoLaunchDone = false; // one auto-launch attempt per page load
    var running = false;        // a tour (full or topic) is on screen

    // ------------------------------------------------------------------
    // Server persistence
    // ------------------------------------------------------------------

    function token() {
        return localStorage.getItem('academy_token');
    }

    function storedRole() {
        try {
            var u = JSON.parse(localStorage.getItem('academy_user') || '{}');
            return u.role || null;
        } catch (e) { return null; }
    }

    async function api(path, options) {
        options = options || {};
        var headers = { 'Content-Type': 'application/json' };
        if (token()) headers.Authorization = 'Bearer ' + token();
        var response = await fetch(BASE + path, {
            method: options.method || 'GET',
            headers: headers,
            body: options.body ? JSON.stringify(options.body) : undefined,
        });
        if (!response.ok) throw new Error('onboarding request failed (' + response.status + ')');
        return response.json();
    }

    async function loadState() {
        state = await api('/onboarding');
        return state;
    }

    async function saveState(patch) {
        patch = Object.assign({ version: CONTENT_VERSION }, patch || {});
        try {
            state = await api('/onboarding', { method: 'PUT', body: patch });
        } catch (e) {
            console.warn('[tour] could not persist onboarding state', e);
            state = Object.assign({}, state || {}, patch);
        }
        return state;
    }

    // ------------------------------------------------------------------
    // Step definitions — built from the LIVE portal DOM (see portal.js).
    // Targets are fallback chains: specific element first, then the section
    // container, so a step never points at an unrelated element.
    // ------------------------------------------------------------------

    var STUDENT_STEPS = [
        {
            id: 'dashboard',
            section: 'dashboard',
            title: 'Your Learning Dashboard',
            text: 'Welcome to your learning dashboard. This is your starting point for checking your music classes, important updates and learning activities. Your account overview, upcoming classes and progress appear right here.',
            target: ['#portalSection .welcome', '#portalSection .grid--stats', '#portalSection'],
        },
        {
            id: 'notifications',
            section: 'dashboard',
            title: 'Notifications',
            text: 'Tap the bell in the top bar to see important updates — new assignments, material shared by your instructor, report publications and replies from the academy.',
            target: '.portal-bell',
        },
        {
            id: 'classes',
            section: 'classes',
            title: 'Your Class Schedule',
            text: 'Your class schedule is available here. Check the day, date and time of your upcoming music lessons — switch between Month, Week and List views. Review it regularly so you never miss a class. If you need to move a lesson, use Request Reschedule on an upcoming class (at least 24 hours in advance); the academy reviews every request.',
            target: ['#portalSection .tabs', '#portalSection .cal', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'assignments',
            section: 'assignments',
            title: 'Assignments & Quizzes',
            text: 'Your instructor may assign practice tasks, exercises or other learning activities here. Open an assignment to read the instructions and due date, review the learning material, upload your work before the deadline, and check submission status along with your instructor’s feedback.',
            target: ['#portalSection .tabs', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'materials',
            section: 'materials',
            title: 'Study Material',
            text: 'Your instructor shares useful study materials and learning resources here. Open the available documents and downloads to practise between your classes — filter by topic to find technique, repertoire or theory material quickly.',
            target: ['#portalSection .chips', '#portalSection .res-row', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'resources',
            section: 'resources',
            title: 'Resources & Learning Links',
            text: 'Books, instruments, accessories and useful external links — including YouTube practice videos — are collected here. Your instructor curates these recommendations for your programme, so check them when you practise at home.',
            target: ['#portalSection .tabs', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'syllabus',
            section: 'syllabus',
            title: 'Progress & Syllabus',
            text: 'Track your musical development here. You can see your assigned syllabus, review learning progress and understand which topics you have already covered and what comes next.',
            target: ['#portalSection .progress', '#portalSection .check-list', '#portalSection'],
        },
        {
            id: 'billing',
            section: 'billing',
            title: 'Fees & Payments',
            text: 'Your fee details are available here. Review your monthly charges, outstanding balance, previous payments and receipts, and use the available payment option to submit your fees. A payment claim is treated as pending until the academy verifies it.',
            target: ['#portalSection .tabs', '#portalSection .pack', '#portalSection'],
        },
        {
            id: 'help',
            section: 'help',
            title: 'Help & Support',
            text: 'Need assistance? Contact the Academy through this section. You can view messages and replies and ask for help regarding your classes or learning activities. Guided tutorials live here too — you can replay this tour any time.',
            target: ['#supSubject', '#portalSection .card', '#portalSection'],
        },
        {
            id: 'profile',
            section: 'profile',
            title: 'Profile & Account',
            text: 'Your personal account information lives here — your name, contact details and Login ID. You can also review and update your account security from this page. Your PIN is never shown anywhere in the portal.',
            target: ['#portalSection .card', '#portalSection'],
        },
    ];

    var INSTRUCTOR_STEPS = [
        {
            id: 'dashboard',
            section: 'dashboard',
            title: 'Instructor Dashboard',
            text: 'Welcome to your Instructor Dashboard. This is your workspace for managing assigned students, checking upcoming classes and staying updated with Academy activities.',
            target: ['#portalSection .welcome', '#portalSection .grid--stats', '#portalSection'],
        },
        {
            id: 'classes',
            section: 'classes',
            title: 'Class Schedule & Calendar',
            text: 'Your teaching timetable is available here. Check your assigned students, class dates and timings before each lesson — switch between Month, Week and List views, and see upcoming and completed classes.',
            target: ['#portalSection .tabs', '#portalSection .cal', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'mark-complete',
            section: 'classes',
            title: 'Marking a Class Completed',
            text: 'After completing a lesson, update its status here and record any relevant class remarks. Your completed teaching sessions help maintain accurate student records and teaching history. Completed classes stay protected — they can only be reopened by an administrator-approved undo.',
            target: ['button[data-action="complete-session"]', '#portalSection .list__row', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'students',
            section: 'dashboard',
            title: 'Your Assigned Students',
            text: 'Your assigned students appear on the dashboard and in your class list. Open a student’s permitted profile to view their instrument or programme, learning progress, syllabus information and class history — always within the access rules of your role.',
            target: ['#portalSection .card__title', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'assignments',
            section: 'assignments',
            title: 'Assignments & Learning Activities',
            text: 'Use this section to support your students’ independent practice. Create assignments, share learning instructions or practice tasks, review submitted work, provide feedback or corrections, and track pending versus reviewed submissions.',
            target: ['#portalSection .tabs', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'materials',
            section: 'materials',
            title: 'Resources & Teaching Materials',
            text: 'Access the Academy’s learning materials here. Upload and share learning links or documents where your permissions allow, and use existing resources to support your lessons and guide your students’ practice.',
            target: ['button[data-action="new-material"]', '#portalSection .chips', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'reports',
            section: 'reports',
            title: 'Progress, Reports & Remarks',
            text: 'Review student progress and prepare monthly reports here. Records you submit are reviewed and published by the Academy administration — you prepare and submit; publication stays with the admin team.',
            target: ['button[data-action="new-report"]', '#portalSection .list', '#portalSection'],
        },
        {
            id: 'help',
            section: 'help',
            title: 'Help & Support',
            text: 'Contact the Academy administration through this section. Read administrative messages, reply to them, and ask for assistance regarding scheduling, students or platform usage. Guided tutorials live here too.',
            target: ['#supSubject', '#portalSection .card', '#portalSection'],
        },
        {
            id: 'profile',
            section: 'profile',
            title: 'Profile & Account Security',
            text: 'Your profile information and assigned teaching details are shown here. You can review your account and use the existing PIN/security options from this page. Your PIN is never displayed.',
            target: ['#portalSection .card', '#portalSection'],
        },
    ];

    // Individual topic tutorials (Help & Support) — subsets of the full tour,
    // reusing the same engine and step objects.
    var STUDENT_TOPICS = {
        'tour': null, // full tour marker
        schedule: ['classes'],
        assignments: ['assignments'],
        resources: ['materials', 'resources'],
        fees: ['billing'],
        contact: ['help'],
    };

    var INSTRUCTOR_TOPICS = {
        'tour': null,
        schedule: ['classes'],
        complete: ['mark-complete'],
        students: ['students'],
        assignments: ['assignments'],
        resources: ['materials'],
        contact: ['help'],
    };

    function roleSteps() {
        return storedRole() === 'instructor' ? INSTRUCTOR_STEPS : STUDENT_STEPS;
    }

    function topicSteps(topicId) {
        var topics = storedRole() === 'instructor' ? INSTRUCTOR_TOPICS : STUDENT_TOPICS;
        var ids = topics[topicId];
        if (!ids) return roleSteps(); // 'tour' or unknown → full tour
        var all = roleSteps();
        return all.filter(function (s) { return ids.indexOf(s.id) >= 0; });
    }

    // ------------------------------------------------------------------
    // Running tours
    // ------------------------------------------------------------------

    function runTour(steps, opts) {
        opts = opts || {};
        if (running || !window.TourEngine) return false;
        if (!steps.length) return false;
        running = true;

        return window.TourEngine.start({
            steps: steps,
            startIndex: opts.startIndex || 0,
            onStep: function (index, step) {
                if (opts.trackProgress !== false) {
                    saveState({ started: true, progress: { step: index, tour: step.tourId || 'full' } });
                }
            },
            onFinish: function () {
                running = false;
                if (opts.trackProgress !== false) {
                    saveState({ started: true, completed: true, skipped: false, progress: null });
                }
                if (opts.onFinish) opts.onFinish();
            },
            onSkip: function () {
                running = false;
                if (opts.trackProgress !== false) {
                    saveState({ started: true, skipped: true, progress: null });
                }
                if (opts.onSkip) opts.onSkip();
            },
            onExit: function (index) {
                running = false;
                // closed mid-tour — remember progress for a later resume
                if (opts.trackProgress !== false) {
                    saveState({ started: true, progress: { step: index, tour: 'full' } });
                }
                if (opts.onExit) opts.onExit(index);
            },
        });
    }

    // ------------------------------------------------------------------
    // Welcome introduction (first-login modal)
    // ------------------------------------------------------------------

    function welcomeCopy() {
        if (storedRole() === 'instructor') {
            return {
                title: 'Welcome to the ChankArts Music Academy Instructor Portal!',
                body: 'Your portal helps you manage your assigned classes, view student schedules, track completed sessions, share learning materials, review student work and stay connected with the Academy.',
                start: 'Start Guided Tour',
            };
        }
        return {
            title: 'Welcome to ChankArts Music Academy!',
            body: 'Your learning portal is your personal space to manage your music classes, track your progress, access learning resources, submit assignments and stay connected with your instructor.',
            start: 'Start Guided Tour',
        };
    }

    function showWelcome() {
        if (document.getElementById('tourWelcomeRoot')) return;
        var copy = welcomeCopy();
        var resuming = state && state.started && state.progress && typeof state.progress.step === 'number';
        var root = document.createElement('div');
        root.id = 'tourWelcomeRoot';
        root.className = 'tour-welcome-root';
        root.innerHTML =
            '<div class="tour-welcome" role="dialog" aria-modal="true" aria-labelledby="tourWelcomeTitle">' +
            '<div class="tour-welcome__badge" aria-hidden="true">♪</div>' +
            '<h2 class="tour-welcome__title" id="tourWelcomeTitle">' + copy.title + '</h2>' +
            '<p class="tour-welcome__body">' + copy.body + '</p>' +
            '<div class="tour-welcome__actions">' +
            '<button type="button" class="btn-p" data-welcome="start">' +
            (resuming ? 'Resume Guided Tour' : copy.start) + '</button>' +
            '<button type="button" class="btn-p btn-p--ghost" data-welcome="skip">Skip for Now</button>' +
            '</div></div>';
        document.body.appendChild(root);

        root.querySelector('[data-welcome="start"]').addEventListener('click', function () {
            closeWelcome();
            var startIndex = resuming ? state.progress.step : 0;
            saveState({ shown: true, started: true, skipped: false, completed: false })
                .then(function () { runTour(roleSteps(), { startIndex: startIndex }); });
        });
        root.querySelector('[data-welcome="skip"]').addEventListener('click', function () {
            closeWelcome();
            saveState({ shown: true, skipped: true });
        });
        // mark shown as soon as it is displayed so a refresh does not re-show it
        saveState({ shown: true });
        try { root.querySelector('[data-welcome="start"]').focus(); } catch (e) { /* ignore */ }
    }

    function closeWelcome() {
        var root = document.getElementById('tourWelcomeRoot');
        if (root && root.parentNode) root.parentNode.removeChild(root);
    }

    // ------------------------------------------------------------------
    // First-login auto-launch (spec §1.B): after PIN change, once per load,
    // role-correct, never repeatedly.
    // ------------------------------------------------------------------

    function maybeAutoLaunch() {
        if (autoLaunchDone) return;
        autoLaunchDone = true;
        var role = storedRole();
        if (role !== 'student' && role !== 'parent' && role !== 'instructor') return;

        loadState().then(function (s) {
            if (!s) return;
            // An explicit skip or a completed tour never auto-launches again;
            // anything else (fresh, undecided, or interrupted mid-tour) may
            // introduce itself once per page load.
            if (s.skipped || s.completed) return;
            setTimeout(function () {
                if (running || document.getElementById('tourWelcomeRoot')) return;
                if (!document.getElementById('portalRoot')) return; // portal still rendering
                showWelcome();
            }, 450);
        }).catch(function (e) {
            console.warn('[tour] onboarding state unavailable', e);
        });
    }

    // ------------------------------------------------------------------
    // Help & Support tutorial centre (spec §5)
    // ------------------------------------------------------------------

    function helpCentreHtml() {
        var instructor = storedRole() === 'instructor';
        var topics = instructor ? [
            ['tour', 'Take the Instructor Portal Tour'],
            ['schedule', 'How to Manage My Class Schedule'],
            ['complete', 'How to Mark Classes Completed'],
            ['students', 'How to Access Assigned Students'],
            ['assignments', 'How to Manage Assignments'],
            ['resources', 'How to Share Learning Resources'],
            ['contact', 'How to Contact the Academy'],
        ] : [
            ['tour', 'Take the Student Portal Tour'],
            ['schedule', 'How to Check My Class Schedule'],
            ['assignments', 'How to View and Submit Assignments'],
            ['resources', 'How to Find Learning Resources'],
            ['fees', 'How to View and Pay Fees'],
            ['contact', 'How to Contact the Academy'],
        ];
        var faqs = instructor ? [
            ['How do I mark a class completed?', 'Open Class Schedule, find the upcoming class and press “Mark Completed”. Add any remarks about the lesson. Completed classes are kept in the student’s record and can only be undone with an administrator-approved action.'],
            ['How do I share material with students?', 'Open Study Material and use “Upload Material”. Students see it in their Study Material section right away.'],
            ['How do I contact the Academy?', 'Open Help & Support, type your subject and message, and press “Send to Administration”. Replies appear here and as a portal notification.'],
        ] : [
            ['How do I check my classes?', 'Open “My Classes” from the left menu. You can switch between Month, Week and List views to see your upcoming lessons.'],
            ['How do I submit an assignment?', 'Open “Assignments”, tap the assignment, read the instructions and due date, then upload your work. You can track its status here.'],
            ['How do I pay my fees?', 'Open “Payments & Billing”. Review your charges and outstanding balance, then use the available payment option. The academy verifies every payment claim before it is marked paid.'],
            ['How do I ask for a reschedule?', 'Open “My Classes” and press “Request Reschedule” on the class (at least 24 hours before it starts). The academy reviews every request.'],
        ];

        var topicButtons = topics.map(function (t) {
            return '<button type="button" class="btn-p btn-p--sm btn-p--ghost" data-action="tour-topic" data-id="' +
                t[0] + '">' + t[1] + '</button>';
        }).join('');

        var faqHtml = faqs.map(function (f) {
            return '<details class="tour-faq"><summary>' + f[0] + '</summary><p>' + f[1] + '</p></details>';
        }).join('');

        return '<div class="card tour-centre" id="tourCentre">' +
            '<h3 class="card__title" style="margin-bottom:6px">Getting Started / Guided Tutorials</h3>' +
            '<p style="font-size:13px;color:var(--text-2);line-height:1.6;margin-bottom:12px">' +
            'New here? Take a short interactive tour that points out where everything lives — ' +
            'or pick a single topic below. You can replay any tutorial whenever you like.</p>' +
            '<div class="btn-row" style="margin-bottom:12px">' +
            '<button type="button" class="btn-p btn-p--auto" data-action="tour-replay">Replay Guided Tour</button>' +
            '</div>' +
            '<div class="tour-centre__topics">' + topicButtons + '</div>' +
            '<h4 class="tour-centre__faq-title">Quick written help</h4>' +
            faqHtml +
            '</div>';
    }

    function startFullTour() {
        closeWelcome();
        var s = state;
        var startIndex = (s && s.started && s.progress && typeof s.progress.step === 'number')
            ? s.progress.step : 0;
        if (s && s.completed) startIndex = 0; // replay always starts fresh
        runTour(roleSteps(), { startIndex: startIndex });
    }

    function startTopic(topicId) {
        closeWelcome();
        if (topicId === 'tour' || topicId === undefined) {
            startFullTour();
            return;
        }
        var steps = topicSteps(topicId);
        // Topic walkthroughs are self-contained: no cross-tour progress writes
        // beyond marking the tour as seen/started.
        runTour(steps, { trackProgress: false });
    }

    return {
        maybeAutoLaunch: maybeAutoLaunch,
        showWelcome: showWelcome,
        startFullTour: startFullTour,
        startTopic: startTopic,
        helpCentreHtml: helpCentreHtml,
        loadState: loadState,
        getState: function () { return state; },
        // exposed for tests
        STUDENT_STEPS: STUDENT_STEPS,
        INSTRUCTOR_STEPS: INSTRUCTOR_STEPS,
        STUDENT_TOPICS: STUDENT_TOPICS,
        INSTRUCTOR_TOPICS: INSTRUCTOR_TOPICS,
        CONTENT_VERSION: CONTENT_VERSION,
    };
})();
