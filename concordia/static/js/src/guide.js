/* global $ trackUIInteraction */

function openOffcanvas() {
    let guide = document.getElementById('guide-sidebar');
    if (guide.classList.contains('offscreen')) {
        guide.classList.remove('offscreen');
        guide.style.borderWidth = '0 0 thick thick';
        guide.style.borderStyle = 'solid';
        guide.style.borderColor = '#0076ad';
        document.addEventListener('keydown', function (event) {
            if (event.key == 'Escape') {
                closeOffcanvas();
            }
        });
        document.getElementById('open-guide').style.background = '#002347';
    } else {
        closeOffcanvas();
    }
}

function closeOffcanvas() {
    let guide = document.getElementById('guide-sidebar');
    guide.classList.add('offscreen');
    guide.style.border = 'none';

    document.getElementById('open-guide').style.background = '#0076AD';
}

$('#open-guide').on('click', openOffcanvas);

$('#close-guide').on('click', closeOffcanvas);

$(function () {
    $('#guide-carousel')
        .carousel({
            interval: false,
            wrap: false,
        })
        .on('slide.bs.carousel', function (event) {
            if (event.to == 0) {
                $('#guide-bars-col').addClass('d-none');
            } else {
                $('#guide-bars-col').removeClass('d-none');
            }
        });
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

export {openOffcanvas, closeOffcanvas};
