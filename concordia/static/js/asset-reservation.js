/* global jQuery displayMessage */
/* exported attemptToReserveAsset */

function attemptToReserveAsset(reservationURL) {
    jQuery
        .ajax({
            url: reservationURL,
            type: 'POST'
        })
        .done(function() {
            displayMessage(
                'info',
                'You have exclusive permission to transcribe this page',
                'transcription-reservation'
            );
        })
        .fail(function(jqXHR, textStatus, errorThrown) {
            if (jqXHR.status == 409) {
                displayMessage(
                    'warning',
                    'Someone else is currently transcribing this page',
                    'transcription-reservation'
                );
            } else {
                displayMessage(
                    'error',
                    'Unable to reserve this page: ' +
                        textStatus +
                        ' ' +
                        errorThrown,
                    'transcription-reservation'
                );
            }
        })
        .always(function() {
            window.setTimeout(attemptToReserveAsset, 60000, reservationURL);
        });

    window.addEventListener('beforeunload', function() {
        var payload = {
            release: true,
            csrfmiddlewaretoken: jQuery(
                'input[name="csrfmiddlewaretoken"]'
            ).val()
        };

        // We'll try Beacon since that's reliable but until we can drop support for IE11 we need a fallback:
        if ('sendBeacon' in navigator) {
            navigator.sendBeacon(
                reservationURL,
                new Blob([jQuery.param(payload)], {
                    type: 'application/x-www-form-urlencoded'
                })
            );
        } else {
            jQuery.ajax({url: reservationURL, type: 'POST', data: payload});
        }
    });
}
