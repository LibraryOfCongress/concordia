/* global jQuery displayMessage displayHtmlMessage buildErrorMessage Sentry */
/* exported attemptToReserveAsset */

function attemptToReserveAsset(reservationURL, findANewPageURL, actionType) {
    var $transcriptionEditor = jQuery('#transcription-editor');

    jQuery
        .ajax({
            url: reservationURL,
            type: 'POST',
            dataType: 'json',
        })
        .done(function () {
            $transcriptionEditor
                .data('hasReservation', true)
                .trigger('update-ui-state');

            // If the asset was successfully reserved, continue reserving it
            window.setTimeout(
                attemptToReserveAsset,
                60_000,
                reservationURL,
                findANewPageURL,
                actionType,
            );
        })
        .fail(function (jqXHR, textStatus, errorThrown) {
            if (jqXHR.status == 409) {
                if (actionType == 'transcribe') {
                    $transcriptionEditor
                        .data('hasReservation', false)
                        .trigger('update-ui-state');
                    jQuery('#asset-reservation-failure-modal').modal();
                } else {
                    displayHtmlMessage(
                        'warning',
                        'There are other reviewers on this page.' +
                            ' <a href="' +
                            findANewPageURL +
                            '">Find a new page to review</a>',
                        'transcription-reservation',
                    );
                    Sentry.captureException(errorThrown, function (scope) {
                        scope.setTransactionName(
                            '409 error when attempting to reserve asset at ' +
                                reservationURL,
                        );
                    });
                }
            } else if (jqXHR.status == 408) {
                $transcriptionEditor
                    .data('hasReservation', false)
                    .trigger('update-ui-state');
                jQuery('#asset-reservation-failure-modal').modal();
                Sentry.captureException(errorThrown, function (scope) {
                    scope.setTransactionName(
                        '408 error when attempting to reserve asset at ' +
                            reservationURL,
                    );
                });
            } else {
                displayMessage(
                    'error',
                    'Unable to reserve this page: ' +
                        buildErrorMessage(jqXHR, textStatus, errorThrown),
                    'transcription-reservation',
                );
                Sentry.captureException(errorThrown, function (scope) {
                    scope.setTransactionName(
                        'Error when attempting to reserve asset at ' +
                            reservationURL,
                    );
                });
            }
        });

    window.addEventListener('beforeunload', function () {
        var payload = {
            release: true,
            csrfmiddlewaretoken: jQuery(
                'input[name="csrfmiddlewaretoken"]',
            ).val(),
        };

        // We'll try Beacon since that's reliable but until we can drop support for IE11 we need a fallback:
        if ('sendBeacon' in navigator) {
            navigator.sendBeacon(
                reservationURL,
                new Blob([jQuery.param(payload)], {
                    type: 'application/x-www-form-urlencoded',
                }),
            );
        } else {
            jQuery.ajax({url: reservationURL, type: 'POST', data: payload});
        }
    });
}
