/* global jQuery */

function getPages() {
    jQuery.ajax({
        type: 'GET',
        url: '/account/get_pages/' + window.location.search,
        dataType: 'json',
        success: function (data) {
            var recentPages = document.createElement('div');
            recentPages.setAttribute('class', 'col-md');
            recentPages.innerHTML = data.content;
            document.getElementById('recent-pages').append(recentPages);
        },
    });
}

jQuery('#recent-tab').on('click', function () {
    getPages();
});
