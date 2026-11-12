/* ChankArts — reusable guided-tour engine.
 *
 * Spotlight + floating bubble over the LIVE interface (no fake screenshots).
 * Supports: role-specific step lists, cross-page navigation, waiting for
 * async content, graceful skipping of missing targets, responsive bubble
 * placement, keyboard navigation and progress callbacks.
 *
 * Loaded before tours.js. Depends on nothing but the DOM.
 */
window.TourEngine = (function () {
    'use strict';

    var active = null;          // { steps, index, opts, els, ... }
    var Z_OVERLAY = 1200;
    var Z_SPOT = 1201;
    var Z_BUBBLE = 1202;
    var TARGET_WAIT_MS = 4500;  // async section loaders
    var POLL_MS = 120;
    var GENERIC_GRACE_MS = 1400; // give specific targets time to render

    // ------------------------------------------------------------------
    // Pure helpers (exposed for unit tests)
    // ------------------------------------------------------------------

    // Where to place the bubble so it never leaves the viewport and does
    // not cover the highlighted element when avoidable.
    function computeBubblePosition(rect, bubbleW, bubbleH, vw, vh, gap) {
        gap = gap == null ? 14 : gap;
        var margin = 12;
        // Accept both DOMRects (bottom/right present) and plain rects.
        var rectBottom = rect.bottom != null ? rect.bottom : rect.top + rect.height;
        var rectRight = rect.right != null ? rect.right : rect.left + rect.width;
        var top;
        var placement;
        var spaceBelow = vh - rectBottom;
        var spaceAbove = rect.top;
        if (spaceBelow >= bubbleH + gap + margin) {
            top = rectBottom + gap;
            placement = 'below';
        } else if (spaceAbove >= bubbleH + gap + margin) {
            top = rect.top - gap - bubbleH;
            placement = 'above';
        } else {
            // neither side fits fully — pick the roomier one and clamp
            if (spaceBelow >= spaceAbove) {
                top = Math.min(rectBottom + gap, vh - bubbleH - margin);
                placement = 'below';
            } else {
                top = Math.max(margin, rect.top - gap - bubbleH);
                placement = 'above';
            }
        }
        top = Math.max(margin, Math.min(top, vh - bubbleH - margin));
        var center = (rect.left + rectRight) / 2;
        var left = center - bubbleW / 2;
        left = Math.max(margin, Math.min(left, vw - bubbleW - margin));
        return { top: top, left: left, placement: placement };
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(value, max));
    }

    // ------------------------------------------------------------------
    // Target resolution
    // ------------------------------------------------------------------

    // A step target may be: a selector string, an array of fallback
    // selectors (first match wins), or a function returning an element.
    function resolveTarget(target) {
        if (!target) return null;
        if (typeof target === 'function') {
            try { return target() || null; } catch (e) { return null; }
        }
        if (Array.isArray(target)) {
            for (var i = 0; i < target.length; i++) {
                var el = resolveTarget(target[i]);
                if (el) return el;
            }
            return null;
        }
        try { return document.querySelector(target); } catch (e) { return null; }
    }

    function currentSection() {
        var m = /^\/academy\/portal\/?([^/?]*)/.exec(window.location.pathname || '');
        return (m && m[1]) || 'dashboard';
    }

    // ------------------------------------------------------------------
    // DOM
    // ------------------------------------------------------------------

    function buildDom() {
        var root = document.createElement('div');
        root.id = 'tourRoot';
        root.className = 'tour-root';

        var overlay = document.createElement('div');
        overlay.className = 'tour-overlay';
        overlay.setAttribute('aria-hidden', 'true');
        root.appendChild(overlay);

        var spot = document.createElement('div');
        spot.className = 'tour-spotlight';
        spot.setAttribute('aria-hidden', 'true');
        root.appendChild(spot);

        var bubble = document.createElement('div');
        bubble.className = 'tour-bubble';
        bubble.setAttribute('role', 'dialog');
        bubble.setAttribute('aria-modal', 'false');
        bubble.setAttribute('aria-label', 'Guided tour');
        bubble.tabIndex = -1;
        bubble.innerHTML =
            '<div class="tour-bubble__progress" aria-live="polite"></div>' +
            '<h4 class="tour-bubble__title"></h4>' +
            '<p class="tour-bubble__text"></p>' +
            '<div class="tour-bubble__controls">' +
            '<button type="button" class="tour-btn tour-btn--ghost" data-tour="back">Back</button>' +
            '<button type="button" class="tour-btn tour-btn--ghost" data-tour="skip">Skip Tour</button>' +
            '<button type="button" class="tour-btn tour-btn--primary" data-tour="next">Next</button>' +
            '</div>';
        root.appendChild(bubble);

        document.body.appendChild(root);

        bubble.querySelector('[data-tour="back"]').addEventListener('click', function () { back(); });
        bubble.querySelector('[data-tour="skip"]').addEventListener('click', function () { exit('skip'); });
        bubble.querySelector('[data-tour="next"]').addEventListener('click', function () { next(); });

        return { root: root, overlay: overlay, spot: spot, bubble: bubble };
    }

    function destroyDom(els) {
        if (els && els.root && els.root.parentNode) {
            els.root.parentNode.removeChild(els.root);
        }
    }

    // ------------------------------------------------------------------
    // Positioning
    // ------------------------------------------------------------------

    function positionFor(step) {
        var els = active.els;
        var target = active.currentTarget;
        if (!target || !target.isConnected) return false;
        var rect = target.getBoundingClientRect();
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        var pad = 6;

        // Spotlight rectangle around the target
        var sTop = clamp(rect.top - pad, 2, vh - 4);
        var sLeft = clamp(rect.left - pad, 2, vw - 4);
        var sW = Math.min(rect.width + pad * 2, vw - sLeft - 2);
        var sH = Math.min(rect.height + pad * 2, vh - sTop - 2);
        els.spot.style.top = sTop + 'px';
        els.spot.style.left = sLeft + 'px';
        els.spot.style.width = Math.max(sW, 8) + 'px';
        els.spot.style.height = Math.max(sH, 8) + 'px';

        // Bubble — measure first at its natural (viewport-capped) size
        els.bubble.style.top = '0px';
        els.bubble.style.left = '0px';
        var bRect = els.bubble.getBoundingClientRect();
        var pos = computeBubblePosition(rect, bRect.width, bRect.height, vw, vh,
            step && step.placement === 'auto' ? 14 : 14);
        els.bubble.style.top = Math.round(pos.top) + 'px';
        els.bubble.style.left = Math.round(pos.left) + 'px';
        els.bubble.setAttribute('data-placement', pos.placement);
        return true;
    }

    var repositionQueued = false;
    function queueReposition() {
        if (!active || repositionQueued) return;
        repositionQueued = true;
        requestAnimationFrame(function () {
            repositionQueued = false;
            if (!active) return;
            // Shell re-render (browser Back, section reload) detached the
            // highlighted node — re-resolve the current step instead of
            // leaving a stale bubble over unrelated content.
            if (active.currentTarget && !active.currentTarget.isConnected) {
                recoverStep();
                return;
            }
            if (active.currentTarget && active.currentTarget.isConnected) {
                positionFor(active.steps[active.index]);
            }
        });
    }

    // ------------------------------------------------------------------
    // Waiting for async targets
    // ------------------------------------------------------------------

    function waitForTarget(step, done) {
        var startedAt = Date.now();
        var navigated = false;
        var seq = active ? active.renderSeq : 0;

        function stillCurrent() {
            return active && active.renderSeq === seq;
        }

        function attempt() {
            if (!stillCurrent()) return; // superseded or tour ended
            // Cross-page navigation: move to the step's section first.
            if (step.section && !navigated && step.section !== currentSection()) {
                navigated = true;
                // `Portal` is a global lexical binding (const in portal.js),
                // not a window property — reference it bare with a guard.
                try {
                    if (typeof Portal !== 'undefined' && Portal && typeof Portal.navigate === 'function') {
                        Portal.navigate(step.section);
                    }
                } catch (e) { /* ignore */ }
            }
            var el = resolveTarget(step.target);
            var elapsed = Date.now() - startedAt;
            // A match on the bare section container usually means the loader
            // is still painting — keep polling briefly for the specific target.
            if (el && el.id === 'portalSection' && elapsed < GENERIC_GRACE_MS) {
                el = null;
            }
            if (el) return done(el, seq);
            if (elapsed >= TARGET_WAIT_MS) {
                return done(null, seq); // caller skips the step gracefully
            }
            setTimeout(attempt, POLL_MS);
        }
        attempt();
    }

    // Re-run the current step's target wait (browser Back / shell re-render
    // can detach the highlighted element while the tour is on screen).
    function recoverStep() {
        if (!active) return;
        active.renderSeq = (active.renderSeq || 0) + 1;
        renderStep();
    }

    // ------------------------------------------------------------------
    // Step lifecycle
    // ------------------------------------------------------------------

    function renderStep() {
        if (!active) return;
        var step = active.steps[active.index];
        var els = active.els;
        active.renderSeq = (active.renderSeq || 0) + 1;
        var seq = active.renderSeq;

        els.bubble.querySelector('.tour-bubble__progress').textContent =
            'Step ' + (active.index + 1) + ' of ' + active.steps.length;
        els.bubble.querySelector('.tour-bubble__title').textContent = step.title || '';
        els.bubble.querySelector('.tour-bubble__text').textContent = step.text || '';

        var backBtn = els.bubble.querySelector('[data-tour="back"]');
        var nextBtn = els.bubble.querySelector('[data-tour="next"]');
        backBtn.disabled = active.index === 0;
        var isLast = active.index === active.steps.length - 1;
        nextBtn.textContent = isLast ? 'Finish Tour' : 'Next';

        els.spot.style.display = 'none';
        els.bubble.style.visibility = 'hidden';

        waitForTarget(step, function (target, cbSeq) {
            if (!active || active.renderSeq !== cbSeq) return; // superseded
            if (!target) {
                // Feature/anchor unavailable for this account — skip gently.
                console.warn('[tour] skipping step "' + step.id + '" — target not found');
                advance(1, { skippedMissing: true });
                return;
            }
            active.currentTarget = target;
            try {
                target.scrollIntoView({ block: 'center', behavior: 'auto' });
            } catch (e) { /* ignore */ }
            // explicit block: the stylesheet default is display:none
            els.spot.style.display = 'block';
            els.bubble.style.visibility = '';
            positionFor(step);
            try { els.bubble.focus({ preventScroll: true }); } catch (e) { els.bubble.focus(); }
            if (active.opts.onStep) {
                try { active.opts.onStep(active.index, step); } catch (e) { /* ignore */ }
            }
        });
    }

    // Move by delta steps, skipping any whose target is unavailable.
    function advance(delta, meta) {
        if (!active) return;
        var next = active.index + delta;
        if (next < 0) next = 0;
        if (next >= active.steps.length) {
            finish();
            return;
        }
        active.index = next;
        if (meta && meta.skippedMissing) {
            // keep going immediately — renderStep will wait/resolve again
        }
        renderStep();
    }

    function next() {
        if (!active) return;
        advance(1);
    }

    function back() {
        if (!active) return;
        advance(-1);
    }

    function finish() {
        if (!active) return;
        var opts = active.opts;
        teardown();
        if (opts.onFinish) { try { opts.onFinish(); } catch (e) { console.error(e); } }
    }

    // reason: 'skip' (explicit Skip Tour) | 'exit' (Escape / teardown)
    function exit(reason) {
        if (!active) return;
        var opts = active.opts;
        var index = active.index;
        teardown();
        if (reason === 'skip' && opts.onSkip) {
            try { opts.onSkip(index); } catch (e) { console.error(e); }
        } else if (opts.onExit) {
            try { opts.onExit(index); } catch (e) { console.error(e); }
        }
    }

    function teardown() {
        if (!active) return;
        var els = active.els;
        window.removeEventListener('resize', queueReposition);
        window.removeEventListener('scroll', queueReposition, true);
        document.removeEventListener('keydown', onKeydown, true);
        destroyDom(els);
        active = null;
    }

    function onKeydown(event) {
        if (!active) return;
        if (event.key === 'ArrowRight') { event.preventDefault(); next(); }
        else if (event.key === 'ArrowLeft') { event.preventDefault(); back(); }
        else if (event.key === 'Escape') { event.preventDefault(); exit('exit'); }
    }

    // ------------------------------------------------------------------
    // Public API
    // ------------------------------------------------------------------

    // opts: { steps, startIndex, onStep, onFinish, onSkip, onExit }
    function start(opts) {
        if (active) teardown();
        if (!opts || !opts.steps || !opts.steps.length) return false;
        active = {
            steps: opts.steps,
            index: clamp(opts.startIndex || 0, 0, opts.steps.length - 1),
            opts: opts,
            els: buildDom(),
            currentTarget: null,
        };
        window.addEventListener('resize', queueReposition);
        window.addEventListener('scroll', queueReposition, true);
        document.addEventListener('keydown', onKeydown, true);
        renderStep();
        return true;
    }

    function stop() {
        if (active) exit('exit');
    }

    function isActive() {
        return !!active;
    }

    function currentIndex() {
        return active ? active.index : -1;
    }

    return {
        start: start,
        stop: stop,
        isActive: isActive,
        currentIndex: currentIndex,
        // exposed for tests
        computeBubblePosition: computeBubblePosition,
        resolveTarget: resolveTarget,
        clamp: clamp,
    };
})();
