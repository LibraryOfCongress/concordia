/* global $ trackUIInteraction */
/* exported openOffcanvas closeOffcanvas showPane hidePane */

function openOffcanvas() {
    var guide = document.getElementById('guide-sidebar');
    guide.classList.remove('offscreen');
    guide.style.borderWidth = '0 0 thick thick';
    guide.style.borderStyle = 'solid';
    guide.style.borderColor = '#0076ad';
    document.getElementById('open-guide').style.display = 'none';
    document.addEventListener('keydown', function (event) {
        if (event.key == 'Escape') {
            closeOffcanvas();
        }
    });
}

function closeOffcanvas() {
    var guide = document.getElementById('guide-sidebar');
    guide.classList.add('offscreen');

    guide.style.border = 'none';
    document.getElementById('open-guide').style.display = 'block';
}

function showPane(elementId) {
    document.getElementById(elementId).classList.add('show', 'active');
    document.getElementById('guide-nav').classList.remove('show', 'active');
}

function hidePane(elementId) {
    document.getElementById(elementId).classList.remove('show', 'active');
    document.getElementById('guide-nav').classList.add('show', 'active');
}

function trackHowToInteraction(element, label) {
    trackUIInteraction(element, 'How To Guide', 'click', label);
}

$('#open-guide').on('click', function () {
    trackHowToInteraction($(this), 'Open');
});
$('#close-guide').on('click', function () {
    trackHowToInteraction($(this), 'Close');
});
$('#previous-guide').on('click', function () {
    trackHowToInteraction($(this), 'Back');
});
$('#next-guide').on('click', function () {
    trackHowToInteraction($(this), 'Next');
});
$('#guide-bars').on('click', function () {
    trackHowToInteraction($(this), 'Hamburger Menu');
});
$('#guide-sidebar .nav-link').on('click', function () {
    let label = $(this).text().trim();
    trackHowToInteraction($(this), label);
});

$('#guide-carousel')
    .carousel({
        interval: false,
        wrap: false,
    })
    .on('slide.bs.carousel', function (event) {
        if (event.to == 0) {
            $('#guide-bars').addClass('d-none');
        } else {
            $('#guide-bars').removeClass('d-none');
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
