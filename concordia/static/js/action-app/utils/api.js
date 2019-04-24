/* eslint-disable no-console */

export function fetchJSON(originalURL) {
    let url = new URL(originalURL, window.location);
    let qs = url.searchParams;
    qs.set('format', 'json');
    let finalURL = `${url.origin}${url.pathname}?${qs}`;

    console.time(`Fetch ${url}`);

    return fetch(finalURL).then(response => {
        console.timeEnd(`Fetch ${url}`);
        return response.json();
    });
}

export function getCachedData(container, objectReference, key) {
    /*
        Assumes a passed object with .id potentially matching a key in
        this.items and .url being the source for the data if we don't
        already have a copy

        The key parameter will be used to extract only a single key from the
        returned data object. This is a code-smell indicator that we may
        want to review our API return format to have the parent/children
        elements use the same name everywhere.
    */
    let id = objectReference.id.toString();

    if (container.has(id)) {
        return Promise.resolve(container.get(id));
    } else {
        return fetchJSON(objectReference.url).then(data => {
            let object = key ? data[key] : data;
            container.set(id, object);
            return object;
        });
    }
}
