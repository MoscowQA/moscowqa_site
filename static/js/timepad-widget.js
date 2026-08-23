/*
 * Lazy embedding of Timepad widgets.
 *
 * Templates (see templates/partials/timepad.html) render only a placeholder:
 *
 *   <section data-timepad-widget="event_register"
 *            data-timepad-loader="https://timepad.ru/js/tpwf/loader/min/loader.js"
 *            data-timepad-customization="123"      (optional)
 *            data-event-date="2026-09-05"          (optional)
 *            data-timepad-eager="1"                (optional)
 *            data-timepad-config='{"event":{"id":"4046132"}, ...}'>
 *     <div class="timepad-widget__mount"></div>
 *     <p class="timepad-widget__fallback">...</p>
 *   </section>
 *
 * This script builds the embed code documented at
 * https://dev.timepad.ru/widget/how-widget-works/ — a <script> tag pointing at
 * Timepad's loader, carrying the widget type in `data-timepad-widget-v2` and
 * the settings as the body of an IIFE — and appends it to the mount node.
 * Timepad's loader then renders the widget in place of that tag.
 *
 * Two things are deliberately kept out of the generated HTML:
 *   - Widgets for events that are already over are never mounted, so archive
 *     pages don't pull in a third-party script.
 *   - Widgets are mounted when they scroll into view, so the loader never
 *     competes with the page's own resources.
 *
 * Until the widget renders, the fallback link stays visible — that is also
 * what visitors without JS get.
 */
(function () {
    'use strict';

    var MOUNTED_ATTR = 'data-timepad-mounted';
    // How long to keep watching the mount node before giving up on the
    // widget and leaving the fallback link in place.
    var RENDER_TIMEOUT_MS = 20000;

    function isPast(dateStr) {
        if (!dateStr) return false;
        var eventDate = new Date(dateStr + 'T00:00:00');
        if (isNaN(eventDate.getTime())) return false;
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        return eventDate < today;
    }

    /* Hide the fallback text as soon as the loader puts something in place. */
    function watchForRender(container, mount) {
        var fallback = container.querySelector('.timepad-widget__fallback');
        if (!fallback) return;

        function rendered() {
            // The embed <script> itself doesn't count as rendered output.
            for (var i = 0; i < mount.children.length; i++) {
                if (mount.children[i].tagName !== 'SCRIPT') return true;
            }
            return false;
        }

        function settle() {
            if (!rendered()) return false;
            container.classList.add('timepad-widget--ready');
            fallback.hidden = true;
            return true;
        }

        if (settle() || typeof MutationObserver !== 'function') return;

        var observer = new MutationObserver(function () {
            if (settle()) observer.disconnect();
        });
        observer.observe(mount, { childList: true, subtree: true });
        setTimeout(function () { observer.disconnect(); }, RENDER_TIMEOUT_MS);
    }

    function mount(container) {
        if (container.hasAttribute(MOUNTED_ATTR)) return;

        var loader = container.getAttribute('data-timepad-loader');
        var widget = container.getAttribute('data-timepad-widget');
        var config = container.getAttribute('data-timepad-config');
        var mountNode = container.querySelector('.timepad-widget__mount');
        if (!loader || !widget || !config || !mountNode) return;

        try {
            JSON.parse(config);
        } catch (e) {
            // A malformed config would make the loader fail silently; better
            // to leave the fallback link alone.
            return;
        }

        container.setAttribute(MOUNTED_ATTR, '');

        var script = document.createElement('script');
        script.type = 'text/javascript';
        script.async = true;
        script.setAttribute('charset', 'UTF-8');
        script.setAttribute('data-timepad-widget-v2', widget);
        var customization = container.getAttribute('data-timepad-customization');
        if (customization) {
            script.setAttribute('data-timepad-customized', customization);
        }
        // Timepad reads the settings from the body of the embed tag.
        script.text = '(function(){return ' + config + ';})();';
        script.src = loader;

        watchForRender(container, mountNode);
        mountNode.appendChild(script);
    }

    function apply() {
        var containers = document.querySelectorAll('[data-timepad-widget]');
        var lazy = [];

        for (var i = 0; i < containers.length; i++) {
            var container = containers[i];
            if (isPast(container.getAttribute('data-event-date'))) {
                container.hidden = true;
                continue;
            }
            // Popup widgets have no visible placeholder to scroll to, so they
            // are mounted right away.
            if (container.hasAttribute('data-timepad-eager')) {
                mount(container);
            } else {
                lazy.push(container);
            }
        }

        if (!lazy.length) return;

        if (typeof IntersectionObserver !== 'function') {
            for (var j = 0; j < lazy.length; j++) mount(lazy[j]);
            return;
        }

        var observer = new IntersectionObserver(function (entries) {
            for (var k = 0; k < entries.length; k++) {
                if (!entries[k].isIntersecting) continue;
                observer.unobserve(entries[k].target);
                mount(entries[k].target);
            }
        }, { rootMargin: '300px 0px' });

        for (var m = 0; m < lazy.length; m++) observer.observe(lazy[m]);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', apply);
    } else {
        apply();
    }
})();
