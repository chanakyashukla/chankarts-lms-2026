/* Tour engine + tour definitions test.
 * Run: node tests/test_tour_engine.js  (exit code 0 = pass)
 *
 * Covers: bubble placement never leaves the viewport, target fallback
 * chains, step-list integrity (ids, sections, targets), topic tutorials
 * only reference existing steps, and role separation (student tour never
 * contains instructor-only steps and vice versa).
 */
const fs = require('fs');
const path = require('path');

const FRONTEND = path.join(__dirname, '..', 'frontend', 'js');

function loadScript(name, windowObj) {
    const src = fs.readFileSync(path.join(FRONTEND, name), 'utf8');
    windowObj.location = windowObj.location || { pathname: '/academy/portal/dashboard', hostname: 'academy.chankarts.com' };
    const fn = new Function('window', 'document', 'location', 'localStorage',
        'fetch', 'console', 'requestAnimationFrame', src);
    fn(windowObj,
        { createElement: () => ({ style: {}, setAttribute() {}, appendChild() {}, addEventListener() {}, querySelector: () => null, focus() {} }),
          querySelector: () => null, body: { appendChild() {} }, addEventListener() {} },
        windowObj.location,
        { getItem: () => null, setItem() {}, removeItem() {} },
        () => Promise.resolve({ ok: true, json: () => Promise.resolve({}) }),
        { log() {}, warn() {}, error() {} },
        (cb) => cb());
    return windowObj;
}

let failures = 0;
function check(cond, msg) {
    if (cond) {
        console.log('  ok -', msg);
    } else {
        failures++;
        console.error('  FAIL -', msg);
    }
}

// ---------------------------------------------------------------------------
console.log('tour-engine.js');
const win1 = {};
loadScript('tour-engine.js', win1);
const Engine = win1.TourEngine;
check(!!Engine && typeof Engine.start === 'function', 'exposes start()');
check(typeof Engine.computeBubblePosition === 'function', 'exposes computeBubblePosition()');

// --- bubble placement: never outside the viewport ---
const vw = 1280, vh = 800;
const cases = [
    ['room below', { top: 100, left: 200, width: 300, height: 120 }, 340, 200],
    ['room above', { top: 640, left: 200, width: 300, height: 120 }, 340, 200],
    ['cramped middle', { top: 380, left: 600, width: 80, height: 40 }, 340, 200],
    ['near right edge', { top: 100, left: 1240, width: 40, height: 40 }, 340, 200],
    ['near left edge', { top: 100, left: 0, width: 40, height: 40 }, 340, 200],
    ['tall target', { top: 0, left: 400, width: 400, height: 800 }, 340, 200],
];
for (const [label, rect, bw, bh] of cases) {
    const pos = Engine.computeBubblePosition(rect, bw, bh, vw, vh, 14);
    check(pos.top >= 12 && pos.top + bh <= vh - 12,
        `${label}: top in viewport (${pos.top}..${pos.top + bh})`);
    check(pos.left >= 12 && pos.left + bw <= vw - 12,
        `${label}: left in viewport (${pos.left}..${pos.left + bw})`);
    check(pos.placement === 'above' || pos.placement === 'below',
        `${label}: placement is above/below (${pos.placement})`);
}
// roomy target below → bubble goes below; near top → above
const belowPos = Engine.computeBubblePosition({ top: 100, left: 400, width: 300, height: 100 }, 340, 200, vw, vh, 14);
check(belowPos.placement === 'below', 'room below → placement below');
const abovePos = Engine.computeBubblePosition({ top: 640, left: 400, width: 300, height: 120 }, 340, 200, vw, vh, 14);
check(abovePos.placement === 'above', 'room above → placement above');

// --- mobile viewport (bubble capped at 100vw - 24px by CSS) ---
const mW = Math.min(366, 390 - 24);
const mpos = Engine.computeBubblePosition({ top: 100, left: 10, width: 370, height: 80 }, mW, 300, 390, 844, 14);
check(mpos.left >= 12 && mpos.left + mW <= 390 - 12, 'mobile: bubble fits 390px width');

// --- resolveTarget fallback chains (needs a real querySelector) ---
const fakeEls = { '#exists': { id: 'a' }, '#also': { id: 'b' } };
const docStub = {
    querySelector: (sel) => fakeEls[sel] || null,
    createElement: () => ({ style: {}, setAttribute() {}, appendChild() {}, addEventListener() {} }),
    body: { appendChild() {} },
    addEventListener() {},
};
const win2 = {};
(function () {
    const src = fs.readFileSync(path.join(FRONTEND, 'tour-engine.js'), 'utf8');
    new Function('window', 'document', 'location', 'localStorage', 'fetch', 'console',
        'requestAnimationFrame', src)(
        win2, docStub, { pathname: '/academy/portal/dashboard', hostname: 'x' },
        { getItem: () => null }, () => Promise.resolve({ ok: true, json: () => ({}) }),
        { log() {}, warn() {}, error() {} }, (cb) => cb());
})();
check(win2.TourEngine.resolveTarget('#missing, #exists') === fakeEls['#exists'] ||
      win2.TourEngine.resolveTarget(['#missing', '#exists']) === fakeEls['#exists'],
    'resolveTarget: array fallback picks first match');
