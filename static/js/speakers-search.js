/*
 * Frontend search over the speakers list (/speakers/).
 *
 * Every card carries `data-speaker-search` — a haystack built in build.py
 * (`speaker_search_text`) out of the speaker's name, company, latin slug and
 * the titles of their MoscowQA and external talks, already lowercased with
 * "ё" folded to "е". The query is normalized the same way and split into
 * words; a card stays visible while every word occurs somewhere in its
 * haystack, so "кленов vk" and "vk кленов" match alike.
 *
 * The form itself is hidden until this script runs (see `.speakers-search`
 * in styles.css), so without JS the full list is still rendered as before.
 * The current query is mirrored into the `?q=` parameter to keep search
 * results linkable.
 */
(function () {
    'use strict';

    var form = document.querySelector('[data-speakers-search]');
    var input = document.querySelector('[data-speakers-search-input]');
    var clearBtn = document.querySelector('[data-speakers-search-clear]');
    var counter = document.querySelector('[data-speakers-count]');
    var empty = document.querySelector('[data-speakers-empty]');

    if (!form || !input) return;

    var cards = document.querySelectorAll('[data-speaker-card]');
    var total = cards.length;
    var defaultCount = counter ? counter.textContent : '';

    function normalize(text) {
        return String(text).toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();
    }

    function plural(n, one, few, many) {
        var mod100 = n % 100;
        if (mod100 >= 11 && mod100 <= 14) return many;
        var mod10 = n % 10;
        if (mod10 === 1) return one;
        if (mod10 >= 2 && mod10 <= 4) return few;
        return many;
    }

    function matches(haystack, words) {
        for (var i = 0; i < words.length; i++) {
            if (haystack.indexOf(words[i]) === -1) return false;
        }
        return true;
    }

    function filter(query) {
        var normalized = normalize(query);
        var words = normalized ? normalized.split(' ') : [];
        var shown = 0;

        for (var i = 0; i < cards.length; i++) {
            var card = cards[i];
            var visible = !words.length ||
                matches(card.getAttribute('data-speaker-search') || '', words);
            card.hidden = !visible;
            if (visible) shown++;
        }

        if (counter) {
            counter.textContent = words.length
                ? shown + ' ' + plural(shown, 'спикер', 'спикера', 'спикеров') +
                  ' из ' + total
                : defaultCount;
        }
        if (empty) empty.hidden = shown !== 0;
        if (clearBtn) clearBtn.hidden = !query;
    }

    function syncUrl(query) {
        if (!window.history || !window.history.replaceState) return;
        try {
            var url = new URL(window.location.href);
            if (query) {
                url.searchParams.set('q', query);
            } else {
                url.searchParams.delete('q');
            }
            window.history.replaceState(null, '', url.toString());
        } catch (e) {
            /* Non-standard URLs (file://, old browsers) simply keep no state. */
        }
    }

    function onQueryChange() {
        filter(input.value);
        syncUrl(input.value.trim());
    }

    input.addEventListener('input', onQueryChange);
    input.addEventListener('search', onQueryChange);
    input.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' || event.key === 'Esc') {
            input.value = '';
            onQueryChange();
        }
    });

    if (clearBtn) {
        clearBtn.addEventListener('click', function () {
            input.value = '';
            onQueryChange();
            input.focus();
        });
    }

    // A shared link like /speakers/?q=playwright opens already filtered.
    var initial = '';
    try {
        initial = new URL(window.location.href).searchParams.get('q') || '';
    } catch (e) {
        initial = '';
    }
    if (initial) input.value = initial;
    filter(input.value);
})();
