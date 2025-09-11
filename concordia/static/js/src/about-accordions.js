import $ from 'jquery';

$(function () {
    $('.toggle-blog-posts').click(function (event) {
        $('.accordion-icon', event.delegateTarget).toggleClass(
            'fa-plus-square fa-minus-square',
        );
        $('.blog-content').toggle();
    });
    $('.toggle-publications').click(function (event) {
        $('.accordion-icon', event.delegateTarget).toggleClass(
            'fa-plus-square fa-minus-square',
        );
        $('.publications-content').toggle();
    });
    $('.toggle-press').click(function (event) {
        $('.accordion-icon', event.delegateTarget).toggleClass(
            'fa-plus-square fa-minus-square',
        );
        $('.press-content').toggle();
    });
    $('.toggle-program-history').click(function (event) {
        $('.accordion-icon', event.delegateTarget).toggleClass(
            'fa-plus-square fa-minus-square',
        );
        $('.program-history').toggle();
    });
});
