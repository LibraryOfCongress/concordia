/* global $ */

import {Carousel} from '/static/bootstrap/dist/js/bootstrap.esm.js';

// initialization
var carouselElement = document.getElementById('homepage-carousel');
var carousel = new Carousel(carouselElement, {
    interval: 1000,
    pause: false,
    // pause: 'hover',
    ride: 'carousel',
});

// play/pause

let playPauseButton = document.getElementById('play-pause-button');
playPauseButton.addEventListener('click', function () {
    if ($(this).hasClass('paused')) {
        carousel.cycle();
    } else {
        carousel.pause();
        // console.log(carousel);
    }
    $(this).children('.fa').toggleClass('fa-pause').toggleClass('fa-play');
    $(this).toggleClass('paused');
});
carouselElement.addEventListener('mouseenter', function () {
    carousel.pause();
});
carouselElement.addEventListener('mouseover', function () {
    carousel.pause();
});
carouselElement.addEventListener('mouseleave', function () {
    if (!playPauseButton.classList.contains('paused')) {
        carousel.cycle();
    }
});
carouselElement.addEventListener('mouseout', function () {
    if (!playPauseButton.classList.contains('paused')) {
        carousel.cycle();
    }
});
