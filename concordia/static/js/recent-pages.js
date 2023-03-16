/* global jQuery */

function getPages(queryString = window.location.search) {
    jQuery.ajax({
        type: 'GET',
        url: '/account/get_pages/' + queryString,
        dataType: 'json',
        success: function (data) {
            var recentPages = document.createElement('div');
            recentPages.setAttribute('class', 'col-md');
            recentPages.innerHTML = data.content;
            jQuery('#recent-pages').html(recentPages);
        },
    });
}

jQuery('#recent-tab').on('click', function () {
    getPages();
});
