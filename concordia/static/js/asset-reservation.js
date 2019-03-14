/* global jQuery displayMessage displayHtmlMessage buildErrorMessage */
/* exported attemptToReserveAsset */

function attemptToReserveAsset(
    reservationURL,
    findANewPageURL,
    actionType,
    firstTime
) {
    var $transcriptionEditor = jQuery('#transcription-editor');

    jQuery
        .ajax({
            url: reservationURL,
            type: 'POST',
            dataType: 'json'
        })
        .done(function() {
            $transcriptionEditor
                .data('hasReservation', true)
                .trigger('update-ui-state');
        })
        .fail(function(jqXHR, textStatus, errorThrown) {
            if (jqXHR.status == 409) {
                if (actionType == 'transcribe') {
                    $transcriptionEditor
                        .data('hasReservation', false)
                        .trigger('update-ui-state');
                    if (firstTime) {
                        jQuery('#asset-reservation-failure-modal').modal();
                    }
                } else {
                    displayHtmlMessage(
                        'warning',
                        'There are other reviewers on this page.' +
                            ' <a href="' +
                            findANewPageURL +
                            '">Find a new page to review</a>',
                        'transcription-reservation'
                    );
                }
            } else {
                displayMessage(
                    'error',
                    'Unable to reserve this page: ' +
                        buildErrorMessage(jqXHR, textStatus, errorThrown),
                    'transcription-reservation'
                );
            }
        });
    /*
        // TODO: implement UI updates for when the transcription has been updated and / or status changed
        // by the user who has the asset reservation. This type of timed update (below) only works correctly when
        // the user who has the asset reservation navigates away from the page without doing anything.
        // e.g. we don't want to re-enable a blank textarea when the user with the reservation has already
        // updated the transcription (and even possibly the asset status) in the background.
        .always(function() {
            window.setTimeout(attemptToReserveAsset, 60000, reservationURL, findANewPageURL, actionType, false);
        });
        */
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
