import {Modal} from 'bootstrap';
import {selectLanguage} from './ocr.js';
import {reserveAssetForEditing} from './asset-reservation.js';
import $ from 'jquery';
import {buildErrorMessage, displayMessage} from './base.js';

function lockControls($container) {
    if (!$container) {
        return;
    }
    // Locks all of the controls in the provided jQuery element
    $container.find('input, textarea').attr('readonly', 'readonly');
    $container.find('input:checkbox').attr('disabled', 'disabled');
    $container.find('button:not(#open-guide)').attr('disabled', 'disabled');
}

function unlockControls($container) {
    if (!$container) {
        return;
    }
    // Unlocks all of the controls except buttons in the provided jQuery element
    $container.find('input, textarea').removeAttr('readonly');
    $container.find('input:checkbox').removeAttr('disabled');

    // Though we lock all buttons in lockControls, we don't automatically
    // unlock most of them. Which buttons should be locked or unlocked
    // is more complicated logic handled by the update-ui-state
    // listener on the transcription form and the form
    // results handlers.
    // The only buttons unlocked here are ones that should always be unlocked.
    $container.find('button#open-guide').removeAttr('disabled');
    $container.find('button#ocr-transcription-button').removeAttr('disabled');
    $container.find('button#close-guide').removeAttr('disabled');
    $container.find('button#new-tag-button').removeAttr('disabled');
}

$(document).on('keydown', function (event) {
    /*
        Global keyboard event handlers

        * F1 and ? open help
        * Control-I focuses on the image viewer
        * Control-T focuses on the transcription text field

        n.b. jQuery interferes with setting the focus so our handlers use the
        DOM directly
    */

    if (
        (event.which == 112 || event.which == 191) &&
        !event.target.tagName.match(/(INPUT|TEXTAREA)/i) // eslint-disable-line  unicorn/prefer-regexp-test, unicorn/better-regex
    ) {
        // Either the F1 or ? keys were pressed outside of a text field so we'll show help:
        $('#keyboard-help-modal').modal('show');
        return false;
    } else if (event.which == 73 && event.ctrlKey) {
        // Control-I == switch to the image viewer
        document.querySelector('#asset-image .openseadragon-canvas').focus();
        return false;
    } else if (event.which == 84 && event.ctrlKey) {
        // Control-T == switch to the transcription field
        document.getElementById('transcription-input').focus();
        return false;
    }
});

function resetTurnstile() {
    if (window.turnstile) {
        window.turnstile.reset('.cf-turnstile');
    }
}

