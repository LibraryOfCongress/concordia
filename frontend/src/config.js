/**
 * Viewer configuration helpers for the React transcription UI.
 *
 * Reads optional values from a DOM element with id "viewer-data" and exposes
 * resolved settings as named exports. Falls back to safe defaults when the
 * element is missing or its dataset values are empty.
 *
 * Expected dataset attributes on #viewer-data:
 *   - data-prefix-url: string URL prefix for OpenSeadragon control images
 *   - data-contact-url: string URL for the "contact us" link
 *
 * No runtime side effects beyond a DOM lookup and a console warning when the
 * element is not present.
 */

/** Default OpenSeadragon image prefix if none is provided via #viewer-data. */
const DEFAULT_PREFIX_URL = '/static/openseadragon-images/';

/** Default contact URL if none is provided via #viewer-data. */
const DEFAULT_CONTACT_URL = 'https://ask.loc.gov/crowd';

/**
 * Shape of the viewer configuration object.
 *
 * @typedef {Object} ViewerConfig
 * @property {string} prefixUrl
 *   Base URL where OpenSeadragon looks for its control images.
 * @property {string} contactUrl
 *   Absolute URL used by "contact us" or help links.
 */

/**
 * Resolve viewer configuration from the DOM with fallbacks.
 *
 * Looks for an element with id "viewer-data". If found, reads the
 * `data-prefix-url` and `data-contact-url` attributes. Empty strings are
 * treated as missing and replaced by defaults.
 *
 * @returns {ViewerConfig}
 */
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

/**
 * Resolved configuration values for consumers.
 *
 * `prefixUrl` is used by OpenSeadragon for control image paths.
 * `contactUrl` is used by UI links that route users to support.
 *
 * @type {string}
 * @name prefixUrl
 *
 * @type {string}
 * @name contactUrl
 */
export const {prefixUrl, contactUrl} = getViewerConfig();
