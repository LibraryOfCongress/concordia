import $ from 'jquery';

export function getPages(queryString = window.location.search) {
    $.ajax({
        type: 'GET',
        url: '/account/get_pages/' + queryString,
        dataType: 'json',
        success: function (data) {
            var recentPages = document.createElement('div');
            recentPages.className = 'col-md';
            recentPages.innerHTML = data.content;
            $('#recent-pages').html(recentPages);
        },
        error: function () {
            $('#recent-pages').html('<p>Failed to load pages.</p>');
        },
    });
}

$('#recent-tab').on('click', () => getPages(window.location.search));

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