function setupPage() {
    $('form.ajax-submission').each(function (index, formElement) {
        /*
        Generic AJAX submission logic which takes a form and POSTs its data to the
        configured action URL, locking the controls until it gets a response either
        way.

        If the AJAX request is successful, the form-submit-success custom event will
        be triggered. On failures, form-submit-failure will be triggered after
        unlocking the controls.

        Because there's no standard way to get the value of the submit button
        clicked, and forms may be submitted without using a button at all, the
        <form> element may have optional data-submit-name and data-submit-value
        attributes for the default values and a click handler will be used to
        update those values based on user interaction.

        The optional data-lock-element attribute can be set to lock additional
        elements in the same way the form is locked once its submitted.
        */

        var $form = $(formElement);

        $form.on('submit', function (event) {
            event.preventDefault();

            var eventData = $form.data();

            lockControls($form);
            if (eventData.lockElement) {
                lockControls($(eventData.lockElement));
            }

            var formData = $form.serializeArray();

            $.ajax({
                url: $form.attr('action'),
                method: 'POST',
                dataType: 'json',
                data: $.param(formData),
            })
                .done(function (data, textStatus) {
                    $form.trigger('form-submit-success', {
                        textStatus: textStatus,
                        requestData: formData,
                        responseData: data,
                        $form: $form,
                    });
                    unlockControls($form);
                    if (eventData.lockElement) {
                        unlockControls($(eventData.lockElement));
                    }
                })
                .fail(function (jqXHR, textStatus, errorThrown) {
                    $form.trigger('form-submit-failure', {
                        textStatus: textStatus,
                        errorThrown: errorThrown,
                        requestData: formData,
                        $form: $form,
                        jqXHR: jqXHR,
                    });
                    unlockControls($form);
                    if (eventData.lockElement) {
                        unlockControls($(eventData.lockElement));
                    }
                });

            return false;
        });
    });

    var $transcriptionEditor = $('#transcription-editor');
    var $saveButton = $transcriptionEditor
        .find('#save-transcription-button')
        .first();
    var $submitButton = $transcriptionEditor
        .find('#submit-transcription-button')
        .first();
    var $nothingToTranscribeCheckbox = $transcriptionEditor
        .find('#nothing-to-transcribe')
        .on('change', function () {
            var $textarea = $transcriptionEditor.find('textarea');
            if (this.checked) {
                const nothingToTranscribeElement = document.getElementById(
                    'nothing-to-transcribe-modal',
                );
                if (nothingToTranscribeElement) {
                    const nothingToTranscribeModal =
                        Modal.getInstance(nothingToTranscribeElement) ||
                        new Modal(nothingToTranscribeElement);
                    var nothingToTranscribeTitle =
                        nothingToTranscribeElement.querySelector(
                            '.modal-title',
                        );
                    var nothingToTranscribeBody =
                        nothingToTranscribeElement.querySelector('.modal-body');
                    if ($textarea.val()) {
                        nothingToTranscribeTitle.textContent =
                            'Text will be deleted';
                        nothingToTranscribeBody.innerHTML =
                            '<p>Text in the transcription box is removed when “Nothing to transcribe” is checked. Do you want to discard that text?</p>';
                    } else {
                        nothingToTranscribeTitle.textContent =
                            'Nothing to transcribe';
                        nothingToTranscribeBody.innerHTML =
                            '<p>Are you sure?</p>';
                    }
                    nothingToTranscribeModal.show();

                    const okButton = document.getElementById('confirmDiscard');
                    okButton.addEventListener('click', function () {
                        $textarea.val('');
                        nothingToTranscribeModal.hide();
                    });
                    const cancelButton =
                        document.getElementById('cancelDiscard');
                    cancelButton.addEventListener('click', function () {
                        $('#nothing-to-transcribe').prop('checked', false);
                        nothingToTranscribeModal.hide();
                    });
                }
            }
            $transcriptionEditor.trigger('update-ui-state');
        });
    var $ocrSection = $('#ocr-section');
    var $ocrForm = $('#ocr-transcription-form');
    var $ocrModal = $('#ocr-transcription-modal');
    var $languageModal = $('#language-selection-modal');
    var $ocrLoading = $('#ocr-loading');
    var rollbackButton = document.getElementById(
        'rollback-transcription-button',
    );
    var rollforwardButton = document.getElementById(
        'rollforward-transcription-button',
    );
    // We need to do this because BS5 does not automatically initialize modals when you
    // try to show them; without new boostrap.Modal, it doesn't recognize it as a modal
    // at all (it's treated as ordinary HTML), so BS controls do not work
    // We try to get Modal.getInstance in case the modal is already initialized
    var errorModalElement = document.getElementById('error-modal');
    if (errorModalElement) {
        var errorModal =
            Modal.getInstance(errorModalElement) ||
            new Modal(errorModalElement);
    }
    var submissionModalElement = document.getElementById(
        'successful-submission-modal',
    );
    if (submissionModalElement) {
        var submissionModal =
            Modal.getInstance(submissionModalElement) ||
            new Modal(submissionModalElement);
    }
    var reviewModalElement = document.getElementById('review-accepted-modal');
    if (reviewModalElement) {
        var reviewModal =
            Modal.getInstance(reviewModalElement) ||
            new Modal(reviewModalElement);
    }

    let firstEditorUpdate = true;
    let editorPlaceholderText = $transcriptionEditor
        .find('textarea')
        .attr('placeholder');
    let editorNothingToTranscribePlaceholderText = 'Nothing to transcribe';

    $transcriptionEditor
        .on('update-ui-state', function () {
            /*
             * All controls are locked when the user does not have the write lock
             *
             * The Save button is enabled when the user has changed the text from
             * what it was when the page was loaded or last saved
             *
             * The Submit button is enabled when the user has either made no changes
             * or has saved the transcription and not changed the text
             */

            var data = $transcriptionEditor.data();

            if (
                !data.hasReservation ||
                (data.transcriptionStatus != 'in_progress' &&
                    data.transcriptionStatus != 'not_started' &&
                    data.transcriptionStatus != 'submitted')
            ) {
                // If the status is completed OR if the user doesn't have the reservation
                lockControls($transcriptionEditor);
                lockControls($ocrSection);
                lockControls($ocrForm);
            } else {
                // Either in transcribe or review mode OR the user has the reservation
                if (data.hasReservation) {
                    unlockControls($ocrSection);
                    unlockControls($ocrForm);
                }
                var $textarea = $transcriptionEditor.find('textarea');

                if (
                    $nothingToTranscribeCheckbox.prop('checked') ||
                    data.transcriptionStatus == 'submitted'
                ) {
                    $textarea.attr('readonly', 'readonly');
                    if ($nothingToTranscribeCheckbox.prop('checked')) {
                        $textarea.attr(
                            'placeholder',
                            editorNothingToTranscribePlaceholderText,
                        );
                    }
                } else {
                    $textarea.removeAttr('readonly');
                    $textarea.attr('placeholder', editorPlaceholderText);
                }

                if (data.transcriptionId && !data.unsavedChanges) {
                    // We have a transcription ID and it's not stale,
                    // so we can submit the transcription for review and disable the save button:
                    $saveButton.attr('disabled', 'disabled');
                    $submitButton.removeAttr('disabled');
                    // We only want to do this the first time the editor ui is updated (i.e., on first load)
                    // because otherwise it's impossible to uncheck the 'Nothing to transcribe' checkbox
                    // since this code would just immediately mark it checked again.
                    if (!$textarea.val() && firstEditorUpdate) {
                        $nothingToTranscribeCheckbox.prop('checked', true);
                        $textarea.attr('readonly', 'readonly');
                        $textarea.attr(
                            'placeholder',
                            editorNothingToTranscribePlaceholderText,
                        );
                    }
                } else {
                    // Unsaved changes are in the textarea and we're in transcribe mode
                    $submitButton.attr('disabled', 'disabled');

                    if (
                        $textarea.val() ||
                        $nothingToTranscribeCheckbox.prop('checked')
                    ) {
                        $saveButton.removeAttr('disabled');
                    } else {
                        $saveButton.attr('disabled', 'disabled');
                    }
                }
            }

            if (
                !data.hasReservation &&
                (data.transcriptionStatus == 'in_progress' ||
                    data.transcriptionStatus == 'not_started')
            ) {
                // If we're in transcribe mode and we don't have the reservation
                $('.transcription-status-display')
                    .children()
                    .attr('hidden', 'hidden')
                    .filter('#display-conflict')
                    .removeAttr('hidden');
            }
            firstEditorUpdate = false;
        })
        .on('form-submit-success', function (event, extra) {
            let responseData = extra.responseData;
            displayMessage(
                'info',
                "Successfully saved your work. Submit it for review when you're done",
                'transcription-save-result',
            );
            $transcriptionEditor.data({
                transcriptionId: responseData.id,
                unsavedChanges: false,
            });
            $transcriptionEditor
                .find('input[name="supersedes"]')
                .val(responseData.id);
            $transcriptionEditor
                .find('textarea[name="text"]')
                .val(responseData.text);
            $transcriptionEditor.data('submitUrl', responseData.submissionUrl);
            $ocrForm.find('input[name="supersedes"]').val(responseData.id);
            $('#transcription-status-display')
                .children()
                .attr('hidden', 'hidden')
                .filter('#display-inprogress')
                .removeAttr('hidden');
            if (responseData.undo_available) {
                $('#rollback-transcription-button').removeAttr('disabled');
            }
            if (responseData.redo_available) {
                $('#rollforward-transcription-button').removeAttr('disabled');
            }
            resetTurnstile();
            let messageChildren = $('#transcription-status-message').children();
            messageChildren
                .attr('hidden', 'hidden')
                .filter('#message-inprogress')
                .removeAttr('hidden');
            $('#transcription-status-display').removeAttr('hidden');
            $('#message-contributors')
                .removeAttr('hidden')
                .find('#message-contributors-num')
                .html(responseData.asset.contributors);
            $transcriptionEditor.trigger('update-ui-state');
        })
        .on('form-submit-failure', function (event, info) {
            displayMessage(
                'error',
                'Unable to save your work: ' +
                    buildErrorMessage(
                        info.jqXHR,
                        info.textStatus,
                        info.errorThrown,
                    ),
                'transcription-save-result',
            );
            resetTurnstile();
            $transcriptionEditor.trigger('update-ui-state');
        });

    $submitButton.on('click', function (event) {
        event.preventDefault();

        $.ajax({
            url: $transcriptionEditor.data('submitUrl'),
            method: 'POST',
            dataType: 'json',
        })
            .done(function (data) {
                $('#transcription-status-display')
                    .children()
                    .attr('hidden', 'hidden');
                let messageChildren = $(
                    '#transcription-status-display',
                ).children();
                messageChildren
                    .attr('hidden', 'hidden')
                    .filter('#message-submitted')
                    .removeAttr('hidden');
                $('#display-submitted').removeAttr('hidden');
                messageChildren
                    .filter('#message-contributors')
                    .removeAttr('hidden')
                    .find('#message-contributors-num')
                    .html(data.asset.contributors);
                submissionModal.show();
                submissionModalElement.addEventListener(
                    'hidden.bs.modal',
                    function () {
                        window.location.reload(true);
                    },
                );
            })
            .fail(function (jqXHR, textStatus, errorThrown) {
                displayMessage(
                    'error',
                    'Unable to save your work: ' +
                        buildErrorMessage(jqXHR, textStatus, errorThrown),
                    'transcription-submit-result',
                );
            });
    });

    $transcriptionEditor
        .find('textarea')
        .each(function (index, textarea) {
            textarea.value = $.trim(textarea.value);
        })
        .on('change input', function () {
            $transcriptionEditor.data('unsavedChanges', true);
            $transcriptionEditor.trigger('update-ui-state');
        });

    function submitReview(status) {
        var reviewUrl = $transcriptionEditor.data('reviewUrl');
        $.ajax({
            url: reviewUrl,
            method: 'POST',
            dataType: 'json',
            data: {
                action: status,
            },
        })
            .done(function (data) {
                if (status == 'reject') {
                    $.ajax({
                        url: window.location,
                        method: 'GET',
                        dataType: 'html',
                    })
                        .done(function (data) {
                            $('#editor-column').html(
                                $(data).find('#editor-column').html(),
                            );
                            $('#ocr-section').html(
                                $(data).find('#ocr-section').html(),
                            );
                            $('#help-container').html(
                                $(data).find('#help-container').html(),
                            );
                            $ocrModal.html(
                                $(data).find('#ocr-transcription-modal').html(),
                            );
                            $('#select-language-button').on(
                                'click',
                                selectLanguage,
                            );
                            reserveAssetForEditing();
                            setupPage();
                        })
                        .fail(function (jqXHR, textStatus, errorThrown) {
                            displayMessage(
                                'error',
                                'Unable to save your review: ' +
                                    buildErrorMessage(
                                        jqXHR,
                                        textStatus,
                                        errorThrown,
                                    ),
                                'transcription-review-result',
                            );
                        });
                } else {
                    $('#transcription-status-display')
                        .children()
                        .attr('hidden', 'hidden');
                    $('#display-completed').removeAttr('hidden');
                    let messageChildren = $(
                        '#transcription-status-message',
                    ).children();
                    messageChildren
                        .attr('hidden', 'hidden')
                        .filter('#message-completed')
                        .removeAttr('hidden');
                    $('#transcription-status-display').removeAttr('hidden');
                    messageChildren
                        .filter('#message-contributors')
                        .removeAttr('hidden')
                        .find('#message-contributors-num')
                        .html(data.asset.contributors);
                    reviewModal.show();
                    reviewModalElement.addEventListener(
                        'hidden.bs.modal',
                        function () {
                            window.location.reload(true);
                        },
                    );
                }
            })
            .fail(function (jqXHR, textStatus, errorThrown) {
                displayMessage(
                    'error',
                    'Unable to save your review: ' +
                        buildErrorMessage(jqXHR, textStatus, errorThrown),
                    'transcription-review-result',
                );
                if (jqXHR.responseJSON && jqXHR.responseJSON.popupError) {
                    let popupErrorMessage = jqXHR.responseJSON.popupError;
                    let popupTitle;
                    if (jqXHR.responseJSON.popupTitle) {
                        popupTitle = jqXHR.responseJSON.popupTitle;
                    } else {
                        popupTitle = 'An error occurred with your review';
                    }
                    $('#error-modal')
                        .find('#error-modal-title')
                        .first()
                        .html(popupTitle);
                    $('#error-modal')
                        .find('#error-modal-message')
                        .first()
                        .html(popupErrorMessage);
                    errorModal.show();
                }
            });
    }

    $('#accept-transcription-button')
        .removeAttr('disabled')
        .on('click', function (event) {
            event.preventDefault();
            submitReview('accept');
        });

    $('#reject-transcription-button')
        .removeAttr('disabled')
        .on('click', function (event) {
            event.preventDefault();
            submitReview('reject');
        });

    function rollTranscription(url) {
        lockControls($transcriptionEditor);
        $.ajax({
            url: url,
            method: 'POST',
            dataType: 'json',
            data: {
                'cf-turnstile-response': $transcriptionEditor
                    .find('input[name="cf-turnstile-response"]')
                    .val(),
            },
        })
            .done(function (responseData) {
                displayMessage(
                    'info',
                    responseData.message,
                    'transcription-save-result',
                );
                $transcriptionEditor.data({
                    transcriptionId: responseData.id,
                    unsavedChanges: false,
                });
                $transcriptionEditor
                    .find('input[name="supersedes"]')
                    .val(responseData.id);
                $transcriptionEditor.data(
                    'submitUrl',
                    responseData.submissionUrl,
                );
                $ocrForm.find('input[name="supersedes"]').val(responseData.id);
                $transcriptionEditor
                    .find('textarea[name="text"]')
                    .val(responseData.text);
                $('#transcription-status-display')
                    .children()
                    .attr('hidden', 'hidden')
                    .filter('#display-inprogress')
                    .removeAttr('hidden');
                if (responseData.undo_available) {
                    $('#rollback-transcription-button').removeAttr('disabled');
                }
                if (responseData.redo_available) {
                    $('#rollforward-transcription-button').removeAttr(
                        'disabled',
                    );
                }
                let messageChildren = $(
                    '#transcription-status-display',
                ).children();
                messageChildren
                    .attr('hidden', 'hidden')
                    .filter('#display-inprogress')
                    .removeAttr('hidden');
                messageChildren
                    .filter('#message-contributors')
                    .removeAttr('hidden')
                    .find('#message-contributors-num')
                    .html(responseData.asset.contributors);
                unlockControls($transcriptionEditor);
                $transcriptionEditor.trigger('update-ui-state');
            })
            .fail(function (jqXHR, textStatus, errorThrown) {
                displayMessage(
                    'error',
                    'Unable to save your work: ' +
                        buildErrorMessage(jqXHR, textStatus, errorThrown),
                    'transcription-save-result',
                );
                unlockControls($transcriptionEditor);
                $transcriptionEditor.trigger('update-ui-state');
            });
    }

    if (rollbackButton) {
        rollbackButton.addEventListener('click', function () {
            rollTranscription(this.dataset.url);
        });
    }

    if (rollforwardButton) {
        rollforwardButton.addEventListener('click', function () {
            rollTranscription(this.dataset.url);
        });
    }

    var $tagEditor = $('#tag-editor'),
        $tagForm = $('#tag-form'),
        $currentTagList = $tagEditor.find('#current-tags'),
        $newTagInput = $('#new-tag-input');

    const characterError =
        'Tags must be between 1-50 characters and may contain only letters, numbers, dashes, underscores, apostrophes, and spaces';
    const duplicateError =
        'That tag has already been added. Each tag can only be added once.';

    function addNewTag() {
        $newTagInput.get(0).setCustomValidity(''); // Resets custom validation
        const $form = $newTagInput.closest('form');
        $form.removeClass('was-validated');
        $newTagInput.val(
            $newTagInput.val().replace('‘', "'").replace('’', "'"),
        );
        if (!$newTagInput.get(0).checkValidity()) {
            $form.find('.invalid-feedback').html(characterError);
            $form.addClass('was-validated');
            return;
        }

        var value = $.trim($newTagInput.val());
        if (value) {
            // Prevent adding tags which are already present:
            var dupeCount = $currentTagList
                .find('input[name="tags"]')
                .filter(function (index, input) {
                    return (
                        input.value.toLocaleLowerCase() ==
                        value.toLocaleLowerCase()
                    );
                }).length;

            if (dupeCount == 0) {
                var $newTag = $(
                    '\
                            <li class="btn btn-outline-dark btn-sm"> \
                                <label class="m-0"> \
                                    <input type="hidden" name="tags" value="' +
                        value +
                        '" /> \
                                </label> \
                                <input type="hidden" name="tags" value="' +
                        value +
                        '" /> \
                                <a class="close" data-bs-dismiss="alert" aria-label="Remove previous tag"> \
                                    <span aria-hidden="true" class="fas fa-times"></span> \
                                </a> \
                            </li> \
                ',
                );
                $newTag.find('label').append(document.createTextNode(value));
                $currentTagList.append($newTag);
                $newTagInput.val('');
                $tagForm.submit();
            } else {
                $newTagInput.get(0).setCustomValidity(duplicateError);
                $form.find('.invalid-feedback').html(duplicateError);
                $newTagInput.closest('form').addClass('was-validated');
                return;
            }
        }
    }

    $tagEditor.find('#new-tag-button').on('click', addNewTag);
    $newTagInput.on('change', addNewTag);
    $newTagInput.on('keydown', function (event) {
        // See https://github.com/LibraryOfCongress/concordia/issues/159 for the source of these values:
        if (event.which == '13' || event.which == '188') {
            // Either the enter or comma keys will add the tag and reset the input field:
            event.preventDefault();
            addNewTag();
        }
    });

    $currentTagList.on('click', '.close', function () {
        $(this).parents('li').remove();
        $tagForm.submit();
    });

    $tagEditor
        .on('form-submit-success', function (event, info) {
            $('#tag-count').html(info.responseData['all_tags'].length);
            unlockControls($tagEditor);
            displayMessage(
                'info',
                'Your tags have been saved',
                'tags-save-result',
            );
        })
        .on('form-submit-failure', function (event, info) {
            unlockControls($tagEditor);

            var message = 'Unable to save your tags: ';
            message += buildErrorMessage(
                info.jqXHR,
                info.textStatus,
                info.errorThrown,
            );

            displayMessage('error', message, 'tags-save-result');
        });

    if ($ocrForm) {
        $ocrForm
            .on('submit', function () {
                $languageModal.modal('hide');
                $ocrLoading.removeAttr('hidden');
            })
            .on('form-submit-success', function (event, extra) {
                let responseData = extra.responseData;
                $transcriptionEditor.data({
                    transcriptionId: responseData.id,
                    unsavedChanges: false,
                });
                $transcriptionEditor
                    .find('input[name="supersedes"]')
                    .val(responseData.id);
                $transcriptionEditor.data(
                    'submitUrl',
                    responseData.submissionUrl,
                );
                $transcriptionEditor
                    .find('textarea[name="text"]')
                    .val(responseData.text);
                $ocrLoading.attr('hidden', 'hidden');
                $('#transcription-status-display')
                    .children()
                    .attr('hidden', 'hidden');
                $('#display-inprogress').removeAttr('hidden');
                let messageChildren = $(
                    '#transcription-status-message',
                ).children();
                if (responseData.undo_available) {
                    $('#rollback-transcription-button').removeAttr('disabled');
                }
                if (responseData.redo_available) {
                    $('#rollforward-transcription-button').removeAttr(
                        'disabled',
                    );
                }
                messageChildren
                    .attr('hidden', 'hidden')
                    .filter('#message-inprogress')
                    .removeAttr('hidden');
                messageChildren
                    .filter('#message-contributors')
                    .removeAttr('hidden')
                    .find('#message-contributors-num')
                    .html(responseData.asset.contributors);
                $('#transcription-status-display').removeAttr('hidden');
                $transcriptionEditor.trigger('update-ui-state');
                $ocrForm.find('input[name="supersedes"]').val(responseData.id);
            })
            .on('form-submit-failure', function (event, info) {
                let errorMessage;
                if (info.jqXHR.status == 429) {
                    errorMessage =
                        'OCR is only available once per minute. Please try again later and review all OCR text closely before submitting.';
                } else {
                    errorMessage = buildErrorMessage(
                        info.jqXHR,
                        info.textStatus,
                        info.errorThrown,
                    );
                }
                displayMessage(
                    'error',
                    'Unable to save your work: ' + errorMessage,
                    'transcription-save-result',
                );
                $ocrLoading.attr('hidden', 'hidden');
                $transcriptionEditor.trigger('update-ui-state');
            });
    }
}

let transcriptionForm = document.getElementById('transcription-editor');
let ocrForm = document.getElementById('ocr-transcription-form');

let formChanged = false;
if (transcriptionForm) {
    transcriptionForm.addEventListener('change', function () {
        formChanged = true;
    });
    transcriptionForm.addEventListener('submit', function () {
        formChanged = false;
    });
}
if (ocrForm) {
    ocrForm.addEventListener('submit', function () {
        formChanged = false;
    });
}
window.addEventListener('beforeunload', function (event) {
    if (formChanged) {
        // Some browsers ignore this value and always display a built-in message instead
        return (event.returnValue =
            "The transcription you've started has not been saved.");
    }
});
$('#asset-reservation-failure-modal').click(function () {
    document.getElementById('transcription-input').placeholder =
        "Someone else is already transcribing this page.\n\nYou can help by transcribing a new page, adding tags to this page, or coming back later to review this page's transcription.";
});

setupPage();
