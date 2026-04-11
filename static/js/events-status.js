/*
 * Frontend-side determination of "upcoming" vs "completed" events.
 *
 * Templates render every event as `.is-upcoming` by default and tag
 * upcoming-only / completed-only bits with `.js-upcoming-only` /
 * `.js-completed-only`. This script walks every element carrying a
 * `data-event-date="YYYY-MM-DD"` attribute, compares it to the visitor's
 * local "today", and flips the parent class when the event is in the past.
 *
 * On the index page, it also partitions cards from `[data-events-source]`
 * into `[data-events-upcoming]` and `[data-events-past]` containers.
 */
(function () {
    'use strict';

    function isCompleted(dateStr) {
        if (!dateStr) return false;
        var eventDate = new Date(dateStr + 'T00:00:00');
        if (isNaN(eventDate.getTime())) return false;
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        return eventDate < today;
    }

    function apply() {
        var nodes = document.querySelectorAll('[data-event-date]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (isCompleted(el.getAttribute('data-event-date'))) {
                el.classList.remove('is-upcoming');
                el.classList.add('is-completed');
            }
        }

        var source = document.querySelector('[data-events-source]');
        var upcomingList = document.querySelector('[data-events-upcoming]');
        var pastList = document.querySelector('[data-events-past]');

        if (source && upcomingList && pastList) {
            var cards = source.querySelectorAll('[data-event-date]');
            for (var j = 0; j < cards.length; j++) {
                var card = cards[j];
                if (card.classList.contains('is-completed')) {
                    pastList.appendChild(card);
                } else {
                    upcomingList.appendChild(card);
                }
            }

            var upcomingSection = upcomingList.closest('section');
            var pastSection = pastList.closest('section');
            if (upcomingSection) {
                upcomingSection.hidden = upcomingList.children.length === 0;
            }
            if (pastSection) {
                pastSection.hidden = pastList.children.length === 0;
            }
            source.parentNode.removeChild(source);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', apply);
    } else {
        apply();
    }
})();
