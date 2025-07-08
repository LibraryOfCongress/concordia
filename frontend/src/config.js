const DEFAULT_PREFIX_URL = '/static/openseadragon-images/';
const DEFAULT_CONTACT_URL = 'https://ask.loc.gov/crowd';

function getViewerConfig() {
    const viewerDataElement = document.getElementById('viewer-data');

    if (!viewerDataElement) {
        console.warn('viewer-data element not found');
        return {
            prefixUrl: DEFAULT_PREFIX_URL,
            contactUrl: DEFAULT_CONTACT_URL,
        };
    }

    const {prefixUrl, contactUrl} = viewerDataElement.dataset;

    return {
        prefixUrl: prefixUrl || DEFAULT_PREFIX_URL,
        contactUrl: contactUrl || DEFAULT_CONTACT_URL,
    };
}

export const {prefixUrl, contactUrl} = getViewerConfig();
