/* global $ */

import {Carousel} from '/static/bootstrap/dist/js/bootstrap.esm.js';

// initialization
var carouselElement = document.getElementById('homepage-carousel');
var carousel = new Carousel(carouselElement, {
    interval: 5000,
    pause: false,
});

// play/pause
document
    .getElementById('play-pause-button')
    .addEventListener('click', function () {
        if ($(this).hasClass('paused')) {
            carousel.cycle();
            $(this).children('.fa').removeClass('fa-play').addClass('fa-pause');
        } else {
            carousel.pause();
            // console.log(carousel);
            $(this).children('.fa').removeClass('fa-pause').addClass('fa-play');
        }
        $(this).toggleClass('paused');
    });