check(win2.TourEngine.resolveTarget(['#missing1', '#missing2']) === null,
    'resolveTarget: all-missing chain returns null (step is skipped)');
check(win2.TourEngine.resolveTarget(() => fakeEls['#also']) === fakeEls['#also'],
    'resolveTarget: function targets supported');

// ---------------------------------------------------------------------------
console.log('tours.js');
const win3 = {};
loadScript('tours.js', win3);
const Tours = win3.Tours;
check(!!Tours && typeof Tours.maybeAutoLaunch === 'function', 'exposes maybeAutoLaunch()');
check(typeof Tours.helpCentreHtml === 'function', 'exposes helpCentreHtml()');

const VALID_SECTIONS = new Set(['dashboard', 'classes', 'billing', 'assignments',
    'materials', 'reports', 'syllabus', 'exams', 'achievements', 'resources',
    'remarks', 'profile', 'help']);

function validateSteps(steps, label) {
    const ids = new Set();
    for (const s of steps) {
        check(!!s.id, `${label}: step has id`);
        check(!ids.has(s.id), `${label}: step id "${s.id}" unique`);
        ids.add(s.id);
        check(!!s.title && s.title.length > 3, `${label}: "${s.id}" has title`);
        check(!!s.text && s.text.length > 40, `${label}: "${s.id}" has explanation text`);
        check(VALID_SECTIONS.has(s.section), `${label}: "${s.id}" section "${s.section}" is a real portal section`);
        check(!!s.target, `${label}: "${s.id}" has a target`);
        check(typeof s.target === 'function' || (Array.isArray(s.target) && s.target.length > 0) || typeof s.target === 'string',
            `${label}: "${s.id}" target is selector/array/function`);
        // no target may be empty-string or obviously broken
        if (Array.isArray(s.target)) {
            check(s.target.every((t) => typeof t === 'string' && t.length > 0),
                `${label}: "${s.id}" fallback selectors non-empty`);
        }
    }
}

validateSteps(Tours.STUDENT_STEPS, 'student tour');
validateSteps(Tours.INSTRUCTOR_STEPS, 'instructor tour');

// role separation
const studentIds = Tours.STUDENT_STEPS.map((s) => s.id);
const instructorIds = Tours.INSTRUCTOR_STEPS.map((s) => s.id);
check(studentIds.includes('billing'), 'student tour covers fees/billing');
check(!instructorIds.includes('billing'), 'instructor tour has no billing step');
check(instructorIds.includes('mark-complete'), 'instructor tour covers marking classes completed');
check(!studentIds.includes('mark-complete'), 'student tour has no mark-complete step');
check(studentIds.includes('syllabus') && instructorIds.includes('help'), 'both tours cover their required topics');

// every spec topic for students is present
for (const topic of ['dashboard', 'classes', 'assignments', 'syllabus', 'billing', 'help', 'profile']) {
    check(studentIds.includes(topic), `student tour includes required topic "${topic}"`);
}
// instructor spec topics
for (const topic of ['dashboard', 'classes', 'mark-complete', 'assignments', 'materials', 'reports', 'help', 'profile']) {
    check(instructorIds.includes(topic), `instructor tour includes required topic "${topic}"`);
}

// topics reference existing step ids
function validateTopics(topics, steps, label) {
    const ids = new Set(steps.map((s) => s.id));
    for (const [key, refs] of Object.entries(topics)) {
        if (refs === null) continue; // full-tour marker
        check(Array.isArray(refs) && refs.length > 0, `${label}: topic "${key}" non-empty`);
        for (const r of refs) {
            check(ids.has(r), `${label}: topic "${key}" references existing step "${r}"`);
        }
    }
}
validateTopics(Tours.STUDENT_TOPICS, Tours.STUDENT_STEPS, 'student topics');
validateTopics(Tours.INSTRUCTOR_TOPICS, Tours.INSTRUCTOR_STEPS, 'instructor topics');

// help centre: role-appropriate content, replay + topics + written help
const studentHtml = Tours.helpCentreHtml(); // storedRole() → null → student branch
check(studentHtml.includes('Replay Guided Tour'), 'help centre has Replay Guided Tour');
check(studentHtml.includes('data-action="tour-replay"'), 'replay button wired to tour-replay action');
check(studentHtml.includes('data-action="tour-topic"'), 'topic buttons wired to tour-topic action');
check(studentHtml.includes('How to View and Pay Fees'), 'student help lists fee topic');
check(studentHtml.includes('<details'), 'written help (FAQ) present');
check(!studentHtml.includes('Mark Classes Completed'), 'student help has no instructor-only topic');

console.log(failures === 0 ? '\nAll tour tests passed.' : `\n${failures} failure(s).`);
process.exit(failures === 0 ? 0 : 1);
