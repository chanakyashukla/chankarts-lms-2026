/* ============================================================
   ChankArts LMS 2026 — Preview API
   ------------------------------------------------------------
   GitHub Pages serves static files only: there is no server to
   run the Python backend. This module provides the full /api/v1
   surface inside the browser so every screen and control is
   genuinely functional in the preview environment:

   - real credential checks (PBKDF2-hashed PINs via WebCrypto)
   - role-based authorization (admin / instructor / student / parent)
   - first-login forced PIN change
   - real data operations (create/edit/search/archive) with
     validation and persistence

   Storage: this browser's localStorage — the preview banner says
   so explicitly. This is NOT a production database; the backend/
   directory contains the production API (FastAPI + PostgreSQL).

   Activates only when no backend can exist (GitHub Pages) or when
   forced with ?preview=1. On localhost/prod domains the real API
   is used unchanged.
   ============================================================ */
(function () {
    'use strict';

    // Preview (demo) data mode is ONLY permitted on the GitHub Pages demo
    // host and local development. The production domain (academy.chankarts.com
    // or any other host) NEVER activates the browser-local demo adapter —
    // there, every request goes to the real backend API.
    var host = location.hostname;
    var isPreviewHost = /\.github\.io$/i.test(host);
    var isLocalDev = host === 'localhost' || host === '127.0.0.1';
    var forced = /[?&]preview=1/.test(location.search);
    var sticky = false;
    try { sticky = localStorage.getItem('chankarts-preview-on') === '1'; } catch (e) { /* ignore */ }
    window.PREVIEW_MODE = !!(isPreviewHost || (isLocalDev && (forced || sticky)));
    if (window.PREVIEW_MODE) {
        try { localStorage.setItem('chankarts-preview-on', '1'); } catch (e) { /* ignore */ }
    } else {
        try { localStorage.removeItem('chankarts-preview-on'); } catch (e) { /* ignore */ }
    }
    if (!window.PREVIEW_MODE) return; // real backend takes over

    var KEY = 'chankarts-lms-2026-preview-v1';

    // ---------- store ----------
    function emptyDb() {
        return {
            demo: true,
            users: [], students: [], instructors: [], enrollments: [], guardian_accounts: [],
            sessions: [], invoices: [], payments: [], reports: [], assignments: [], submissions: [],
            syllabi: [], syllabus_items: [], syllabus_progress: [], syllabus_assignments: [],
            exams: [], milestones: [], achievements: [], support_requests: [], support_replies: [],
            notifications: [], credits: [], materials: [], recommendations: [], audit: [],
            pin_reset_requests: [], registration_requests: [], packages: []
        };
    }
    function load() {
        try {
            var raw = localStorage.getItem(KEY);
            if (raw) return JSON.parse(raw);
        } catch (e) { /* fall through to seed */ }
        var db = emptyDb();
        save(db);
        return db;
    }
    function save(db) { localStorage.setItem(KEY, JSON.stringify(db)); }
    var DB = load();

    function uid(p) { return (p || 'id') + '_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4); }
    function day(offset) { var d = new Date(); d.setDate(d.getDate() + offset); return d.toISOString().slice(0, 10); }

    // ---------- crypto (PBKDF2) ----------
    function b64(buf) { var s = ''; new Uint8Array(buf).forEach(function (b) { s += String.fromCharCode(b); }); return btoa(s); }
    async function hashPin(pin, salt) {
        var key = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin), 'PBKDF2', false, ['deriveBits']);
        var bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', salt: new TextEncoder().encode(salt), iterations: 150000, hash: 'SHA-256' }, key, 256);
        return b64(bits);
    }

    // ---------- tokens (preview-grade) ----------
    function signToken(payload) {
        var body = btoa(JSON.stringify(payload));
        var sig = btoa(String(payload.uid).split('').reverse().join('') + ':' + payload.exp).replace(/=/g, '');
        return body + '.' + sig;
    }
    function readToken(tok) {
        if (!tok) return null;
        try {
            var parts = tok.split('.');
            var payload = JSON.parse(atob(parts[0]));
            var expect = btoa(String(payload.uid).split('').reverse().join('') + ':' + payload.exp).replace(/=/g, '');
            if (parts[1] !== expect) return null;
            if (payload.exp < Date.now()) return null;
            return payload;
        } catch (e) { return null; }
    }

    // ---------- helpers ----------
    function json(data, status) {
        return new Response(JSON.stringify(data), { status: status || 200, headers: { 'Content-Type': 'application/json' } });
    }
    function err(status, detail) { return json({ detail: detail }, status); }
    function userById(id) { return DB.users.filter(function (u) { return u.id === id; })[0]; }
    function studentById(id) { return DB.students.filter(function (s) { return s.id === id; })[0]; }
    function studentForUser(uidv) { return DB.students.filter(function (s) { return s.user_id === uidv; })[0]; }
    function enrollmentsFor(studentId) {
        return DB.enrollments.filter(function (e) { return e.student_id === studentId; }).map(function (e) {
            var inst = DB.instructors.filter(function (i) { return i.id === e.instructor_id; })[0];
            return Object.assign({}, e, {
                instructor: inst ? inst.first_name + ' ' + inst.last_name : null,
                student_name: (studentById(e.student_id) || {}).full_name || ''
            });
        });
    }
    function linkedStudentIds(user) {
        if (user.role === 'student') { var s = studentForUser(user.id); return s ? [s.id] : []; }
        if (user.role === 'parent') {
            return DB.guardian_accounts.filter(function (g) { return g.user_id === user.id; }).map(function (g) { return g.student_id; });
        }
        return null; // staff: unrestricted (checked per-route)
    }

    // ---------- demo seed (clearly labelled demo data) ----------
// ---- credential table: PBKDF2 hashes of the academy register PINs.
    // Plaintext PINs are NEVER included in this bundle; the values below are
    // precomputed SHA-256/PBKDF2 (150k iterations, per-account salt).
    var PRECOMPUTED = {
    "CMA-001": {
        "hash": "TP3/7g7FnD8LVJ6qKRBlz0ZoXD9FGS/YVqN1HgFpEl0=",
        "salt": "chankarts-lms-2026:CMA-001"
    },
    "CMA-002": {
        "hash": "3z2V8VxLleygd0f6pRvQyyzddoJaFZvvVspJvJDHwuA=",
        "salt": "chankarts-lms-2026:CMA-002"
    },
    "CMA-003": {
        "hash": "tOMmgFN6KU6SPN54+YA/+pLQx4W9xqN8ZVMwsdmvLFk=",
        "salt": "chankarts-lms-2026:CMA-003"
    },
    "CMA-004": {
        "hash": "lNatnArjaCPrV1irrvXC7fAcluGnCTyvG/TCZyPT2Og=",
        "salt": "chankarts-lms-2026:CMA-004"
    },
    "CMA-005": {
        "hash": "cGjLKmt1IgWXfDnNIQjT4iNXOESn743bAWuEp2CYzWs=",
        "salt": "chankarts-lms-2026:CMA-005"
    },
    "CMA-006": {
        "hash": "LUTD04KSXNBAN6qMTWrU3hiLh6VIxel1ZkSXtiS6xoA=",
        "salt": "chankarts-lms-2026:CMA-006"
    },
    "CMA-007": {
        "hash": "jja6dUqjLufupFNwwWDKNeKmwmEHpvz86AYOm8D1J90=",
        "salt": "chankarts-lms-2026:CMA-007"
    },
    "CMA-008": {
        "hash": "ejw4ca6VgclPdFb7fdQRCrYmz9JESj2Y64Dn2quywBI=",
        "salt": "chankarts-lms-2026:CMA-008"
    },
    "CMA-009": {
        "hash": "0cZKm/FoFFElYE8+icaCzf4ThYMvGr0idmIx/mt3y9U=",
        "salt": "chankarts-lms-2026:CMA-009"
    },
    "CMA-010": {
        "hash": "hOeOFvn9ZtxMuILsisAzJ83BrJZT918meqOTYNyMK80=",
        "salt": "chankarts-lms-2026:CMA-010"
    },
    "CMA-011": {
        "hash": "wdS7fSDRIkYZiHkHCaqhPb9Uh2CVNZcQh7lURLzRw9U=",
        "salt": "chankarts-lms-2026:CMA-011"
    },
    "CMA-012": {
        "hash": "qi7DB5XxYMzALam9DKgwskjEm9yZZAesx35SavTFRYM=",
        "salt": "chankarts-lms-2026:CMA-012"
    },
    "CMA-013": {
        "hash": "cx+aPMuCC7lTwDssA6yOdkiurYvKCGxORNGbFHecuN8=",
        "salt": "chankarts-lms-2026:CMA-013"
    },
    "CMA-014": {
        "hash": "MgLM26cyNlNJrXp9ZQ4fn2UJafhT9fpKd0V3bPRn+hI=",
        "salt": "chankarts-lms-2026:CMA-014"
    },
    "chanakya.shukla": {
        "hash": "+hPtdDogieoHE0ClhqKDW8AbuYVA4a6ixa8O9iiX6hE=",
        "salt": "chankarts-lms-2026:chanakya.shukla"
    },
    "instructor1": {
        "hash": "RMCuh/z3AGTQxazQf5aMsez98yELie8s3l2+dKWQuF0=",
        "salt": "chankarts-lms-2026:instructor1"
    },
    "parent1": {
        "hash": "cNIL3CqTxSpcnr8ui0sXJpwgtaknefmJs+9tHmvd6Uo=",
        "salt": "chankarts-lms-2026:parent1"
    },
    "preetam.piano": {
        "hash": "1jDO4gXbaKzoR3aw4bjZ7ElMRXRYwEfdkgZfbnzOnJY=",
        "salt": "chankarts-lms-2026:preetam.piano"
    },
    "student1": {
        "hash": "Hwi/lfYvOWZEwvxBTqnk7TiGjfLTLsf7XmGHXGhTKLk=",
        "salt": "chankarts-lms-2026:student1"
    },
    "student2": {
        "hash": "vptDecEFFm3SXkQyzm8ohD2ofZlYKSPXEwIz+lPFEOM=",
        "salt": "chankarts-lms-2026:student2"
    }
};

    var seedReady = null;
    async function ensureSeed() {
        if (seedReady) return seedReady;
        seedReady = (async function () {
            if (DB.users.length) return;
            var now = new Date();

            function addUser(username, role, name) {
                var u = {
                    id: uid('u'), username: username, email: null, role: role,
                    name: name, is_active: true, must_change_pin: false,
                    created_at: new Date().toISOString()
                };
                var pc = PRECOMPUTED[username];
                if (pc) { u.pin_salt = pc.salt; u.pin_hash = pc.hash; }
                DB.users.push(u);
                return u;
            }

            // ---- staff (academy register) ----
            var admin = addUser('admin', 'admin', 'ChankArts Admin');
            var admin2 = addUser('chanakya.shukla', 'admin', 'Chanakya Sir');
            var inst1 = addUser('instructor1', 'instructor', 'Asha Piano');
            var inst2 = addUser('preetam.piano', 'instructor', 'Preetam Piano');
            var parent1 = addUser('parent1', 'parent', 'Aarav\u2019s Parent');
            DB.instructors.push({ id: uid('ins'), user_id: inst1.id, first_name: 'Asha', last_name: 'Piano', specializations: 'piano, electronic keyboard', qualifications: 'Trinity Grade 8', experience_years: 8, is_active: true });
            DB.instructors.push({ id: uid('ins'), user_id: inst2.id, first_name: 'Preetam', last_name: 'Piano', specializations: 'piano, western vocals', qualifications: 'Trinity Grade 6', experience_years: 4, is_active: true });

            // ---- the real 14-student roster (ChankArts Music Academy) ----
            // [login, first, last, programme, schedule(s) as [day, start, end], fee plan]
            var roster = [
                ['CMA-001', 'Anish', 'Patil', 'Western Vocals', [['monday', '17:00', '18:00']], '4_classes'],
                ['CMA-002', 'Siri', 'Hosangadi', 'Electronic Keyboard', [['thursday', '17:00', '18:00']], '4_classes'],
                ['CMA-003', 'Suraj', 'Hosangadi', 'Electronic Keyboard', [['thursday', '18:00', '19:00']], '4_classes'],
                ['CMA-004', 'Sana', 'Muttalli', 'Electronic Keyboard', [['thursday', '19:00', '20:00']], '4_classes'],
                ['CMA-005', 'Prakhyaat', 'Verma', 'Ukulele', [['thursday', '16:00', '17:00']], '4_classes'],
                ['CMA-006', 'Ryan', 'Brahmachari', 'Electronic Keyboard', [['friday', '17:00', '18:00']], '4_classes'],
                ['CMA-007', 'Shael', 'Sharma', 'Acoustic Guitar', [['friday', '18:00', '19:00']], '4_classes'],
                ['CMA-008', 'Amaira', 'Kapoor', 'Electronic Keyboard', [['friday', '18:00', '19:00']], '4_classes'],
                ['CMA-009', 'Vedant', 'Gupta', 'Electronic Keyboard', [['saturday', '08:30', '09:30'], ['sunday', '08:30', '09:30']], '8_classes'],
                ['CMA-010', 'Punit', 'Gupta', 'Piano', [['saturday', '09:30', '10:30']], '4_classes'],
                ['CMA-011', 'Raina', 'Singh', 'Electronic Keyboard', [['saturday', '12:00', '13:00'], ['sunday', '12:00', '13:00']], '8_classes'],
                ['CMA-012', 'Rhyah', 'Kansara', 'Piano', [['saturday', '13:30', '14:30'], ['sunday', '13:30', '14:30']], '8_classes'],
                ['CMA-013', 'Nolen', 'Kumar', 'Electronic Keyboard', [['sunday', '15:30', '16:30']], '4_classes'],
                ['CMA-014', 'Vidip', 'Prasad', 'Electronic Keyboard', [['sunday', '17:00', '18:00']], '4_classes'],
                ['student1', 'Aarav', 'Sharma', 'Piano', [['wednesday', '17:00', '18:00']], '4_classes'],
                ['student2', 'Diya', 'Patel', 'Piano', [['tuesday', '18:00', '19:00']], '4_classes']
            ];
            var DAYS = { monday: 1, tuesday: 2, wednesday: 3, thursday: 4, friday: 5, saturday: 6, sunday: 0 };

            roster.forEach(function (row, idx) {
                var login = row[0], first = row[1], last = row[2], programme = row[3], slots = row[4], plan = row[5];
                var u = addUser(login, 'student', first + ' ' + last);
                var st = {
                    id: uid('st'), user_id: u.id, first_name: first, last_name: last,
                    cma_registration_id: 'CMA-2026-' + String(idx + 1).padStart(4, '0'),
                    login_id: login, status: 'active',
                    skill_level: idx % 3 === 0 ? 'beginner' : idx % 3 === 1 ? 'intermediate' : 'advanced',
                    date_of_birth: (2011 + (idx % 5)) + '-04-12', phone: null, notes: null,
                    created_at: new Date().toISOString()
                };
                DB.students.push(st);
                var teacher = (programme === 'Western Vocals' || programme === 'Piano') ? DB.instructors[1].id : DB.instructors[0].id;
                var enr = {
                    id: uid('en'), student_id: st.id,
                    programme_id: programme.toLowerCase().replace(/ /g, '_'),
                    programme_name: programme, instructor_id: teacher,
                    fee_plan: plan, fee_amount: plan === '8_classes' ? 8000 : 4500,
                    status: 'active', start_date: day(-70), created_at: new Date().toISOString()
                };
                DB.enrollments.push(enr);
                // weekly recurring timetable (fixed)
                slots.forEach(function (slot) {
                    DB.schedule_rows = DB.schedule_rows || [];
                    DB.audit.push({ id: uid('a'), action: 'schedule.created', entity: st.login_id + ' ' + slot[0] + ' ' + slot[1], at: new Date().toISOString(), note: 'Recurring weekly slot' });
                    // materialise dated sessions: last 4 and next 4 weeks
                    for (var w = -4; w <= 4; w++) {
                        var base = new Date(now);
                        var delta = (DAYS[slot[0]] - base.getDay() + 7) % 7 - 7;
                        base.setDate(base.getDate() + delta + w * 7);
                        var dstr = base.toISOString().slice(0, 10);
                        if (base > now) {
                            var stt = 'scheduled';
                            if (w === 0 && base.getDate() === now.getDate() && slot[0] === 'friday' && idx === 6) stt = 'rescheduling_required';
                            DB.sessions.push({ id: uid('se'), student_id: st.id, enrollment_id: enr.id, instructor_id: teacher, scheduled_date: dstr, scheduled_start: slot[1], scheduled_end: slot[2], status: stt, reschedule_reason: stt === 'rescheduling_required' ? 'Family function' : null, preferred_date: stt === 'rescheduling_required' ? day(3) : null, updated_at: new Date().toISOString() });
                        } else {
                            var roll = (idx + w) % 7;
                            var s2 = roll === 0 ? 'absent' : 'completed';
                            if (idx === 7 && w === -1) s2 = 'absent';
                            DB.sessions.push({
                                id: uid('se'), student_id: st.id, enrollment_id: enr.id, instructor_id: teacher,
                                scheduled_date: dstr, scheduled_start: slot[1], scheduled_end: slot[2],
                                status: s2,
                                topics_covered: s2 === 'completed' ? ['Scales & warm-ups', 'Sight reading', 'Repertoire piece', 'Rhythm patterns', 'Theory: notation', 'Aural training', 'Ear training games'][Math.abs((idx + w) % 7)] : null,
                                faculty_remarks: s2 === 'completed' ? (Math.abs((idx + w) % 3) === 0 ? null : 'Steady progress in class (DEMO record).') : null,
                                practice_recommendations: s2 === 'completed' && Math.abs((idx + w) % 2) === 0 ? '15 minutes daily practice' : null,
                                updated_at: new Date().toISOString()
                            });
                        }
                    }
                });
                // fee ledger: last + current + next month
                var amount = plan === '8_classes' ? 800000 : 450000;
                [-1, 0, 1].forEach(function (m) {
                    var d2 = new Date(now.getFullYear(), now.getMonth() + m, 1);
                    var ym = d2.getFullYear() + '-' + String(d2.getMonth() + 1).padStart(2, '0');
                    var paid = m <= 0;
                    var inv = {
                        id: uid('inv'), invoice_number: 'CMA/INV/' + ym.replace('-', '/') + '/' + String(idx + 1).padStart(4, '0'),
                        student_id: st.id, enrollment_id: enr.id, billing_month: ym,
                        amount_paise: amount, amount_paid_paise: paid ? amount : 0,
                        status: paid ? 'paid' : 'pending', charge_type: 'tuition',
                        description: 'Monthly tuition ' + ym + ' (' + plan.replace('_', ' ') + ' \u2014 ' + (plan === '8_classes' ? '8 classes' : '4 classes') + ')',
                        due_date: ym + '-05', created_at: new Date().toISOString()
                    };
                    DB.invoices.push(inv);
                    if (paid) {
                        DB.payments.push({
                            id: uid('pay'), provider: 'manual',
                            provider_payment_id: (m % 2 ? 'UPI-' : 'CASH-') + uid('ref'),
                            invoice_id: inv.id, student_id: st.id, amount_paise: amount, currency: 'INR',
                            method: m % 2 ? 'upi' : 'cash', status: 'verified', source: 'manual',
                            paid_at: ym + '-04', receipt_number: 'CMA/RCPT/' + ym.slice(0, 4) + '/' + String(DB.payments.length + 1).padStart(4, '0'),
                            notes: 'Recorded at the front desk'
                        });
                    }
                });
                // monthly progress report (published, generated from class records)
                var lastM = ymOf(now, -1);
                DB.reports.push({
                    id: uid('rep'), student_id: st.id, enrollment_id: enr.id, report_month: lastM,
                    revision: 1, status: 'published', published_at: new Date().toISOString(),
                    progress_summary: 'Completed ' + (2 + (idx % 2)) + ' of 4 classes. ' + programme + ' technique consolidating well.',
                    topics_covered: 'Scales & warm-ups, sight reading, repertoire piece',
                    strengths: 'Consistent weekly practice', areas_for_improvement: 'Hand position and posture',
                    practice_recommendations: '15 minutes daily', next_month_focus: 'Repertoire polish + exam preparation',
                    faculty_remarks: 'A productive month in ' + programme + '.'
                });
                // assignments + a quiz with recorded score
                DB.assignments.push({ id: uid('as'), student_id: st.id, enrollment_id: enr.id, title: 'Weekly practice log', instructions: 'Record daily practice minutes', assigned_date: day(-10), due_date: day(4), status: idx % 2 ? 'submitted' : 'assigned', priority: 'normal', created_at: new Date().toISOString() });
                DB.assignments.push({ id: uid('as'), student_id: st.id, enrollment_id: enr.id, title: 'Theory quiz \u2014 Notation basics', instructions: 'Complete the 10-question quiz', assigned_date: day(-20), due_date: day(-13), status: 'reviewed', priority: 'normal', created_at: new Date().toISOString() });
                DB.submissions.push({ id: uid('su'), assignment_id: DB.assignments[DB.assignments.length - 1].id, student_id: st.id, attempt_number: 1, status: 'reviewed', submitted_at: new Date().toISOString(), feedback: 'Well done \u2014 review time signatures.', score: 8 + (idx % 3) });
            });
            // family links: parent1 -> Aarav; Hosangadi parent -> Siri & Suraj
            DB.guardian_accounts.push({ id: uid('g'), user_id: parent1.id, student_id: DB.students[14].id, relationship: 'mother' });
            var hos = addUser('hosangadi.parent', 'parent', 'Hosangadi Parent');
            DB.guardian_accounts.push({ id: uid('g'), user_id: hos.id, student_id: DB.students[1].id, relationship: 'mother' });
            DB.guardian_accounts.push({ id: uid('g'), user_id: hos.id, student_id: DB.students[2].id, relationship: 'mother' });

            // syllabi (Trinity + Rockschool) with assignment + progress
            var sy1 = { id: uid('sy'), title: 'Trinity Piano Grade 1', board: 'trinity', programme_id: 'piano', grade: 'Grade 1', description: 'Technical work, repertoire, supporting tests', is_active: true };
            var sy2 = { id: uid('sy'), title: 'Rockschool Electronic Keyboard Debut', board: 'rockschool', programme_id: 'electronic_keyboard', grade: 'Debut', description: 'Debut keyboard pathway', is_active: true };
            DB.syllabi.push(sy1, sy2);
            [['Posture and hand position', 'topic'], ['Scales: C, G, F major', 'technical_work'], ['Repertoire: Minuet in G', 'repertoire'], ['Sight reading', 'technical_work'], ['Aural: dynamics and tempo', 'topic'], ['Performance piece', 'milestone']].forEach(function (t, i) {
                DB.syllabus_items.push({ id: uid('si'), syllabus_id: sy1.id, title: t[0], item_type: t[1], learning_objective: 'Demonstrate ' + t[0].toLowerCase(), sort_order: i });
            });
            [['Keyboard posture', 'topic'], ['Major scales', 'technical_work'], ['Debut pieces', 'repertoire'], ['Improvisation basics', 'topic']].forEach(function (t, i) {
                DB.syllabus_items.push({ id: uid('si'), syllabus_id: sy2.id, title: t[0], item_type: t[1], learning_objective: 'Demonstrate ' + t[0].toLowerCase(), sort_order: i });
            });
            DB.syllabus_assignments.push({ id: uid('sa'), student_id: DB.students[9].id, enrollment_id: DB.enrollments[9].id, syllabus_id: sy1.id, status: 'active' });   // Punit
            DB.syllabus_assignments.push({ id: uid('sa'), student_id: DB.students[11].id, enrollment_id: DB.enrollments[11].id, syllabus_id: sy1.id, status: 'active' }); // Rhyah
            DB.syllabus_assignments.push({ id: uid('sa'), student_id: DB.students[0].id, enrollment_id: DB.enrollments[0].id, syllabus_id: sy2.id, status: 'active' });    // Anish (vocals -> debut pathway demo)
            DB.syllabus_items.slice(0, 6).forEach(function (it, i) {
                DB.syllabus_progress.push({ id: uid('sp'), student_id: DB.students[9].id, enrollment_id: DB.enrollments[9].id, syllabus_id: sy1.id, item_id: it.id, status: i < 3 ? 'completed' : i < 5 ? 'in_progress' : 'not_started', faculty_notes: i < 3 ? 'Secure' : null });
            });
            DB.syllabus_items.slice(6).forEach(function (it, i) {
                DB.syllabus_progress.push({ id: uid('sp'), student_id: DB.students[0].id, enrollment_id: DB.enrollments[0].id, syllabus_id: sy2.id, item_id: it.id, status: i < 2 ? 'completed' : 'in_progress', faculty_notes: null });
            });

            // exams (Trinity / Rockschool) incl. exam-fee tracking
            DB.exams.push({ id: uid('ex'), student_id: DB.students[9].id, board: 'Trinity College London', instrument: 'Piano', grade_level: 'Grade 1', application_status: 'confirmed', payment_status: 'pending', exam_date: day(52), readiness: 'preparing', result: null, notes: 'Entry confirmed with Trinity' });
            DB.exams.push({ id: uid('ex'), student_id: DB.students[1].id, board: 'Rockschool', instrument: 'Electronic Keyboard', grade_level: 'Debut', application_status: 'planning', payment_status: 'not_applicable', exam_date: day(95), readiness: 'not_started', result: null, notes: 'Target session: summer' });
            DB.exam_fees = DB.exam_fees || [];
            DB.exam_fees.push({ id: uid('ef'), student_id: DB.students[9].id, board: 'Trinity College London', grade_level: 'Grade 1', fee_charged_paise: 600000, academy_paid_paise: 600000, reimbursed_paise: 300000, reimbursement_balance_paise: 300000, status: 'academy_paid', exam_session: 'Spring 2027' });

            // achievements (verified) + milestones
            DB.achievements.push({ id: uid('ac'), student_id: DB.students[9].id, title: 'Trinity Grade 1 Piano \u2014 Distinction', category: 'exam', awarding_body: 'Trinity College London', programme_id: 'piano', grade_level: 'Grade 1', result: 'Distinction', achieved_on: day(-120), is_verified: true, is_archived: false, description: 'Awarded Distinction in the Grade 1 piano examination.' });
            DB.achievements.push({ id: uid('ac'), student_id: DB.students[10].id, title: 'Winter Recital Performance', category: 'recital', awarding_body: 'ChankArts Music Academy', result: 'Performed', achieved_on: day(-45), is_verified: true, is_archived: false, description: 'Solo performance at the academy winter recital.' });
            DB.milestones.push({ id: uid('ms'), student_id: DB.students[0].id, title: 'First full song performed', description: 'Performed confidently at the student evening', status: 'achieved', achieved_on: day(-21) });

            // study materials + recommendations (targeted visibility demo)
            DB.materials.push({ id: uid('mt'), title: 'Piano scales workbook', category: 'technique', programme_id: 'piano', visibility_scope: 'programme', material_type: 'link', link_url: '#', is_published: true });
            DB.materials.push({ id: uid('mt'), title: 'Keyboard chord chart (all students)', category: 'technique', visibility_scope: 'all', material_type: 'link', link_url: '#', is_published: true });
            DB.recommendations.push({ id: uid('rc'), resource_type: 'book', name: 'Faber Piano Adventures Level 1', visibility_scope: 'programme', programme_id: 'piano', is_active: true });
            DB.recommendations.push({ id: uid('rc'), resource_type: 'accessory', name: 'Keyboard sustain pedal', visibility_scope: 'programme', programme_id: 'electronic_keyboard', is_active: true });

            // packages
            DB.packages.push({ id: 'pkg4', code: 'standard_4', name: '4 Classes Package', sessions_included: 4, fee_paise: 450000, description: 'Monthly tuition \u2014 4 classes (60 min each)', is_active: true });
            DB.packages.push({ id: 'pkg8', code: 'standard_8', name: '8 Classes Package', sessions_included: 8, fee_paise: 800000, description: 'Monthly tuition \u2014 8 classes (60 min each)', is_active: true });

            // a pending online-reported payment (manual confirmation workflow) + advance credit
            DB.payments.push({ id: uid('pay'), provider: 'reported', provider_payment_id: 'PAY-DEMO-PENDING', invoice_id: DB.invoices.filter(function (i) { return i.student_id === DB.students[1].id && i.status === 'pending'; })[0] ? DB.invoices.filter(function (i) { return i.student_id === DB.students[1].id && i.status === 'pending'; })[0].id : null, student_id: DB.students[1].id, amount_paise: 450000, currency: 'INR', method: 'upi', status: 'pending_verification', source: 'reported', paid_at: day(0), receipt_number: null, notes: 'Payment reported by family \u2014 awaiting admin confirmation' });
            DB.credits.push({ id: uid('cr'), student_id: DB.students[13].id, kind: 'advance', amount_paise: 200000, note: 'Advance held on account', created_at: new Date().toISOString() });

            // support conversation + notifications + packages of activity
            DB.support_requests.push({ id: uid('sr'), sender_user_id: parent1.id, sender_role: 'parent', subject: 'Question about the winter recital', message: 'Could you share the recital schedule and costume details?', status: 'replied', created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
            DB.support_replies.push({ id: uid('sr2'), request_id: DB.support_requests[0].id, author_role: 'admin', body: 'The recital is on the 12th \u2014 details have been emailed to all families.', created_at: new Date().toISOString() });
            DB.notifications.push({ id: uid('nt'), user_id: admin.id, type: 'welcome', title: 'ChankArts LMS ready', body: 'All 16 students, schedules, fees and reports are loaded.', created_at: new Date().toISOString(), read_at: null });

            DB.audit.push({ id: uid('a'), action: 'demo.seeded', entity: 'roster', at: new Date().toISOString(), note: 'Academy roster demo data (preview)' });
            save(DB);
        })();
        return seedReady;
    }

        function ymOf(d, offset) { var x = new Date(d.getFullYear(), d.getMonth() + offset, 1); return x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0'); }

    // ---------- fetch interception ----------
    var realFetch = window.fetch.bind(window);
    window.fetch = async function (input, init) {
        var url = typeof input === 'string' ? input : input.url;
        var m = url.match(/\/api\/v1(\/[^?]*)?(\?.*)?$/);
        if (!m) return realFetch(input, init);
        await ensureSeed();

        var path = (m[1] || '/');
        var query = {};
        (m[2] || '').replace(/^\?/, '').split('&').forEach(function (kv) { if (!kv) return; var p = kv.split('='); query[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ''); });
        var method = ((init && init.method) || (typeof input === 'object' && input.method) || 'GET').toUpperCase();
        var body = {};
        try { body = init && init.body ? JSON.parse(init.body) : {}; } catch (e) { body = {}; }
        var headers = (init && init.headers) || {};
        var auth = headers.Authorization || (headers.authorization) || '';
        var token = auth.replace(/^Bearer\s+/i, '');
        var me = readToken(token);
        try {
            return route(method, path, query, body, me, token);
        } catch (e) {
            return err(500, 'Preview error: ' + e.message);
        }
    };

    // ---------- routing ----------
    function route(method, path, q, body, me, token) {
        var seg = path.replace(/\/+$/, '').split('/').filter(Boolean);
        var P = '/' + seg.join('/');

        // ---- public auth ----
        if (P === '/auth/login' && method === 'POST') return login(body);
        if (P === '/auth/pin-reset-request' && method === 'POST') {
            DB.pin_reset_requests.push({ id: uid('pr'), username: body.email || body.username || 'unknown', status: 'pending', created_at: new Date().toISOString() });
            save(DB);
            return json({ message: 'If that account exists, a reset request has been recorded.' });
        }
        if (P === '/verify-email/request' || P.indexOf('/verify-email/') === 0) return json({ message: 'ok' });

        // ---- everything else requires auth ----
        if (!me) return err(401, 'Not authenticated');
        var user = userById(me.uid);
        if (!user || !user.is_active) return err(401, 'Not authenticated');
        var isChangePin = (P === '/auth/change-pin');
        if (user.must_change_pin && !isChangePin) return err(403, 'PIN_CHANGE_REQUIRED');

        if (isChangePin && method === 'POST') return changePin(user, body);
        if (P === '/auth/me') return json({ id: user.id, username: user.username, email: user.email, role: user.role, is_active: user.is_active, created_at: user.created_at });

        // ---- portal (role-scoped) ----
        if (P === '/portal/me') return portalMe(user);
        if (P === '/portal/dashboard') return portalDashboard(user, q);
        if (P === '/portal/enrollments') {
            var ids = linkedStudentIds(user);
            if (ids === null) ids = DB.students.map(function (s) { return s.id; });
            return json([].concat.apply([], ids.map(enrollmentsFor)));
        }
        if (P === '/portal/notifications') return json(DB.notifications.filter(function (n) { return n.user_id === user.id; }));
        if (P === '/portal/notifications/read' && method === 'POST') {
            DB.notifications.forEach(function (n) { if (n.user_id === user.id) n.read_at = new Date().toISOString(); });
            save(DB); return json({ updated: true });
        }
        if (P.indexOf('/portal/support') === 0) return supportRoutes(method, seg, body, user, q);
        if (P === '/portal/achievements') return json(DB.achievements.filter(function (a) { return a.is_verified && !a.is_archived && allowedStudent(user, a.student_id); }));

        // ---- sessions ----
        if (P === '/sessions' && method === 'GET') return listSessions(user, q);
        if (P === '/sessions/stats/monthly') return sessionStats(user, q);
        if (P === '/sessions/reschedule-requests') return json(DB.sessions.filter(function (s) { return s.status === 'rescheduling_required'; }).map(sessionOut));
        if (seg[0] === 'sessions' && seg[2] && method === 'POST') return sessionAction(seg[2], seg[1], body, user);
        if (seg[0] === 'sessions' && seg[1] && method === 'PATCH') {
            var s2 = findSession(seg[1]); if (!s2) return err(404, 'Not found');
            if (!isAdmin(user) && s2.instructor_id !== instructorIdFor(user)) return err(403, 'Not authorised');
            Object.assign(s2, body); save(DB); return json(sessionOut(s2));
        }

        // ---- learning ----
        if (P.indexOf('/learning/') === 0) return learningRoutes(method, seg, q, body, user);

        // ---- billing ----
        if (P.indexOf('/billing/') === 0) return billingRoutes(method, seg, q, body, user);

        // ---- admin ----
        if (P.indexOf('/admin/') === 0) return adminRoutes(method, seg, q, body, user);

        // ---- students router (self/profile reads) ----
        if (seg[0] === 'students') {
            var st = studentById(seg[1]);
            if (!st) return err(404, 'Student not found');
            if (!allowedStudent(user, st.id)) return err(403, 'Not authorised');
            return json(studentOut(st));
        }

        return err(404, 'Not found: ' + method + ' ' + P);
    }

    function isAdmin(u) { return u.role === 'admin'; }
    function instructorIdFor(u) { var ins = DB.instructors.filter(function (i) { return i.user_id === u.id; })[0]; return ins ? ins.id : null; }
    function allowedStudent(u, studentId) {
        if (u.role === 'admin') return true;
        var ids = linkedStudentIds(u);
        if (ids === null) { // instructor
            var iid = instructorIdFor(u);
            return DB.enrollments.some(function (e) { return e.student_id === studentId && e.instructor_id === iid; });
        }
        return ids.indexOf(studentId) !== -1;
    }
    function studentOut(s) {
        return Object.assign({}, s, {
            full_name: s.first_name + ' ' + s.last_name,
            login_id: s.login_id || s.cma_registration_id,
            enrollments: enrollmentsFor(s.id)
        });
    }
    function sessionOut(s) {
        var st = studentById(s.student_id) || {};
        var enr = DB.enrollments.filter(function (e) { return e.id === s.enrollment_id; })[0] || {};
        return Object.assign({}, s, {
            student_name: (st.first_name || '') + ' ' + (st.last_name || ''),
            student_cma: st.cma_registration_id, programme: enr.programme_name
        });
    }

    // ---- auth handlers ----
    async function login(body) {
        var id = (body.email || '').trim();
        var pin = body.password || '';
        var u = DB.users.filter(function (x) { return x.username === id || x.email === id; })[0];
        if (!u) return err(401, 'Incorrect email or password');
        // lazy demo-hash for seeded students
        if (!u.pin_hash && u.__demo_pin) {
            u.pin_salt = 'chankarts-preview-salt';
            u.pin_hash = await hashPin(u.__demo_pin, u.pin_salt);
            delete u.__demo_pin;
            save(DB);
        }
        if (!u.pin_hash) return err(401, 'Incorrect email or password');
        var h = await hashPin(pin, u.pin_salt);
        if (h !== u.pin_hash) return err(401, 'Incorrect email or password');
        if (!u.is_active) return err(403, 'Inactive user');
        var st = studentForUser(u.id);
        if (u.role === 'student' && st && st.status !== 'active') return err(403, 'Inactive user');
        var token = signToken({ uid: u.id, role: u.role, exp: Date.now() + 12 * 3600 * 1000 });
        return json({ access_token: token, token_type: 'bearer', must_change_pin: !!u.must_change_pin, role: u.role, user: { id: u.id, username: u.username, role: u.role, name: u.name || u.username } });
    }
    async function changePin(user, body) {
        var h = await hashPin(body.current_pin, user.pin_salt);
        if (h !== user.pin_hash) return err(400, 'Current PIN is incorrect');
        if (!/^\d{4}$/.test(body.new_pin || '')) return err(400, 'New PIN must be exactly 4 digits');
        if (body.new_pin === body.current_pin) return err(400, 'Choose a different PIN');
        user.pin_salt = 'chankarts-preview-salt';
        user.pin_hash = await hashPin(body.new_pin, user.pin_salt);
        user.must_change_pin = false;
        save(DB);
        return json({ message: 'PIN updated' });
    }

    // ---- portal ----
    function portalMe(user) {
        var out = { id: user.id, username: user.username, role: user.role, name: user.name || user.username };
        var st = studentForUser(user.id);
        if (st) out.student = studentOut(st);
        if (user.role === 'instructor') {
            var ins = DB.instructors.filter(function (i) { return i.user_id === user.id; })[0];
            if (ins) out.instructor = { id: ins.id, name: ins.first_name + ' ' + ins.last_name, specializations: ins.specializations, qualifications: ins.qualifications, experience_years: ins.experience_years };
        }
        if (user.role === 'parent') {
            out.children = linkedStudentIds(user).map(studentOut);
        }
        return json(out);
    }
    function portalDashboard(user, q) {
        var sid = q.student_id;
        if (!sid) { var ids = linkedStudentIds(user) || []; sid = ids[0]; }
        var st = studentById(sid);
        if (!st) return json({ student: {}, enrollments: [], month_summary: {}, fee: null, latest_report: null, syllabus: null, upcoming: [] });
        if (!allowedStudent(user, st.id)) return err(403, 'Not authorised');
        var month = new Date().toISOString().slice(0, 7);
        var sess = DB.sessions.filter(function (s) { return s.student_id === st.id; });
        var monthSess = sess.filter(function (s) { return s.scheduled_date.slice(0, 7) === month; });
        var inv = DB.invoices.filter(function (i) { return i.student_id === st.id && i.billing_month === month; })[0];
        var rep = DB.reports.filter(function (r) { return r.student_id === st.id; })[0];
        var sylA = DB.syllabus_assignments.filter(function (a) { return a.student_id === st.id && a.status === 'active'; })[0];
        var prog = sylA ? DB.syllabus_progress.filter(function (p) { return p.student_id === st.id && p.syllabus_id === sylA.syllabus_id; }) : [];
        var syl = sylA ? DB.syllabi.filter(function (s) { return s.id === sylA.syllabus_id; })[0] : null;
        return json({
            student: studentOut(st),
            enrollments: enrollmentsFor(st.id),
            month_summary: {
                completed: monthSess.filter(function (s) { return s.status === 'completed'; }).length,
                scheduled: monthSess.filter(function (s) { return s.status === 'scheduled'; }).length,
                total: monthSess.length
            },
            fee: inv ? { billed: inv.amount_paise, paid: inv.amount_paid_paise, status: inv.status, due_date: inv.due_date } : null,
            latest_report: rep || null,
            syllabus: syl ? { syllabus: syl, percent: prog.length ? Math.round(100 * prog.filter(function (p) { return p.status === 'completed'; }).length / prog.length) : 0, items: prog } : null,
            upcoming: sess.filter(function (s) { return s.status === 'scheduled' && s.scheduled_date >= new Date().toISOString().slice(0, 10); }).slice(0, 5).map(sessionOut)
        });
    }

    // ---- sessions ----
    function listSessions(user, q) {
        var ids = linkedStudentIds(user);
        var rows = DB.sessions.slice();
        if (ids === null) {
            if (user.role === 'instructor') { var iid = instructorIdFor(user); rows = rows.filter(function (s) { return s.instructor_id === iid; }); }
        } else {
            rows = rows.filter(function (s) { return ids.indexOf(s.student_id) !== -1; });
        }
        if (q.student_id) rows = rows.filter(function (s) { return s.student_id === q.student_id; });
        if (q.date_from) rows = rows.filter(function (s) { return s.scheduled_date >= q.date_from; });
        if (q.date_to) rows = rows.filter(function (s) { return s.scheduled_date <= q.date_to; });
        rows.sort(function (a, b) { return (a.scheduled_date + a.scheduled_start) < (b.scheduled_date + b.scheduled_start) ? -1 : 1; });
        return json(rows.slice(0, Number(q.limit) || 300).map(sessionOut));
    }
    function findSession(id) { return DB.sessions.filter(function (s) { return s.id === id; })[0]; }
    function sessionStats(user, q) {
        var rows = JSON.parse(listSessions(user, { limit: '1000' })._data || '[]');
        // simpler: recompute
        var ids = linkedStudentIds(user);
        var all = DB.sessions.filter(function (s) {
            return ids === null ? (user.role !== 'instructor' || s.instructor_id === instructorIdFor(user)) : ids.indexOf(s.student_id) !== -1;
        });
        var month = q.month || new Date().toISOString().slice(0, 7);
        var mm = all.filter(function (s) { return s.scheduled_date.slice(0, 7) === month; });
        var out = { completed: 0, scheduled: 0, cancelled: 0, rescheduled: 0, rescheduling_required: 0 };
        mm.forEach(function (s) { out[s.status] = (out[s.status] || 0) + 1; });
        return json(out);
    }
    function sessionAction(action, id, body, user) {
        var s = findSession(id);
        if (!s) return err(404, 'Session not found');
        if (!allowedStudent(user, s.student_id) && user.role !== 'admin') return err(403, 'Not authorised');
        if (action === 'complete') {
            if (s.status === 'completed') return err(409, 'This session is already marked completed');
            if (user.role === 'instructor' && s.instructor_id !== instructorIdFor(user)) return err(403, 'Not authorised');
            Object.assign(s, { status: 'completed', topics_covered: body.topics_covered || null, faculty_remarks: body.faculty_remarks || null, practice_recommendations: body.practice_recommendations || null, actual_date: body.actual_date || s.scheduled_date, updated_at: new Date().toISOString() });
            DB.audit.push({ id: uid('a'), action: 'session.completed', entity: s.id, at: new Date().toISOString(), by: user.username });
            save(DB); return json(sessionOut(s));
        }
        if (action === 'flag-reschedule') {
            if (s.status === 'rescheduling_required') {
                s.reschedule_reason = body.reason || s.reschedule_reason;
                s.preferred_date = body.preferred_date || s.preferred_date;
                save(DB); return json(sessionOut(s));
            }
            if (s.status !== 'scheduled') return err(400, 'Only scheduled sessions can be flagged');
            // 24-hour notice policy
            var start = new Date(s.scheduled_date + 'T' + s.scheduled_start + ':00+05:30').getTime();
            if (start - Date.now() < 24 * 3600 * 1000) return err(422, 'Rescheduling requests must be made at least 24 hours before the class start time. Inside 24 hours, please contact the academy directly.');
            s.status = 'rescheduling_required';
            s.reschedule_reason = body.reason || 'no reason given';
            s.preferred_date = body.preferred_date || null;
            DB.audit.push({ id: uid('a'), action: 'session.flagged', entity: s.id, at: new Date().toISOString(), by: user.username });
            save(DB); return json(sessionOut(s));
        }
        if (action === 'cancel') {
            if (user.role !== 'admin') return err(403, 'Only administrators can cancel');
            s.status = 'cancelled'; s.updated_at = new Date().toISOString();
            save(DB); return json(sessionOut(s));
        }
        if (action === 'reschedule' || action === 'reschedule-exception') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            if (action === 'reschedule' && s.status === 'scheduled' && (new Date(s.scheduled_date + 'T' + s.scheduled_start + ':00+05:30').getTime() - Date.now()) < 24 * 3600 * 1000) {
                return err(400, 'Inside 24 hours of the class, use the exception workflow with a reason.');
            }
            s.status = 'rescheduled';
            DB.sessions.push({
                id: uid('se'), student_id: s.student_id, enrollment_id: s.enrollment_id, instructor_id: s.instructor_id,
                scheduled_date: body.new_date, scheduled_start: (body.new_start || '17:00').slice(0, 5), scheduled_end: (body.new_end || '18:00').slice(0, 5),
                status: 'scheduled', replaces_session_id: s.id, reschedule_reason: body.reason || null, updated_at: new Date().toISOString()
            });
            DB.audit.push({ id: uid('a'), action: 'session.rescheduled', entity: s.id, at: new Date().toISOString(), by: user.username, note: body.reason });
            save(DB); return json(sessionOut(s));
        }
        if (action === 'reject-reschedule') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            s.status = 'scheduled'; save(DB); return json(sessionOut(s));
        }
        return err(400, 'Unknown session action');
    }

    // ---- learning ----
    function learningRoutes(method, seg, q, body, user) {
        var p = seg.slice(1).join('/');
        var staff = user.role === 'admin' || user.role === 'instructor';
        if (p === 'assignments' && method === 'GET') {
            var ids = linkedStudentIds(user);
            var rows = DB.assignments.filter(function (a) {
                return ids === null ? (user.role !== 'instructor' || DB.enrollments.some(function (e) { return e.id === a.enrollment_id && e.instructor_id === instructorIdFor(user); })) : ids.indexOf(a.student_id) !== -1;
            });
            if (q.status) rows = rows.filter(function (a) { return a.status === q.status; });
            return json(rows.map(assignmentOut));
        }
        if (p === 'assignments' && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            var a = Object.assign({ id: uid('as'), status: 'assigned', created_at: new Date().toISOString() }, body);
            DB.assignments.push(a); save(DB); return json(assignmentOut(a), 201);
        }
        if (seg[1] === 'assignments' && seg[2] && seg[3] === 'submit' && method === 'POST') {
            var asg = DB.assignments.filter(function (x) { return x.id === seg[2]; })[0];
            if (!asg) return err(404, 'Not found');
            if (!allowedStudent(user, asg.student_id)) return err(403, 'Not authorised');
            var sub = { id: uid('su'), assignment_id: asg.id, student_id: asg.student_id, attempt_number: DB.submissions.filter(function (s) { return s.assignment_id === asg.id; }).length + 1, notes: body.notes || '', status: 'submitted', submitted_at: new Date().toISOString(), feedback: null, score: null };
            DB.submissions.push(sub); asg.status = 'submitted'; save(DB); return json(sub, 201);
        }
        if (seg[1] === 'submissions' && seg[2] && seg[3] === 'review' && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            var sub2 = DB.submissions.filter(function (x) { return x.id === seg[2]; })[0];
            if (!sub2) return err(404, 'Not found');
            Object.assign(sub2, { feedback: body.feedback || '', status: body.status || 'reviewed', score: body.score != null ? body.score : sub2.score, reviewed_at: new Date().toISOString() });
            save(DB); return json(sub2);
        }
        if (p === 'reports' && method === 'GET') {
            var ids2 = linkedStudentIds(user);
            var rr = DB.reports.filter(function (r) {
                if (ids2) return ids2.indexOf(r.student_id) !== -1 && (r.status === 'published' || user.role !== 'student' && user.role !== 'parent');
                return user.role !== 'instructor' || DB.enrollments.some(function (e) { return e.id === r.enrollment_id && e.instructor_id === instructorIdFor(user); });
            });
            return json(rr);
        }
        if (p === 'reports' && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            var rep = Object.assign({ id: uid('rep'), revision: 1, status: 'draft', created_at: new Date().toISOString() }, body);
            DB.reports.push(rep); save(DB); return json(rep, 201);
        }
        if (p === 'reports/generate-draft' && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            var existing = DB.reports.filter(function (r) { return r.enrollment_id === body.enrollment_id && r.report_month === body.report_month; })[0];
            if (existing && !body.confirm_overwrite) return err(409, 'A report already exists for ' + body.report_month + '. Pass confirm_overwrite=true to regenerate the draft from class records.');
            var sess = DB.sessions.filter(function (s) { return s.enrollment_id === body.enrollment_id && s.scheduled_date.slice(0, 7) === body.report_month; });
            var completed = sess.filter(function (s) { return s.status === 'completed'; });
            var draft = existing || { id: uid('rep'), revision: 1, student_id: (DB.enrollments.filter(function (e) { return e.id === body.enrollment_id; })[0] || {}).student_id, enrollment_id: body.enrollment_id, report_month: body.report_month, status: 'draft', created_at: new Date().toISOString(), strengths: null, areas_for_improvement: null, next_month_focus: null, faculty_remarks: null, staff_notes: null };
            draft.topics_covered = completed.length ? completed.map(function (s) { return s.scheduled_date.slice(8, 10) + '/' + s.scheduled_date.slice(5, 7) + ' — ' + (s.topics_covered || '[no lesson note recorded for this class]'); }).join('\n') : '[no completed classes recorded for this month]';
            draft.practice_recommendations = completed.filter(function (s) { return s.practice_recommendations; }).map(function (s) { return s.practice_recommendations; }).join('\n') || '[no practice recommendations recorded]';
            draft.progress_summary = completed.length + ' of ' + sess.length + ' scheduled classes completed in ' + body.report_month + '. (Generated from class records.)';
            draft.generated_from_sessions = { completed: completed.length, deliverable: sess.length };
            if (!existing) DB.reports.push(draft);
            save(DB); return json(draft, existing ? 200 : 201);
        }
        if (seg[1] === 'reports' && seg[2] && seg[3] === 'submit' && method === 'POST') {
            var r3 = DB.reports.filter(function (x) { return x.id === seg[2]; })[0];
            if (!r3) return err(404, 'Not found');
            if (r3.status === 'published') return err(400, 'Published reports cannot be re-submitted');
            r3.status = 'submitted'; save(DB); return json(r3);
        }
        if (seg[1] === 'reports' && seg[2] && seg[3] === 'publish' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Only an administrator can approve and publish a report');
            var r4 = DB.reports.filter(function (x) { return x.id === seg[2]; })[0];
            if (!r4) return err(404, 'Not found');
            r4.status = 'published'; r4.published_at = new Date().toISOString(); save(DB); return json(r4);
        }
        if (seg[1] === 'reports' && seg[2] && method === 'PATCH') {
            var r5 = DB.reports.filter(function (x) { return x.id === seg[2]; })[0];
            if (!r5) return err(404, 'Not found');
            if (r5.status === 'published') return err(400, 'Published reports cannot be edited — create a new revision');
            if (r5.status === 'submitted' && user.role !== 'admin') return err(403, 'This report is submitted for review');
            Object.assign(r5, body); save(DB); return json(r5);
        }
        if (p === 'syllabi' && method === 'GET') {
            var rows2 = DB.syllabi.slice();
            if (user.role !== 'admin') {
                var mine = DB.syllabus_assignments.filter(function (a) { return allowedStudent(user, a.student_id) && a.status === 'active'; }).map(function (a) { return a.syllabus_id; });
                rows2 = rows2.filter(function (s) { return mine.indexOf(s.id) !== -1; });
            }
            return json(rows2.map(function (s) {
                return Object.assign({}, s, {
                    items: DB.syllabus_items.filter(function (i) { return i.syllabus_id === s.id; }),
                    assignments: DB.syllabus_assignments.filter(function (a) { return a.syllabus_id === s.id; }).map(function (a) { return { id: a.id, student_id: a.student_id, status: a.status }; })
                });
            }));
        }
        if (p === 'syllabi' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Only an administrator can create a syllabus');
            var syl = Object.assign({ id: uid('sy'), is_active: true, created_at: new Date().toISOString() }, body);
            DB.syllabi.push(syl); save(DB); return json(syl, 201);
        }
        if (seg[1] === 'syllabi' && seg[2] && seg[3] === 'items' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Only an administrator can edit a syllabus');
            var it = Object.assign({ id: uid('si'), syllabus_id: seg[2], sort_order: DB.syllabus_items.length }, body);
            DB.syllabus_items.push(it); save(DB); return json(it, 201);
        }
        if (seg[1] === 'syllabi' && seg[2] && seg[3] === 'assign' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Only an administrator can assign a syllabus');
            var dup = DB.syllabus_assignments.filter(function (a) { return a.syllabus_id === seg[2] && a.student_id === body.student_id && a.enrollment_id === body.enrollment_id; })[0];
            if (dup && dup.status === 'active') return err(409, 'This syllabus is already assigned to that student/enrolment');
            if (dup) { dup.status = 'active'; save(DB); return json({ id: dup.id, status: 'active', reactivated: true }, 201); }
            var sa = { id: uid('sa'), syllabus_id: seg[2], student_id: body.student_id, enrollment_id: body.enrollment_id, instructor_id: body.instructor_id || null, status: 'active', created_at: new Date().toISOString() };
            DB.syllabus_assignments.push(sa); save(DB); return json({ id: sa.id, status: 'active', reactivated: false }, 201);
        }
        if (seg[1] === 'syllabi' && seg[2] && seg[3] === 'assignments' && seg[4] && method === 'PATCH') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            var sa2 = DB.syllabus_assignments.filter(function (a) { return a.id === seg[4]; })[0];
            if (!sa2) return err(404, 'Not found');
            Object.assign(sa2, body); save(DB); return json(sa2);
        }
        if (p === 'syllabus-progress' && method === 'GET') {
            var sid2 = q.student_id;
            if (!allowedStudent(user, sid2)) return err(403, 'Not authorised');
            var prog2 = DB.syllabus_progress.filter(function (x) { return x.student_id === sid2; });
            var done = prog2.filter(function (x) { return x.status === 'completed'; }).length;
            return json({ student_id: sid2, completed: done, total: prog2.length, percent: prog2.length ? Math.round(100 * done / prog2.length) : 0, items: prog2.map(function (x) { var it = DB.syllabus_items.filter(function (i) { return i.id === x.item_id; })[0] || {}; return Object.assign({}, x, { title: it.title, item_type: it.item_type }); }) });
        }
        if (seg[1] === 'syllabus-progress' && seg[2] && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            if (!allowedStudent(user, q.student_id)) return err(403, 'Not authorised');
            var ex = DB.syllabus_progress.filter(function (x) { return x.item_id === seg[2] && x.student_id === q.student_id; })[0];
            if (ex) { Object.assign(ex, body, { updated_at: new Date().toISOString() }); }
            else {
                ex = Object.assign({ id: uid('sp'), item_id: seg[2], student_id: q.student_id, enrollment_id: q.enrollment_id, syllabus_id: (DB.syllabus_items.filter(function (i) { return i.id === seg[2]; })[0] || {}).syllabus_id }, body);
                DB.syllabus_progress.push(ex);
            }
            save(DB); return json(ex, ex.created_at ? 200 : 201);
        }
        if (p === 'exams' && method === 'GET') {
            var ids3 = linkedStudentIds(user);
            return json(DB.exams.filter(function (e) { return ids3 === null ? true : ids3.indexOf(e.student_id) !== -1; }));
        }
        if (p === 'exams' && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            var ex2 = Object.assign({ id: uid('ex'), created_at: new Date().toISOString() }, body);
            DB.exams.push(ex2); save(DB); return json(ex2, 201);
        }
        if (seg[1] === 'exams' && seg[2] && method === 'PATCH') {
            if (!staff) return err(403, 'Staff only');
            var ex3 = DB.exams.filter(function (e) { return e.id === seg[2]; })[0];
            if (!ex3) return err(404, 'Not found');
            Object.assign(ex3, body); save(DB); return json(ex3);
        }
        if (p === 'milestones' && method === 'GET') {
            var ids4 = linkedStudentIds(user);
            return json(DB.milestones.filter(function (m) { return ids4 === null ? true : ids4.indexOf(m.student_id) !== -1; }));
        }
        if (p === 'milestones' && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            var ms = Object.assign({ id: uid('ms'), status: 'planned', created_at: new Date().toISOString() }, body);
            DB.milestones.push(ms); save(DB); return json(ms, 201);
        }
        if (p === 'materials' && method === 'GET') {
            var ids5 = linkedStudentIds(user);
            return json(DB.materials.filter(function (m) {
                if (m.visibility_scope === 'all') return true;
                if (!ids5) return true;
                return ids5.some(function (id) { return allowedStudent(user, id); });
            }));
        }
        if (p === 'materials' && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            var mt = Object.assign({ id: uid('mt'), is_published: true, visibility_scope: body.visibility_scope || 'all', created_at: new Date().toISOString() }, body);
            DB.materials.push(mt); save(DB); return json(mt, 201);
        }
        if (p === 'recommendations' && method === 'GET') return json(DB.recommendations.filter(function (r) { return r.is_active !== false; }));
        if (p === 'recommendations' && method === 'POST') {
            if (!staff) return err(403, 'Staff only');
            var rc = Object.assign({ id: uid('rc'), is_active: true, created_at: new Date().toISOString() }, body);
            DB.recommendations.push(rc); save(DB); return json(rc, 201);
        }
        return err(404, 'Unknown learning route: ' + p);
    }
    function assignmentOut(a) {
        var st = studentById(a.student_id) || {};
        return Object.assign({}, a, { student_name: st.first_name + ' ' + st.last_name, submissions: DB.submissions.filter(function (s) { return s.assignment_id === a.id; }) });
    }

    // ---- billing ----
    function billingRoutes(method, seg, q, body, user) {
        var p = seg.slice(1).join('/');
        if (p === 'packages') return json(DB.packages.filter(function (x) { return x.is_active !== false; }));
        if (p === 'exam-fees') return json(DB.exam_fees || []);   // exam-fee ledger
        if (p === 'payments/config') return json({ enabled: false, key_id: null, currency: 'INR', note: 'Online payments are disabled in this environment. Manual reconciliation only — no payment is ever simulated.' });
        if (p === 'invoices' && method === 'GET') {
            var ids = linkedStudentIds(user);
            var rows = DB.invoices.filter(function (i) { return ids === null ? true : ids.indexOf(i.student_id) !== -1; });
            if (q.student_id) rows = rows.filter(function (i) { return i.student_id === q.student_id; });
            if (q.billing_month) rows = rows.filter(function (i) { return i.billing_month === q.billing_month; });
            return json(rows.map(invoiceOut));
        }
        if (p === 'invoices' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            var enr = DB.enrollments.filter(function (e) { return e.id === body.enrollment_id; })[0];
            if (!enr) return err(404, 'Enrolment not found');
            var dup = DB.invoices.filter(function (i) { return i.enrollment_id === body.enrollment_id && i.billing_month === body.billing_month; })[0];
            if (dup) return err(409, 'An invoice already exists for this enrolment and month');
            var amt = body.amount_paise || (body.charge_type === 'exam' || body.charge_type === 'other' ? body.amount_paise : (enr.fee_plan === '8_classes' ? 800000 : enr.fee_plan === '4_classes' ? 450000 : (enr.fee_amount || 0) * 100));
            var inv = {
                id: uid('inv'), invoice_number: 'CMA/INV/' + body.billing_month.replace('-', '/') + '/' + String(DB.invoices.length + 1).padStart(4, '0'),
                enrollment_id: enr.id, student_id: enr.student_id, billing_month: body.billing_month,
                amount_paise: amt, amount_paid_paise: 0, status: 'pending', charge_type: body.charge_type || 'tuition',
                description: body.description || null, due_date: body.due_date || null, created_at: new Date().toISOString()
            };
            DB.invoices.push(inv); save(DB); return json(invoiceOut(inv), 201);
        }
        if (seg[1] === 'invoices' && seg[2] && seg[3] === 'void' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            var inv2 = DB.invoices.filter(function (i) { return i.id === seg[2]; })[0];
            if (!inv2) return err(404, 'Not found');
            if (inv2.amount_paid_paise > 0) return err(409, 'This invoice has payments — reverse them first, then void');
            inv2.status = 'void'; save(DB); return json(invoiceOut(inv2));
        }
        if (seg[1] === 'invoices' && seg[2]) {
            var inv3 = DB.invoices.filter(function (i) { return i.id === seg[2]; })[0];
            if (!inv3) return err(404, 'Not found');
            if (!allowedStudent(user, inv3.student_id)) return err(403, 'Not authorised');
            return json(invoiceOut(inv3));
        }
        if (p === 'payments' && method === 'GET') {
            var ids2 = linkedStudentIds(user);
            var rows2 = DB.payments.filter(function (x) { return ids2 === null ? true : ids2.indexOf(x.student_id) !== -1; });
            if (q.status) rows2 = rows2.filter(function (x) { return x.status === q.status; });
            return json(rows2);
        }
        if (p === 'payments/manual' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            var inv4 = DB.invoices.filter(function (i) { return i.id === body.allocations[0].invoice_id; })[0];
            if (!inv4) return err(404, 'Invoice not found');
            var pay = {
                id: uid('pay'), provider: 'manual', provider_payment_id: body.reference || 'MANUAL-' + uid('ref'),
                invoice_id: inv4.id, student_id: inv4.student_id, amount_paise: body.amount_paise, currency: 'INR',
                method: body.method || 'cash', status: 'verified', source: 'manual',
                paid_at: body.paid_at || new Date().toISOString().slice(0, 10),
                receipt_number: 'CMA/RCPT/' + new Date().getFullYear() + '/' + String(DB.payments.length + 1).padStart(4, '0'),
                notes: body.notes || 'Admin-recorded payment (not an independently verified bank transaction)'
            };
            DB.payments.push(pay);
            inv4.amount_paid_paise = Math.min(inv4.amount_paise, inv4.amount_paid_paise + body.amount_paise);
            inv4.status = inv4.amount_paid_paise >= inv4.amount_paise ? 'paid' : 'partially_paid';
            save(DB); return json(pay, 201);
        }
        if (p === 'payments/report' && method === 'POST') {
            if (!allowedStudent(user, body.student_id)) return err(403, 'Not authorised');
            var pay2 = {
                id: uid('pay'), provider: 'reported', provider_payment_id: body.reference || 'REPORTED-' + uid('ref'),
                invoice_id: null, student_id: body.student_id, amount_paise: body.amount_paise, currency: 'INR',
                method: body.method, status: 'pending_verification', source: 'reported',
                paid_at: body.paid_at || new Date().toISOString().slice(0, 10), receipt_number: null, notes: body.notes || null
            };
            DB.payments.push(pay2); save(DB);
            return json({ status: 'pending_verification', payment: pay2 }, 201);
        }
        if (seg[1] === 'payments' && seg[2] && seg[3] === 'confirm' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            var pay3 = DB.payments.filter(function (x) { return x.id === seg[2]; })[0];
            if (!pay3) return err(404, 'Not found');
            if (pay3.status === 'verified') return err(409, 'This payment has already been confirmed');
            pay3.status = 'verified';
            pay3.receipt_number = pay3.receipt_number || ('CMA/RCPT/' + new Date().getFullYear() + '/' + String(DB.payments.length + 1).padStart(4, '0'));
            pay3.notes = ((pay3.notes || '') + ' | Confirmed by admin').trim();
            if (pay3.invoice_id) {
                var inv5 = DB.invoices.filter(function (i) { return i.id === pay3.invoice_id; })[0];
                if (inv5) {
                    inv5.amount_paid_paise = Math.min(inv5.amount_paise, inv5.amount_paid_paise + pay3.amount_paise);
                    inv5.status = inv5.amount_paid_paise >= inv5.amount_paise ? 'paid' : 'partially_paid';
                }
            }
            DB.audit.push({ id: uid('a'), action: 'payment.confirmed_by_admin', entity: pay3.id, at: new Date().toISOString(), by: user.username });
            save(DB); return json(Object.assign({}, pay3, { allocations: [] }));
        }
        if (seg[1] === 'payments' && seg[2] && seg[3] === 'receipt') {
            var pay4 = DB.payments.filter(function (x) { return x.id === seg[2]; })[0];
            if (!pay4) return err(404, 'Not found');
            if (!allowedStudent(user, pay4.student_id) && user.role !== 'admin') return err(403, 'Not authorised');
            var html = '<!DOCTYPE html><title>Receipt ' + (pay4.receipt_number || '') + '</title><body style="font-family:Georgia,serif;max-width:600px;margin:40px auto"><h1>ChankArts Music Academy — Receipt</h1><p>Receipt no. <b>' + (pay4.receipt_number || '—') + '</b></p><p>Amount: <b>₹' + (pay4.amount_paise / 100).toFixed(2) + '</b> · Method: ' + pay4.method + '<br>Reference: ' + (pay4.provider_payment_id || '—') + '<br>Date: ' + pay4.paid_at + '</p><p style="color:#666;font-size:12px">Preview receipt (demo data). ' + (pay4.source === 'manual' ? 'Admin-recorded payment — not an independently verified bank transaction.' : '') + '</p></body>';
            return new Response(html, { status: 200, headers: { 'Content-Type': 'text/html' } });
        }
        if (p === 'statement') {
            var ids3 = linkedStudentIds(user) || [];
            if (q.student_id && allowedStudent(user, q.student_id)) ids3 = [q.student_id];
            var students = ids3.map(function (sid) {
                var st = studentById(sid);
                var charges = DB.invoices.filter(function (i) { return i.student_id === sid && i.status !== 'void'; }).map(invoiceOut);
                var pays = DB.payments.filter(function (x) { return x.student_id === sid; });
                return {
                    student_id: sid, student_name: st ? st.first_name + ' ' + st.last_name : sid,
                    cma_registration_id: st ? st.cma_registration_id : null,
                    charges: charges, payments: pays, credits: DB.credits.filter(function (c) { return c.student_id === sid; }),
                    exam_fees: [], 
                    totals: {
                        charged_paise: charges.reduce(function (a, c) { return a + c.amount_paise; }, 0),
                        paid_paise: charges.reduce(function (a, c) { return a + c.amount_paid_paise; }, 0),
                        outstanding_paise: charges.reduce(function (a, c) { return a + Math.max(c.amount_paise - c.amount_paid_paise, 0); }, 0),
                        credit_balance_paise: 0
                    }
                };
            });
            return json({ students: students, totals: students.reduce(function (a, s) { return { charged_paise: a.charged_paise + s.totals.charged_paise, paid_paise: a.paid_paise + s.totals.paid_paise, outstanding_paise: a.outstanding_paise + s.totals.outstanding_paise, credit_balance_paise: 0 }; }, { charged_paise: 0, paid_paise: 0, outstanding_paise: 0, credit_balance_paise: 0 }) });
        }
        if (p === 'statement/export') {
            var csv = 'student,type,reference,period,description,charged_paise,paid_paise,status\n';
            DB.invoices.forEach(function (i) {
                var st = studentById(i.student_id) || {};
                csv += [st.first_name + ' ' + st.last_name, 'charge', i.invoice_number, i.billing_month, (i.description || i.charge_type), i.amount_paise, i.amount_paid_paise, i.status].join(',') + '\n';
            });
            return new Response(csv, { status: 200, headers: { 'Content-Type': 'text/csv', 'Content-Disposition': 'attachment; filename=statement.csv' } });
        }
        if (p === 'generate-charges' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            var created = [], skipped = [];
            DB.enrollments.forEach(function (e) {
                if (e.status !== 'active') return;
                if (DB.invoices.some(function (i) { return i.enrollment_id === e.id && i.billing_month === body.billing_month; })) {
                    skipped.push({ enrollment_id: e.id, reason: 'already_exists' }); return;
                }
                var amt = e.fee_plan === '8_classes' ? 800000 : e.fee_plan === '4_classes' ? 450000 : null;
                if (!amt) { skipped.push({ enrollment_id: e.id, reason: 'no_fee_amount' }); return; }
                var inv6 = {
                    id: uid('inv'), invoice_number: 'CMA/INV/' + body.billing_month.replace('-', '/') + '/' + String(DB.invoices.length + 1).padStart(4, '0'),
                    enrollment_id: e.id, student_id: e.student_id, billing_month: body.billing_month,
                    amount_paise: amt, amount_paid_paise: 0, status: 'pending', charge_type: 'tuition',
                    description: 'Monthly tuition ' + body.billing_month + ' (' + e.fee_plan + ')', due_date: body.billing_month + '-' + String(body.due_day || 5).padStart(2, '0'),
                    created_at: new Date().toISOString()
                };
                DB.invoices.push(inv6);
                created.push({ enrollment_id: e.id, invoice: inv6.invoice_number, amount_paise: amt });
            });
            save(DB); return json({ billing_month: body.billing_month, created: created, skipped: skipped });
        }
        if (p === 'reports/collections') {
            var month = q.billing_month;
            var invs = DB.invoices.filter(function (i) { return i.billing_month === month; });
            var paysM = DB.payments.filter(function (x) { return (x.paid_at || '').slice(0, 7) === month; });
            var byMethod = {};
            paysM.forEach(function (x) { byMethod[x.method] = byMethod[x.method] || { count: 0, amount_paise: 0 }; byMethod[x.method].count++; byMethod[x.method].amount_paise += x.amount_paise; });
            return json({
                billing_month: month,
                charges_by_type: { tuition: { count: invs.length, charged_paise: invs.reduce(function (a, i) { return a + i.amount_paise; }, 0), paid_paise: invs.reduce(function (a, i) { return a + i.amount_paid_paise; }, 0), outstanding_paise: invs.reduce(function (a, i) { return a + Math.max(i.amount_paise - i.amount_paid_paise, 0); }, 0) } },
                collections_by_method: byMethod,
                totals: { charged_paise: invs.reduce(function (a, i) { return a + i.amount_paise; }, 0), collected_paise: paysM.reduce(function (a, x) { return a + x.amount_paise; }, 0), outstanding_paise: invs.reduce(function (a, i) { return a + Math.max(i.amount_paise - i.amount_paid_paise, 0); }, 0) }
            });
        }
        if (p === 'credits/advance' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            var c = { id: uid('cr'), student_id: body.student_id, kind: 'advance', amount_paise: body.amount_paise, note: body.notes || 'Advance credit', created_at: new Date().toISOString() };
            DB.credits.push(c); save(DB); return json({ credit_entry_id: c.id, balance_paise: DB.credits.filter(function (x) { return x.student_id === body.student_id; }).reduce(function (a, x) { return a + x.amount_paise; }, 0) }, 201);
        }
        if (p === 'credits/apply' && method === 'POST') {
            if (user.role !== 'admin') return err(403, 'Administrators only');
            DB.credits.push({ id: uid('cr'), student_id: body.student_id, kind: 'applied', amount_paise: -body.amount_paise, invoice_id: body.invoice_id, note: body.note, created_at: new Date().toISOString() });
            var inv7 = DB.invoices.filter(function (i) { return i.id === body.invoice_id; })[0];
            if (inv7) { inv7.amount_paid_paise = Math.min(inv7.amount_paise, inv7.amount_paid_paise + body.amount_paise); inv7.status = inv7.amount_paid_paise >= inv7.amount_paise ? 'paid' : 'partially_paid'; }
            save(DB); return json({ applied_paise: body.amount_paise, invoice: inv7 ? invoiceOut(inv7) : null });
        }
        return err(404, 'Unknown billing route: ' + p);
    }
    function invoiceOut(i) {
        return Object.assign({}, i, {
            outstanding_paise: Math.max(i.amount_paise - i.amount_paid_paise, 0),
            is_overdue: i.due_date ? (i.due_date < new Date().toISOString().slice(0, 10) && i.status !== 'paid') : false
        });
    }

    // ---- admin ----
    function adminRoutes(method, seg, q, body, user) {
        if (user.role !== 'admin') return err(403, 'Administrator access required');
        var p = seg.slice(1).join('/');
        if (p === 'dashboard/stats') {
            var today = new Date().toISOString().slice(0, 10);
            var upcoming = DB.sessions.filter(function (s) { return s.status === 'scheduled' && s.scheduled_date >= today; });
            return json({
                total_students: DB.students.length, active_students: DB.students.filter(function (s) { return s.status === 'active'; }).length,
                total_instructors: DB.instructors.length, todays_classes: DB.sessions.filter(function (s) { return s.scheduled_date === today; }).length,
                upcoming_classes: upcoming.length,
                pending_fee_records: DB.invoices.filter(function (i) { return i.status !== 'paid' && i.status !== 'void'; }).length,
                collected_this_month: DB.payments.filter(function (x) { return (x.paid_at || '').slice(0, 7) === new Date().toISOString().slice(0, 7); }).reduce(function (a, x) { return a + x.amount_paise; }, 0),
                outstanding_total: DB.invoices.reduce(function (a, i) { return a + Math.max(i.amount_paise - i.amount_paid_paise, 0); }, 0),
                recent_activity: DB.audit.slice(-8).reverse()
            });
        }
        if (p === 'students' && method === 'GET') return json(DB.students.map(studentOut));
        if (p === 'students' && method === 'POST') {
            if (!body.first_name || !body.last_name) return err(400, 'First and last name are required');
            var num = DB.students.length + 1;
            var nu = { id: uid('u'), username: body.login_id || ('CMA-' + String(num).padStart(3, '0')), email: body.email || null, role: 'student', is_active: true, must_change_pin: true, created_at: new Date().toISOString() };
            nu.pin_salt = 'chankarts-preview-salt'; nu.pin_hash = null; nu.__demo_pin = body.temp_pin || '0000';
            DB.users.push(nu);
            var s = {
                id: uid('st'), user_id: nu.id, first_name: body.first_name, last_name: body.last_name,
                cma_registration_id: body.cma_registration_id || ('CMA-2026-' + String(num).padStart(4, '0')),
                login_id: nu.username, status: 'active', date_of_birth: body.date_of_birth || null,
                phone: body.phone || null, skill_level: body.skill_level || null, notes: body.notes || null,
                created_at: new Date().toISOString()
            };
            DB.students.push(s);
            if (body.guardians && body.guardians.length) {
                body.guardians.forEach(function (g) {
                    var gu = { id: uid('u'), username: 'guardian-' + uid('g'), email: g.email || null, role: 'parent', is_active: true, must_change_pin: true, created_at: new Date().toISOString() };
                    gu.pin_salt = 'chankarts-preview-salt'; gu.pin_hash = null; gu.__demo_pin = '0000';
                    DB.users.push(gu);
                    DB.guardian_accounts.push({ id: uid('g'), user_id: gu.id, student_id: s.id, relationship: g.relationship || 'parent' });
                });
            }
            if (body.enrollment && body.enrollment.programme_name) {
                DB.enrollments.push(Object.assign({ id: uid('en'), student_id: s.id, status: 'active', start_date: new Date().toISOString().slice(0, 10), created_at: new Date().toISOString() }, body.enrollment));
            }
            DB.audit.push({ id: uid('a'), action: 'student.created', entity: s.id, at: new Date().toISOString(), by: user.username });
            save(DB); return json(Object.assign({ temp_pin: nu.__demo_pin }, studentOut(s)), 201);
        }
        if (seg[1] === 'students' && seg[2] && seg[3] === 'reset-pin' && method === 'POST') {
            var su = DB.students.filter(function (x) { return x.id === seg[2]; })[0];
            if (!su) return err(404, 'Not found');
            var uu = userById(su.user_id);
            var pin = String(Math.floor(1000 + Math.random() * 9000));
            uu.pin_salt = 'chankarts-preview-salt'; uu.pin_hash = null; uu.__demo_pin = pin; uu.must_change_pin = true;
            save(DB); return json({ new_pin: pin, must_change_pin: true });
        }
        if (seg[1] === 'students' && seg[2] && method === 'PATCH') {
            var su2 = DB.students.filter(function (x) { return x.id === seg[2]; })[0];
            if (!su2) return err(404, 'Not found');
            Object.assign(su2, body);
            if (body.status) { var u2 = userById(su2.user_id); if (u2) u2.is_active = body.status === 'active'; }
            save(DB); return json(studentOut(su2));
        }
        if (seg[1] === 'students' && seg[2] && method === 'DELETE') {
            var su3 = DB.students.filter(function (x) { return x.id === seg[2]; })[0];
            if (!su3) return err(404, 'Not found');
            var hasHistory = DB.enrollments.some(function (e) { return e.student_id === su3.id; }) || DB.sessions.some(function (s) { return s.student_id === su3.id; });
            if (hasHistory) return err(409, 'This student has enrolment or class history — archive instead of deleting');
            DB.students = DB.students.filter(function (x) { return x.id !== su3.id; });
            save(DB); return json({ deleted: true, id: seg[2] });
        }
        if (seg[1] === 'students' && seg[2]) {
            var su4 = DB.students.filter(function (x) { return x.id === seg[2]; })[0];
            if (!su4) return err(404, 'Not found');
            return json(studentOut(su4));
        }
        if (p === 'instructors' && method === 'GET') return json(DB.instructors.map(function (i) { return Object.assign({}, i, { full_name: i.first_name + ' ' + i.last_name, login_id: (userById(i.user_id) || {}).username }); }));
        if (p === 'instructors' && method === 'POST') {
            var iu = { id: uid('u'), username: body.login_id || ('instructor' + (DB.instructors.length + 1)), email: body.email || null, role: 'instructor', is_active: true, must_change_pin: true, created_at: new Date().toISOString() };
            iu.pin_salt = 'chankarts-preview-salt'; iu.pin_hash = null; iu.__demo_pin = body.temp_pin || '0000';
            DB.users.push(iu);
            var ins = { id: uid('ins'), user_id: iu.id, first_name: body.first_name, last_name: body.last_name, specializations: body.specializations || '', qualifications: body.qualifications || '', experience_years: body.experience_years || null, is_active: true };
            DB.instructors.push(ins); save(DB); return json(Object.assign({ temp_pin: iu.__demo_pin }, ins), 201);
        }
        if (seg[1] === 'instructors' && seg[2] && seg[3] === 'impact') {
            var iid = seg[2];
            return json({ enrollments: DB.enrollments.filter(function (e) { return e.instructor_id === iid; }).length, sessions: DB.sessions.filter(function (s) { return s.instructor_id === iid; }).length });
        }
        if (seg[1] === 'instructors' && seg[2] && method === 'PATCH') {
            var ins2 = DB.instructors.filter(function (x) { return x.id === seg[2]; })[0];
            if (!ins2) return err(404, 'Not found');
            if (body.is_active === false && DB.sessions.some(function (s) { return s.instructor_id === ins2.id && s.status === 'scheduled'; }) && !body.acknowledge_future_classes) {
                return err(409, 'This instructor has upcoming classes — confirm to deactivate (classes keep their records)');
            }
            Object.assign(ins2, body);
            var iu2 = userById(ins2.user_id); if (iu2 && body.is_active !== undefined) iu2.is_active = body.is_active;
            save(DB); return json(ins2);
        }
        if (seg[1] === 'instructors' && seg[2] && method === 'DELETE') {
            var ins3 = DB.instructors.filter(function (x) { return x.id === seg[2]; })[0];
            if (!ins3) return err(404, 'Not found');
            if (DB.enrollments.some(function (e) { return e.instructor_id === ins3.id; }) || DB.sessions.some(function (s) { return s.instructor_id === ins3.id; })) {
                return err(409, 'This instructor has teaching history — deactivate instead of deleting');
            }
            DB.instructors = DB.instructors.filter(function (x) { return x.id !== ins3.id; });
            save(DB); return json({ deleted: true });
        }
        if (p === 'fees') return json(DB.invoices.map(invoiceOut));
        if (p === 'settings') return json({ fee_packages: DB.packages, razorpay: { enabled: false, mode: 'disabled' } });
        if (p === 'reports/class-completion') {
            var rows = DB.sessions.map(sessionOut);
            return json({
                totals: {
                    total: rows.length, completed: rows.filter(function (r) { return r.status === 'completed'; }).length,
                    scheduled_upcoming: rows.filter(function (r) { return r.status === 'scheduled' && r.scheduled_date >= new Date().toISOString().slice(0, 10); }).length,
                    awaiting_update: rows.filter(function (r) { return r.status === 'scheduled' && r.scheduled_date < new Date().toISOString().slice(0, 10); }).length,
                    cancelled: rows.filter(function (r) { return r.status === 'cancelled'; }).length,
                    rescheduled: rows.filter(function (r) { return r.status === 'rescheduled'; }).length,
                    reschedule_requested: rows.filter(function (r) { return r.status === 'rescheduling_required'; }).length,
                    completion_rate_pct: 0, last_completion_update: null
                },
                by_instructor: [{ instructor_id: DB.instructors[0].id, instructor_name: DB.instructors[0].first_name + ' ' + DB.instructors[0].last_name, login_id: 'instructor1', completed: rows.filter(function (r) { return r.status === 'completed'; }).length, awaiting_update: rows.filter(function (r) { return r.status === 'scheduled' && r.scheduled_date < new Date().toISOString().slice(0, 10); }).length, scheduled_upcoming: rows.filter(function (r) { return r.status === 'scheduled' && r.scheduled_date >= new Date().toISOString().slice(0, 10); }).length, rescheduled: 0, reschedule_requested: rows.filter(function (r) { return r.status === 'rescheduling_required'; }).length, cancelled: 0, last_completion: null, lesson_notes: [] }],
                sessions: rows
            });
        }
        if (p === 'pin-reset-requests') return json(DB.pin_reset_requests);
        if (seg[1] === 'pin-reset-requests' && seg[2] && (seg[3] === 'approve' || seg[3] === 'reject') && method === 'POST') {
            var pr = DB.pin_reset_requests.filter(function (x) { return x.id === seg[2]; })[0];
            if (!pr) return err(404, 'Not found');
            pr.status = seg[3] === 'approve' ? 'approved' : 'rejected';
            pr.reviewed_at = new Date().toISOString();
            var pinOut = null;
            if (seg[3] === 'approve') {
                var target = DB.users.filter(function (x) { return x.username === pr.username; })[0];
                if (target) { pinOut = String(Math.floor(1000 + Math.random() * 9000)); target.pin_salt = 'chankarts-preview-salt'; target.pin_hash = null; target.__demo_pin = pinOut; target.must_change_pin = true; }
            }
            save(DB); return json(Object.assign({}, pr, pinOut ? { new_pin: pinOut } : {}));
        }
        if (p === 'registration-requests') return json(DB.registration_requests);
        if (seg[1] === 'registration-requests' && seg[2] && seg[3] === 'status' && method === 'PATCH') {
            var rr = DB.registration_requests.filter(function (x) { return x.id === seg[2]; })[0];
            if (!rr) return err(404, 'Not found');
            rr.status = body.status; rr.reviewed_at = new Date().toISOString(); rr.account_created = false;
            save(DB); return json(rr);
        }
        if (seg[1] === 'enrollments' && seg[2] && seg[3] === 'instructor' && method === 'POST') {
            var e2 = DB.enrollments.filter(function (x) { return x.id === seg[2]; })[0];
            if (!e2) return err(404, 'Not found');
            e2.instructor_id = body.instructor_id || null;
            DB.sessions.forEach(function (s) { if (s.enrollment_id === e2.id && (s.status === 'scheduled' || s.status === 'rescheduling_required')) s.instructor_id = e2.instructor_id; });
            save(DB); return json({ enrollment_id: e2.id, instructor_id: e2.instructor_id, schedule_rows_updated: 0 });
        }
        if (seg[1] === 'enrollments' && seg[2] && method === 'PATCH') {
            var e3 = DB.enrollments.filter(function (x) { return x.id === seg[2]; })[0];
            if (!e3) return err(404, 'Not found');
            Object.assign(e3, body); save(DB); return json(e3);
        }
        return err(404, 'Unknown admin route: ' + p);
    }

    function supportRoutes(method, seg, body, user, q) {
        var isAdminRoute = seg[0] === 'admin';
        if (seg[1] === 'support' && !seg[2] && method === 'GET') {
            var rows = isAdminRoute ? DB.support_requests.slice() : DB.support_requests.filter(function (r) { return r.sender_user_id === user.id; });
            return json(rows);
        }
        if (seg[seg.length - 1] === 'support' && method === 'POST' && !isAdminRoute) {
            var req = { id: uid('sr'), sender_user_id: user.id, sender_role: user.role, subject: body.subject, message: body.message, status: 'open', created_at: new Date().toISOString(), updated_at: new Date().toISOString(), replies: [] };
            DB.support_requests.push(req); save(DB); return json(req, 201);
        }
        if (seg[1] === 'support' && seg[2] && !seg[3] && method === 'GET') {
            var req2 = DB.support_requests.filter(function (r) { return r.id === seg[2]; })[0];
            if (!req2) return err(404, 'Not found');
            if (!isAdminRoute && req2.sender_user_id !== user.id) return err(403, 'Not authorised');
            return json(Object.assign({}, req2, { replies: DB.support_replies.filter(function (x) { return x.request_id === req2.id; }) }));
        }
        if (seg[1] === 'support' && seg[2] && seg[3] === 'reply' && method === 'POST') {
            var req3 = DB.support_requests.filter(function (r) { return r.id === seg[2]; })[0];
            if (!req3) return err(404, 'Not found');
            if (!isAdminRoute && req3.sender_user_id !== user.id) return err(403, 'Not authorised');
            var rep = { id: uid('sr2'), request_id: req3.id, author_role: user.role, body: body.body, created_at: new Date().toISOString() };
            DB.support_replies.push(rep);
            req3.status = isAdminRoute ? 'replied' : 'open';
            req3.updated_at = new Date().toISOString();
            save(DB); return json(rep, 201);
        }
        if (seg[1] === 'support' && seg[2] && seg[3] === 'status' && method === 'POST') {
            var req4 = DB.support_requests.filter(function (r) { return r.id === seg[2]; })[0];
            if (!req4) return err(404, 'Not found');
            req4.status = body.status; req4.updated_at = new Date().toISOString();
            save(DB); return json(req4);
        }
        return err(404, 'Unknown support route');
    }

    // banner: honest environment label
    document.addEventListener('DOMContentLoaded', function () {
        var b = document.createElement('div');
        b.id = 'previewBanner';
        b.style.cssText = 'position:fixed;bottom:0;left:0;right:0;z-index:9999;background:#1c1a15;color:#f4efe6;font:12px/1.5 -apple-system,sans-serif;padding:8px 14px;border-top:2px solid #B58A35;text-align:center';
        b.innerHTML = '<strong>Preview environment.</strong> The full academy demo (16 students, schedules, fees, reports) is saved <strong>in this browser</strong> — not a production database. Sign in with your academy register credentials (CMA-001…CMA-014, admin, instructor1, parent1). The production API lives in <code>backend/</code>.';
        document.body.appendChild(b);
        document.body.style.paddingBottom = '44px';
    });
})();
