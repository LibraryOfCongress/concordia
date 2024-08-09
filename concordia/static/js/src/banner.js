/* global $ */

if (typeof Storage !== 'undefined') {
    if (!(window.screen.width < 1024 || window.screen.height < 768)) {
        for (var key in localStorage) {
            if (key.startsWith('banner-')) {
                if ($('#' + key).hasClass('alert')) {
                    $('#' + key).attr('hidden', true);
                }
            }
        }
    }
}

$('#no-interface-banner').click(function (event) {
    localStorage.setItem(event.target.parentElement.id, true);
    $('#' + event.target.parentElement.id).attr('hidden', true);
});
