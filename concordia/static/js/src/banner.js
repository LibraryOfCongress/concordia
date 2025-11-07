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
        if (key.startsWith('banner-')) {
            const banner = document.getElementById(key);
            if (banner && banner.classList.contains('alert')) {
                banner.setAttribute('hidden', 'hidden');
            }
        }
    }
}
const noInterfaceBanner = document.getElementById('no-interface-banner');
if (noInterfaceBanner) {
    noInterfaceBanner.addEventListener('click', (event) => {
        var banner = event.target.parentElement.parentElement;
        if (banner.hasAttribute('id')) {
            storage.setItem(banner.id, 'true');
            banner.classList.remove('d-flex');
            banner.setAttribute('hidden', 'hidden');
        }
    });
}
