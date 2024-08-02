/* global $ trackUIInteraction setTutorialHeight */

function trackQuickTipsInteraction(element, label) {
    trackUIInteraction(element, 'Quick Tips', 'click', label);
}

var mainContentHeight = $('#contribute-main-content').height();
if (mainContentHeight < 710) {
    $('.sidebar').height(mainContentHeight - 130);
}

$('#tutorial-popup').on('shown.bs.modal', function () {
    setTutorialHeight();
});

$('#quick-tips').on('click', function () {
    trackQuickTipsInteraction($(this), 'Open');
});
$('#previous-card').on('click', function () {
    trackQuickTipsInteraction($(this), 'Back');
});
$('#next-card').on('click', function () {
    trackQuickTipsInteraction($(this), 'Next');
});
$('.carousel-indicators li').on('click', function () {
    let index = [...this.parentElement.children].indexOf(this);
    trackQuickTipsInteraction($(this), `Carousel ${index}`);
});
$('#tutorial-popup').on('hidden.bs.modal', function () {
    // We're tracking whenever the popup closes, so we don't separately track the close button being clicked
    trackUIInteraction($(this), 'Quick Tips', 'click', 'Close');
});
$('#tutorial-popup').on('shown-on-load', function () {
    // We set a timeout to make sure the analytics code is loaded before trying to track
    setTimeout(function () {
        trackUIInteraction($(this), 'Quick Tips', 'load', 'Open');
    }, 1000);
});
