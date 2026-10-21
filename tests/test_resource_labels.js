/**
 * Resource link label: generic external resource URLs must be labelled
 * "Link" (never "Buy Link") on the student portal; admin screens use a
 * neutral "Open" label.  No genuine purchase-field behaviour is touched.
 */
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..', 'frontend', 'js');
const portal = fs.readFileSync(path.join(root, 'portal.js'), 'utf8');
const admin = fs.readFileSync(path.join(root, 'admin.js'), 'utf8');

let failures = 0;
function check(ok, label) {
    if (ok) console.log(`✓ ${label}`);
    else { console.error(`✗ ${label}`); failures++; }
}

check(!/Buy Link/.test(portal), 'portal.js has no "Buy Link" label');
check(/external_url[\s\S]{0,200}>\s*Link\s*</.test(portal) ||
      />\s*Link\s*<\/a>/.test(portal),
      'portal.js renders generic resource URL as "Link"');
check(!/Buy Link/.test(admin), 'admin.js has no "Buy Link" label');
check(/external_url[\s\S]{0,120}Open<\/a>/.test(admin),
      'admin.js keeps neutral "Open" label for resource URLs');

if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
}
console.log('all resource-label checks passed');
