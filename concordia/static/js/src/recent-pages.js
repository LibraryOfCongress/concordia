import $ from 'jquery';

function getPages(queryString = window.location.search) {
    $.ajax({
        type: 'GET',
        url: '/account/get_pages/' + queryString,
        dataType: 'json',
        success: function (data) {
            var recentPages = document.createElement('div');
            recentPages.setAttribute('class', 'col-md');
            recentPages.innerHTML = data.content;
            $('#recent-pages').html(recentPages);
        },
    });
}

$('#recent-tab').on('click', function () {
    getPages();
});
