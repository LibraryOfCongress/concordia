/* global */

import $ from 'jquery';
import {Carousel} from 'bootstrap';
import {trackUIInteraction} from './base.js';

function openOffcanvas() {
    let guide = document.getElementById('guide-sidebar');
    if (guide.classList.contains('offscreen')) {
        guide.classList.remove('offscreen');
        guide.style.borderWidth = '0 0 thick thick';
        guide.style.borderStyle = 'solid';
        guide.style.borderColor = '#0076ad';
        document.addEventListener('keydown', function (event) {
            if (event.key == 'Escape') {
                closeOffcanvas();
            }
        });
        document.getElementById('open-guide').style.background = '#002347';
    } else {
        closeOffcanvas();
    }
}

function closeOffcanvas() {
    let guide = document.getElementById('guide-sidebar');
    guide.classList.add('offscreen');
    guide.style.border = 'none';

    let openGuide = document.getElementById('open-guide');
    if (openGuide) {
        openGuide.style.background = '#0076AD';
    }
}

document.getElementById('open-guide')?.addEventListener('click', openOffcanvas);

document
    .getElementById('close-guide')
    ?.addEventListener('click', closeOffcanvas);

document.addEventListener('DOMContentLoaded', () => {
    const guideCarouselElement = document.getElementById('guide-carousel');
    if (guideCarouselElement) {
        new Carousel(guideCarouselElement, {
            interval: false,
            wrap: false,
        });

        guideCarouselElement.addEventListener('slide.bs.carousel', (event) => {
            const barsCol = document.getElementById('guide-bars-col');
            if (!barsCol) return;

            if (event.to === 0) {
                barsCol.classList.add('d-none');
            } else {
                barsCol.classList.remove('d-none');
            }
        });
    }
});

$('#previous-card').hide();

$('#card-carousel').on('slid.bs.carousel', function () {
    if ($('#card-carousel .carousel-item:first').hasClass('active')) {
        $('#previous-card').hide();
        $('#next-card').show();
    } else if ($('#card-carousel .carousel-item:last').hasClass('active')) {
        $('#previous-card').show();
        $('#next-card').hide();
    } else {
        $('#previous-card').show();
        $('#next-card').show();
    }
});

function trackHowToInteraction(element, label) {
    trackUIInteraction(element, 'How To Guide', 'click', label);
}

if ($('#open-guide').length > 0) {
    $('#open-guide').on('click', function () {
        trackHowToInteraction($(this), 'Open');
    });
}
if ($('#close-guide').length > 0) {
    $('#close-guide').on('click', function () {
        trackHowToInteraction($(this), 'Close');
    });
}
if ($('#previous-guide').length > 0) {
    $('#previous-guide').on('click', function () {
        trackHowToInteraction($(this), 'Back');
    });
}
if ($('#next-guide').length > 0) {
    $('#next-guide').on('click', function () {
        trackHowToInteraction($(this), 'Next');
    });
}
if ($('#guide-bars').length > 0) {
    $('#guide-bars').on('click', function () {
        trackHowToInteraction($(this), 'Hamburger Menu');
    });
}
$('#guide-sidebar .nav-link').on('click', function () {
    let label = $(this).text().trim();
    trackHowToInteraction($(this), label);
});

export {openOffcanvas, closeOffcanvas};
