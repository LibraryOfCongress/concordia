/* global $ */

import {Carousel} from 'bootstrap';

// initialization
var carouselElement = document.getElementById('homepage-carousel');
var carousel = new Carousel(carouselElement, {
    interval: 5000,
    pause: false,
    ride: 'carousel',
});

// play/pause

let playPauseButton = document.getElementById('play-pause-button');
playPauseButton.addEventListener('click', function () {
    if ($(this).hasClass('paused')) {
        carousel.cycle();
    } else {
        carousel.pause();
    }
    $(this).children('.fa').toggleClass('fa-pause').toggleClass('fa-play');
    $(this).toggleClass('paused');
});
carouselElement.addEventListener('mouseover', function () {
    carousel.pause();
});
carouselElement.addEventListener('mouseleave', function () {
    if (!playPauseButton.classList.contains('paused')) {
        carousel.cycle();
    }
});
