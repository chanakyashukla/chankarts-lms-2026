/* Preview-gate test: the browser-local demo adapter must NEVER activate on
 * the Render production domain (or any non-GitHub, non-localhost host), so
 * every real LMS request goes to the same-origin FastAPI backend.
 * Run: node tests/test_preview_gate.js  (exit code 0 = pass) */
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'js', 'preview-api.js'), 'utf8');

function evaluateGate(hostname, search, sticky) {
    const store = { getItem: (k) => (k === 'chankarts-preview-on' && sticky ? '1' : null), setItem: () => {}, removeItem: () => {} };
    const wrapped = { count: 0 };
    const fetchStub = () => { wrapped.count++; };
    const windowObj = { fetch: fetchStub };
    const location = { hostname, search };
    const localStorage = store;
    const document = { addEventListener: () => {}, createElement: () => ({}), head: { appendChild: () => {} } };
    try {
        // evaluate the IIFE with stubbed globals
        new Function('window', 'location', 'localStorage', 'document', 'fetch', src)(
            windowObj, location, localStorage, document, fetchStub);
    } catch (e) {
        console.error('gate evaluation error:', e.message);
        process.exit(1);
    }
    return { preview: windowObj.PREVIEW_MODE === true, fetchWrapped: wrapped.count > 0 };
}

const cases = [
    ['chankarts-lms-2026.onrender.com', '', false, false, 'Render production host must NOT activate the demo'],
    ['academy.chankarts.com', '?preview=1', true, false, 'production domain ignores even ?preview=1'],
    ['chankarts-lms-2026.onrender.com', '', true, false, 'sticky flag ignored outside allowed hosts'],
    ['chanakyashukla.github.io', '', false, true, 'GitHub Pages demo DOES activate'],
    ['chanakyashukla.github.io', '?preview=1', false, true, 'GitHub Pages with flag activates'],
    ['localhost', '?preview=1', false, true, 'local dev with flag activates'],
    ['127.0.0.1', '', false, false, 'local without flag uses the real backend'],
];

let failed = 0;
for (const [host, search, sticky, expect, why] of cases) {
    const r = evaluateGate(host, search, sticky);
    const ok = r.preview === expect;
    const wrapOk = expect ? true : r.fetchWrapped === false; // when demo off, fetch must be untouched
    if (!ok || !wrapOk) failed++;
    console.log(`${ok && wrapOk ? '✓' : '✗'} ${host}${search} sticky=${sticky} -> PREVIEW_MODE=${r.preview} (expected ${expect}) — ${why}`);
}
console.log(failed === 0 ? `\nall ${cases.length} gate cases passed` : `\n${failed} FAILED`);
process.exit(failed ? 1 : 0);
