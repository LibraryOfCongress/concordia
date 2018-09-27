$(document).ready(function() {
    if (window.location.href.indexOf('#tab-tag') > -1) {
        $('#nav-pill-tag').tab('show');
        $('#tag-input').focus();
    }

    $('#nav-pill-tag, #nav-pill-transcription').click(function(e) {
        var target = e.target.id;
        changeTheURL(target);
    });

    $('input[type="submit"]').click(function(e) {
        var target = e.target.id;
        sessionStorage.setItem('show_message', 'true');

        if (target == 'save-button') {
            sessionStorage.setItem('status', 'save');
        } else if (target == 'review-button') {
            sessionStorage.setItem('status', 'review');
        } else if (target == 'complete-button') {
            sessionStorage.setItem('status', 'complete');
        }
    });
});

function changeTheURL(nav) {
    if (nav == 'nav-pill-tag') {
        window.location.hash = 'tab-tag';
    } else {
        window.location.hash = 'tab-transcription';
    }
}
