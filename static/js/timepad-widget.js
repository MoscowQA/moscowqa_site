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

    /* --- Фон под попапом ----------------------------------------------
     *
     * Форму регистрации Timepad открывает поверх страницы, но саму страницу
     * при этом не блокирует: колесо мыши прокручивает фон, а попап остаётся
     * там, где его открыли, и уезжает за край экрана.
     *
     * Ни события «попап открылся», ни своих классов Timepad наружу не отдаёт
     * (в bindEvents только события отрисовки — dev.timepad.ru/widget/
     * bind-to-event), так что опираемся на то, что видно из DOM: своих
     * iframe у сайта нет, значит крупный видимый iframe вне блоков
     * встроенной формы и афиши — это и есть попап.
     */

    var LOCK_CLASS = 'timepad-popup-open';
    // Служебные iframe загрузчика — нулевого размера, форма заметно больше.
    var POPUP_MIN_SIZE = 200;
    // Попап могут не удалить, а спрятать; об этом MutationObserver
    // рассказывает не всегда, поэтому пока замок стоит — переспрашиваем.
    var RECHECK_MS = 500;
    // Отступ сверху, когда подводим страницу к верху формы.
    var REVEAL_GAP = 16;

    var locked = false;
    var recheckTimer = null;
    var lastHeight = 0;

    function popupFrame() {
        var frames = document.querySelectorAll('iframe');
        for (var i = 0; i < frames.length; i++) {
            var holder = frames[i].closest('[data-timepad-widget]');
            // Встроенная форма и афиша живут в своих блоках прямо на
            // странице — это не попап, и блокировать из-за них нечего.
            if (holder && !holder.classList.contains('timepad-widget--popup')) continue;
            var rect = frames[i].getBoundingClientRect();
            if (rect.width >= POPUP_MIN_SIZE && rect.height >= POPUP_MIN_SIZE) {
                return frames[i];
            }
        }
        return null;
    }

    /* Привязан ли попап к окну: тогда прокрутка страницы на его видимость
       не влияет — ни в плюс, ни в минус. Достаточно найти position: fixed
       на любом родителе: он прижимает к окну всё поддерево. */
    function pinnedToWindow(frame) {
        for (var node = frame; node && node !== document.body; node = node.parentElement) {
            if (window.getComputedStyle(node).position === 'fixed') return true;
        }
        return false;
    }

    /* Форма выросла (нажали «Продолжить»), и её верх уехал за край окна.
       Подводим страницу к нему — сам Timepad этого не делает, и посетитель
       остаётся смотреть на середину нового шага. */
    function revealPopup(frame) {
        var top = frame.getBoundingClientRect().top;
        if (top >= 0) return;
        window.scrollTo(0, Math.max(0, window.pageYOffset + top - REVEAL_GAP));
    }

    function lockBackground() {
        if (locked) return;
        locked = true;
        // Полоса прокрутки исчезает вместе со скроллом — компенсируем, иначе
        // страница под попапом дёрнется вправо на её ширину.
        var gap = window.innerWidth - document.documentElement.clientWidth;
        if (gap > 0) document.body.style.paddingRight = gap + 'px';
        document.documentElement.classList.add(LOCK_CLASS);
        recheckTimer = setInterval(sync, RECHECK_MS);
    }

    function unlockBackground() {
        if (!locked) return;
        locked = false;
        clearInterval(recheckTimer);
        recheckTimer = null;
        document.documentElement.classList.remove(LOCK_CLASS);
        document.body.style.paddingRight = '';
    }

    function sync() {
        var frame = popupFrame();
        if (!frame) {
            unlockBackground();
            lastHeight = 0;
            return;
        }

        var height = frame.getBoundingClientRect().height;
        // Высота меняется на смене шага формы — это и есть «нажали
        // Продолжить». Просто прокрутку посетителя так не спутать.
        var stepChanged = height !== lastHeight;
        lastHeight = height;

        // Попап помещается в окно — фон можно останавливать. Прижатый к окну
        // попап от прокрутки не зависит вовсе, его тоже можно.
        if (height <= document.documentElement.clientHeight || pinnedToWindow(frame)) {
            lockBackground();
            return;
        }

        // Попап выше окна и стоит в потоке страницы: замок сделал бы низ
        // формы недосягаемым, а это уже не косметика, а несделанная
        // регистрация. Фон отпускаем, но на смене шага подводим страницу
        // к верху формы, чтобы попап не оставался за краем экрана.
        unlockBackground();
        if (stepChanged) revealPopup(frame);
    }

    function watchPopups() {
        if (typeof MutationObserver !== 'function') return;

        var scheduled = false;
        function schedule() {
            if (scheduled) return;
            scheduled = true;
            // Попап появляется пачкой изменений — пересчитываем раз за кадр.
            var run = function () { scheduled = false; sync(); };
            if (typeof requestAnimationFrame === 'function') requestAnimationFrame(run);
            else setTimeout(run, 16);
        }

        new MutationObserver(schedule).observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ['style', 'class', 'hidden']
        });
        // Окно могли уменьшить так, что попап перестал помещаться.
        window.addEventListener('resize', schedule);
    }

    function init() {
        apply();
        watchPopups();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
