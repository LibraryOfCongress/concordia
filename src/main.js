import $ from 'jquery';
window.$ = window.jQuery = $;
import 'bootstrap';
import 'bootstrap/dist/css/bootstrap.min.css';

/* local scripts */
import '../concordia/static/js/src/about-accordions.js';
import '../concordia/static/js/src/asset-reservation.js';
import '../concordia/static/js/src/banner.js';
import '../concordia/static/js/src/contribute.js';
import '../concordia/static/js/src/filter-assets.js';
import '../concordia/static/js/src/guide.js';
import '../concordia/static/js/src/homepage-carousel.js';
import '../concordia/static/js/src/ocr.js';
import {setTutorialHeight} from '../concordia/static/js/src/modules/quick-tips.js';
import '../concordia/static/js/src/quick-tips-setup.js';
import '../concordia/static/js/src/viewer.js';
import '../concordia/static/js/src/viewer-split.js';

/*- Third-party */
import OpenSeadragon from 'openseadragon';
import 'openseadragon-filtering';

OpenSeadragon.setString(
    'prefixUrl',
    "{% static 'openseadragon/build/openseadragon/images/' %}",
);

if (window.OpenSeadragon?.Filters && !OpenSeadragon.Filters) {
    OpenSeadragon.Filters = window.OpenSeadragon.Filters;
}

if (
    window.OpenSeadragon?.Viewer?.prototype.setFilterOptions &&
    !OpenSeadragon.Viewer.prototype.setFilterOptions
) {
    OpenSeadragon.Viewer.prototype.setFilterOptions =
        window.OpenSeadragon.Viewer.prototype.setFilterOptions;
}

if (setTutorialHeight) {
    window.setTutorialHeight = setTutorialHeight;
}
