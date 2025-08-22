import $ from 'jquery';
window.$ = window.jQuery = $;
import 'bootstrap';
import 'bootstrap/dist/css/bootstrap.min.css';
import '@scss/base.scss';

/* local scripts */
import '../concordia/static/js/src/asset-reservation.js';
import '../concordia/static/js/src/guide.js';
import '../concordia/static/js/src/homepage-carousel.js';
import '../concordia/static/js/src/ocr.js';
import {setTutorialHeight} from '../concordia/static/js/src/modules/quick-tips.js';
import '../concordia/static/js/src/quick-tips-setup.js';
import '../concordia/static/js/src/viewer.js';
import '../concordia/static/js/src/viewer-split.js';
import '../concordia/static/js/src/contribute.js';

window.setTutorialHeight = setTutorialHeight;
