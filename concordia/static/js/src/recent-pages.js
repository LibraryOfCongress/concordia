import $ from 'jquery';

let currentRequest;

export function getPages(queryString = window.location.search) {
    if (currentRequest) {
        // Cancel previous before starting a new one
        currentRequest.abort();
    }
    currentRequest = $.ajax({
        type: 'GET',
        url: '/account/get_pages' + queryString,
        dataType: 'json',
        success: function (data) {
            var recentPages = document.createElement('div');
            recentPages.className = 'col-md';
            recentPages.innerHTML = data.content; // render data into the DOM
            $('#recent-pages').html(recentPages);
        },
        error: function () {
            $('#recent-pages').html('<p>Failed to load pages.</p>');
        },
        complete: function () {
            // clear the reference
            currentRequest = undefined;
        },
    });
}

if (!window._recentPagesHandlersInitialized) {
    window._recentPagesHandlersInitialized = true;

    $(document).on('click', '#recent-tab', () =>
        getPages(window.location.search),
    );

    $(document).on('submit', '.date-filter', function (event) {
        event.preventDefault();

        const parameters = new URLSearchParams(new FormData(this));

        getPages('?' + parameters.toString());
    });

    $(document).on('click', '#current-filters a', function (event) {
        event.preventDefault();

        const href = $(this).attr('href'); // e.g. "?tab=recent"

        getPages(href);
    });

    $(document).on('click', '.dropdown-menu a.filter-link', function (event) {
        event.preventDefault();

        const href = $(this).attr('href') || '';
        const qsFromLink = href.startsWith('?') ? href.slice(1) : href;
        const linkParameters = new URLSearchParams(qsFromLink);

        const currentParameters = new URLSearchParams(window.location.search);

        for (const [key, value] of linkParameters.entries()) {
            if (key.startsWith('delete:')) {
                currentParameters.delete(key.replace('delete:', ''));
            } else {
                currentParameters.set(key, value);
            }
        }
        finalizePageUpdate(currentParameters);
    });

    $(document).on(
        'submit',
        'nav[aria-label="Page Jump"] form',
        function (event) {
            event.preventDefault();

            const pageNumber = $(this).find('select[name="page"]').val();

            const currentParameters = new URLSearchParams(
                window.location.search,
            );

            currentParameters.set('page', pageNumber);

            // Preserve other filters
            $(this)
                .find('input[type="hidden"]')
                .each(function () {
                    currentParameters.set(this.name, this.value);
                });
            finalizePageUpdate(currentParameters);
        },
    );

    $(document).ready(function () {
        if (window.location.pathname.includes('/account/profile')) {
            getPages(window.location.search);
        }
    });
}

function finalizePageUpdate(currentParameters) {
    if (!currentParameters.has('tab')) currentParameters.set('tab', 'recent');

    const newQuery = '?' + currentParameters.toString();
    // Call AJAX loader
    getPages(newQuery);
    // Update the URL in the address bar without reloading
    history.replaceState(undefined, '', newQuery + window.location.hash);
}
