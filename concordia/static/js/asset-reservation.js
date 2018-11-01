/* global jQuery displayMessage buildErrorMessage */
/* exported attemptToReserveAsset */

function attemptToReserveAsset(reservationURL) {
    var $transcriptionEditor = jQuery('#transcription-editor');

    jQuery
        .ajax({
            url: reservationURL,
            type: 'POST'
        })
        .done(function() {
            $transcriptionEditor
                .data('hasReservation', true)
                .trigger('update-ui-state');
        })
        .fail(function(jqXHR, textStatus, errorThrown) {
            /* TODO: add handling for 429 rate limited error */
            if (jqXHR.status == 409) {
                $transcriptionEditor
                    .data('hasReservation', false)
                    .trigger('update-ui-state');
                jQuery('#asset-reservation-failure-modal').modal();
            } else {
                displayMessage(
                    'error',
                    'Unable to reserve this page: ' +
                        buildErrorMessage(jqXHR, textStatus, errorThrown),
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
