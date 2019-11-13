/* eslint-disable no-console */

export function fetchJSON(originalURL) {
    let url = new URL(originalURL, window.location);
    let qs = url.searchParams;
    qs.set('format', 'json');
    let finalURL = `${url.origin}${url.pathname}?${qs}`;

    return fetchURL(finalURL).then(response => response.json());
}

function fetchURL(url, retryLimit = 5) {
    /*

        If everything succeeds we will log the timing and return the response

        If an error occurs it will be retried up to retryLimit times with a
        timed back-off mechanism before finally being rejected.
    */

    return new Promise((resolve, reject) => {
        let retryCount = 0;

        function fetchWrapper() {
            console.time(`Fetch ${url} (retry ${retryCount})`);

            return fetch(url)
                .then(response => {
                    console.timeEnd(`Fetch ${url} (retry ${retryCount})`);
                    resolve(response);
                })
                .catch(error => {
                    retryCount++;
                    if (retryCount < retryLimit) {
                        console.error(`Retrying ${url}: ${error}`);
                        setTimeout(
                            fetchWrapper.bind(this),
                            250 * 2 ** retryCount
                        );
                    } else {
                        console.error(
                            `Failed to fetch ${url} after ${retryCount} retries: ${error}`
                        );
                        reject(error);
                    }
                });
        }
        fetchWrapper();
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
