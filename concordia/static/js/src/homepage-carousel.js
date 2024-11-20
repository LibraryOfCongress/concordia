/* global $ */

import {Carousel} from '/static/bootstrap/dist/js/bootstrap.bundle.min.js';

// play/pause
function cycleCarousel(carouselElement) {
    var carouselInstance = Carousel.getInstance(carouselElement);

    carouselInstance.cycle();
    carouselElement.dataset.bsInterval = 5000;
    carouselElement.dataset.bsPause = 'hover';
    carouselElement.dataset.bsRide = 'carousel';
    $(this).children('.fa').removeClass('fa-play').addClass('fa-pause');
    $(this).removeClass('paused');
}

function pauseCarousel(carouselElement) {
    var carouselInstance = Carousel.getInstance(carouselElement);

    carouselInstance.pause();
    carouselElement.dataset.bsInterval = false;
    carouselElement.dataset.bsPause = false;
    carouselElement.dataset.bsRide = false;
    $(this).children('.fa').removeClass('fa-pause').addClass('fa-play');
    $(this).addClass('paused');
}

$('.play-pause-button').click(function () {
    var carouselElement = document.getElementById('homepage-carousel');

    if ($(this).hasClass('paused')) {
        cycleCarousel(carouselElement);
    } else {
        pauseCarousel(carouselElement);
    }
});
