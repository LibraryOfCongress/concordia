import $ from 'jquery';
import {Carousel} from 'bootstrap';

document.addEventListener('DOMContentLoaded', () => {
    const carouselElement = document.getElementById('homepage-carousel');
    if (!carouselElement) return; // exit if not on homepage

    // avoid double init
    const carousel = Carousel.getOrCreateInstance(carouselElement, {
        interval: 5000,
        pause: false,
        ride: 'carousel',
    });

    const playPauseButton = document.getElementById('play-pause-button');
    if (!playPauseButton) return;

    playPauseButton.addEventListener('click', function () {
        if ($(this).hasClass('paused')) {
            carousel.cycle();
        } else {
            carousel.pause();
        }
        $(this).children('.fa').toggleClass('fa-pause').toggleClass('fa-play');
        $(this).toggleClass('paused');
    });

    carouselElement.addEventListener('mouseover', () => {
        carousel.pause();
    });

    carouselElement.addEventListener('mouseleave', () => {
        if (!playPauseButton.classList.contains('paused')) {
            carousel.cycle();
        }
    });
});
