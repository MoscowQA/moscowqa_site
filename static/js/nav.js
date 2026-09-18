/*
 * Mobile navigation.
 *
 * The burger used to carry an inline onclick that only flipped a class: the
 * button announced nothing about the menu's state and the menu could only be
 * closed by hitting the same button again. Here the state lives in one place,
 * `aria-expanded` follows it, and Esc or a tap outside closes the menu —
 * which is what a keyboard or screen reader user expects of a disclosure.
 */
(function () {
    'use strict';

    var toggle = document.querySelector('[data-nav-toggle]');
    var nav = document.querySelector('[data-nav]');
    if (!toggle || !nav) return;

    function isOpen() {
        return nav.classList.contains('open');
    }

    function setOpen(open) {
        nav.classList.toggle('open', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    toggle.addEventListener('click', function () {
        setOpen(!isOpen());
    });

    document.addEventListener('keydown', function (event) {
        if (!isOpen()) return;
        if (event.key === 'Escape' || event.key === 'Esc') {
            setOpen(false);
            // Focus goes back to the control that opened the menu, so the
            // keyboard user does not end up at the top of the document.
            toggle.focus();
        }
    });

    document.addEventListener('click', function (event) {
        if (!isOpen()) return;
        if (nav.contains(event.target) || toggle.contains(event.target)) return;
        setOpen(false);
    });

    // Following a link navigates away anyway; closing first keeps the menu
    // from staying open behind a same-page anchor.
    nav.addEventListener('click', function (event) {
        if (event.target.closest && event.target.closest('a')) setOpen(false);
    });
})();
