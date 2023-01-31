/* global jQuery */

function getPages() {
    jQuery.ajax({
        type: 'GET',
        url: '/account/get_pages/',
        dataType: 'json',
        success: function (data) {
            var tableBody = document.createElement('tbody');
            tableBody.innerHTML = data.content;
            document.getElementById('recent-pages').append(tableBody);
        },
    });
}

jQuery('#pages-tab').on('click', function () {
    getPages();
});
