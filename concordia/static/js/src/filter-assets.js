export function filterAssets(filterAssets, url) {
    var button;
    if (filterAssets) {
        button = document.getElementById('show-all');
    } else {
        button = document.getElementById('filter-assets');
    }
    button.checked = false;
    window.location = url;
}
