/* global jQuery */

jQuery(function ($) {
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
});
