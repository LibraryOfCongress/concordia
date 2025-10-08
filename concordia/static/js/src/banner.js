import $ from 'jquery';

var storage = window.localStorage;
var storageAvailable;
try {
    const x = '__storage_test__';
    storage.setItem(x, x);
    storage.removeItem(x);
    storageAvailable = true;
} catch {
    storageAvailable = false;
}
if (storageAvailable) {
    for (var key in storage) {
        if (key.startsWith('banner-') && $('#' + key).hasClass('alert')) {
            $('#' + key).attr('hidden', true);
        }
    }
}
$('#no-interface-banner').click(function (event) {
    var banner = event.target.parentElement.parentElement;
    if (banner.hasAttribute('id')) {
        storage.setItem(banner.id, true);
        var element = document.getElementById(banner.id);
        element.classList.remove('d-flex');
        $(element).attr('hidden', 'hidden');
    }
});
