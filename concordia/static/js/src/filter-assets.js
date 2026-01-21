function filterAssets(doFilter, url) {
    const button = doFilter
        ? document.getElementById('show-all')
        : document.getElementById('filter-assets');

    button.checked = false;
    window.location = url;
}

document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('change', function (event) {
        if (event.target.name === 'radioButtons') {
            filterAssets(
                event.target.dataset.filter === 'true',
                event.target.dataset.url,
            );
        }
    });
});

window.filterAssets = filterAssets;
