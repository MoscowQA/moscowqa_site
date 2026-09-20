/*
 * Поправка статуса событий на дату посетителя.
 *
 * Раскладывает события по «предстоящим» и «прошедшим» сборка (build.py,
 * `split_events`), а сайт пересобирается каждую ночь. Этот скрипт закрывает
 * то, что остаётся: часы между ночной сборкой и визитом, и посетителей в
 * других часовых поясах, у которых «сегодня» наступает раньше.
 *
 * Что он делает:
 *   - сверяет `data-event-date` с локальным «сегодня» и ставит элементу
 *     `.is-completed` или `.is-upcoming` (по ним CSS прячет `.js-upcoming-only`
 *     и `.js-completed-only` — кнопку регистрации, подпись блока и прочее);
 *   - переносит карточку между `[data-events-upcoming]` и `[data-events-past]`,
 *     если сборка успела устареть;
 *   - прячет пустую секцию.
 *
 * На свежей сборке переносить обычно нечего, и страница не дёргается.
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

    function applyStatus(el, completed) {
        el.classList.toggle('is-completed', completed);
        el.classList.toggle('is-upcoming', !completed);
    }

    // Карточка переезжает в начало списка: предстоящие идут ближайшим вперёд,
    // прошедшие — свежим вперёд, и в обоих случаях её место именно там.
    function move(cards, target) {
        for (var i = 0; i < cards.length; i++) {
            target.insertBefore(cards[i], target.firstChild);
        }
    }

    function staleCards(container, wantCompleted) {
        var found = [];
        if (!container) return found;
        var cards = container.querySelectorAll('[data-event-date]');
        for (var i = 0; i < cards.length; i++) {
            if (isCompleted(cards[i].getAttribute('data-event-date')) === wantCompleted) {
                found.push(cards[i]);
            }
        }
        return found;
    }

    function hideIfEmpty(container) {
        if (!container) return;
        var section = container.closest('section');
        if (section) section.hidden = container.children.length === 0;
    }

    function apply() {
        var nodes = document.querySelectorAll('[data-event-date]');
        for (var i = 0; i < nodes.length; i++) {
            applyStatus(nodes[i], isCompleted(nodes[i].getAttribute('data-event-date')));
        }

        var upcoming = document.querySelector('[data-events-upcoming]');
        var past = document.querySelector('[data-events-past]');
        if (!upcoming || !past) return;

        move(staleCards(upcoming, true), past);
        // Обратный случай: посетитель в часовом поясе западнее сборки, у него
        // событие ещё не наступило.
        move(staleCards(past, false), upcoming);

        hideIfEmpty(upcoming);
        hideIfEmpty(past);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', apply);
    } else {
        apply();
    }
})();
