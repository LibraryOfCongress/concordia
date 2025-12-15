import $ from 'jquery';
import {Modal} from 'bootstrap';
import {buildErrorMessage, displayHtmlMessage, displayMessage} from './base.js';
import * as Sentry from '@sentry/browser';

const assetReservationElement = document.getElementById(
    'asset-reservation-data',
);
const assetReservationData = assetReservationElement
    ? assetReservationElement.dataset
    : {};

function attemptToReserveAsset(reservationURL, findANewPageURL, actionType) {
    let $transcriptionEditor = $('#transcription-editor');
    // We need to do this because BS5 does not automatically initialize modals when you
    // try to show them; without new boostrap.Modal, it doesn't recognize it as a modal
    // at all (it's treated as ordinary HTML), so BS controls do not work
    var reservationModalElement = document.getElementById(
        'asset-reservation-failure-modal',
    );
    // This tries to get the modal if it exists, otherwise it initializes it
    var reservationModal =
        Modal.getInstance(reservationModalElement) ||
        new Modal(reservationModalElement);

    $.ajax({
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
                    reservationModal.show();
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
                reservationModal.show();
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
}

window.addEventListener('beforeunload', function () {
    let payload = {
        release: true,
        csrfmiddlewaretoken: $('input[name="csrfmiddlewaretoken"]').val(),
    };

    // We'll try Beacon since that's reliable but until we can drop support for IE11 we need a fallback:
    if ('sendBeacon' in navigator) {
        navigator.sendBeacon(
            assetReservationData.reserveAssetUrl,
            new Blob([$.param(payload)], {
                type: 'application/x-www-form-urlencoded',
            }),
        );
    } else {
        $.ajax({
            url: assetReservationData.reserveAssetUrl,
            type: 'POST',
            data: payload,
        });
    }
});

function reserveAssetForEditing() {
    if (assetReservationData.reserveAssetUrl) {
        attemptToReserveAsset(
            assetReservationData.reserveAssetUrl,
            '',
            'transcribe',
        );
    }
}

$(function () {
    if (assetReservationData.reserveForEditing) {
        reserveAssetForEditing();
    }
});

export {reserveAssetForEditing};
