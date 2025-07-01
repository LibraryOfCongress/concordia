/* global jQuery */

jQuery(function ($) {
    $('.toggle-publications').click(function (event) {
        $('.accordion-icon', event.delegateTarget).toggleClass(
            'icon-plus-square icon-minus-square',
        );
        $('.publications-content').toggle();
    });
    $('.toggle-press').click(function (event) {
        $('.accordion-icon', event.delegateTarget).toggleClass(
            'icon-plus-square icon-minus-square',
        );
        $('.press-content').toggle();
    });
});
