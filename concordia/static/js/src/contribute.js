/* global $ displayMessage buildErrorMessage reserveAssetForEditing */

function lockControls($container) {
    if (!$container) {
        return;
    }
    // Locks all of the controls in the provided jQuery element
    $container.find('input, textarea').attr('readonly', 'readonly');
    $container.find('input:checkbox').attr('disabled', 'disabled');
    $container.find('button').attr('disabled', 'disabled');
}

function unlockControls($container) {
    if (!$container) {
        return;
    }
    // Unlocks all of the controls in the provided jQuery element
    $container.find('input, textarea').removeAttr('readonly');
    $container.find('input:checkbox').removeAttr('disabled');
    $container.find('button').removeAttr('disabled');
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

function setupPage() {
    var $captchaModal = $('#captcha-modal');
    var $triggeringCaptchaForm = false;
    var $captchaForm = $captchaModal
        .find('form')
        .on('submit', function (event) {
            event.preventDefault();

            var formData = $captchaForm.serializeArray();

            $.ajax({
                url: $captchaForm.attr('action'),
                method: 'POST',
                dataType: 'json',
                data: $.param(formData),
            })
                .done(function () {
                    $captchaModal.modal('hide');
                    if ($triggeringCaptchaForm) {
                        $triggeringCaptchaForm.submit();
                    }
                    $triggeringCaptchaForm = false;
                })
                .fail(function (jqXHR) {
                    if (jqXHR.status == 401) {
                        $captchaModal
                            .find('[name=key]')
                            .val(jqXHR.responseJSON.key);
                        $captchaModal
                            .find('#captcha-image')
                            .attr('src', jqXHR.responseJSON.image);
                    }
                });
        });

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

            var data = $form.data();

            lockControls($form);
            if (data.lockElement) {
                lockControls($(data.lockElement));
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
                    if (data.lockElement) {
                        unlockControls($(data.lockElement));
                    }
                })
                .fail(function (jqXHR, textStatus, errorThrown) {
                    if (jqXHR.status == 401) {
                        $captchaModal
                            .find('[name=key]')
                            .val(jqXHR.responseJSON.key);
                        $captchaModal
                            .find('#captcha-image')
                            .attr('src', jqXHR.responseJSON.image);
                        $triggeringCaptchaForm = $form;
                        $captchaModal.modal();
                    } else {
                        $form.trigger('form-submit-failure', {
                            textStatus: textStatus,
                            errorThrown: errorThrown,
                            requestData: formData,
                            $form: $form,
                            jqXHR: jqXHR,
                        });
                        unlockControls($form);
                        if (data.lockElement) {
                            unlockControls($(data.lockElement));
                        }
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
                if ($textarea.val()) {
                    if (
                        confirm(
                            'You currently have entered text which will not be saved because “Nothing to transcribe” is checked. Do you want to discard that text?',
                        )
                    ) {
                        $textarea.val('');
                    } else {
                        this.checked = false;
                    }
                } else if (!confirm('Are you sure?')) {
                    this.checked = false;
                }
            }
            $transcriptionEditor.trigger('update-ui-state');
        });
    var $ocrSection = $('#ocr-section');
    var $ocrForm = $('#ocr-transcription-form');
    var $ocrModal = $('#ocr-transcription-modal');
    var $languageModal = $('#language-selection-modal');
    var $ocrLoading = $('#ocr-loading');

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
                    // We have a transcription ID and it's not stale, so we can submit the transcription for review:
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
            displayMessage(
                'info',
                "Successfully saved your work. Submit it for review when you're done",
                'transcription-save-result',
            );
            $transcriptionEditor.data({
                transcriptionId: extra.responseData.id,
                unsavedChanges: false,
            });
            $transcriptionEditor
                .find('input[name="supersedes"]')
                .val(extra.responseData.id);
            $transcriptionEditor.data(
                'submitUrl',
                extra.responseData.submissionUrl,
            );
            $ocrForm
                .find('input[name="supersedes"]')
                .val(extra.responseData.id);
            $('#transcription-status-display')
                .children()
                .attr('hidden', 'hidden')
                .filter('#display-inprogress')
                .removeAttr('hidden');
            let messageChildren = $('#transcription-status-message').children();
            messageChildren
                .attr('hidden', 'hidden')
                .filter('#message-inprogress')
                .removeAttr('hidden');
            messageChildren
                .filter('#message-contributors')
                .removeAttr('hidden')
                .find('#message-contributors-num')
                .html(extra.responseData.asset.contributors);
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
                    .attr('hidden', 'hidden')
                    .filter('#display-submitted')
                    .removeAttr('hidden');
                let messageChildren = $(
                    '#transcription-status-message',
                ).children();
                messageChildren
                    .attr('hidden', 'hidden')
                    .filter('#message-submitted')
                    .removeAttr('hidden');
                messageChildren
                    .filter('#message-contributors')
                    .removeAttr('hidden')
                    .find('#message-contributors-num')
                    .html(data.asset.contributors);
                $('#successful-submission-modal')
                    .modal()
                    .on('hidden.bs.modal', function () {
                        window.location.reload(true);
                    });
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
                            $('#help-container').html(
                                $(data).find('#help-container').html(),
                            );
                            $ocrModal.html(
                                $(data).find('#ocr-transcription-modal').html(),
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
                        .attr('hidden', 'hidden')
                        .filter('#display-completed')
                        .removeAttr('hidden');
                    let messageChildren = $(
                        '#transcription-status-message',
                    ).children();
                    console.log(messageChildren);
                    messageChildren
                        .attr('hidden', 'hidden')
                        .filter('#message-completed')
                        .removeAttr('hidden');
                    messageChildren
                        .filter('#message-contributors')
                        .removeAttr('hidden')
                        .find('#message-contributors-num')
                        .html(data.asset.contributors);
                    $('#review-accepted-modal')
                        .modal()
                        .on('hidden.bs.modal', function () {
                            window.location.reload(true);
                        });
                }
            })
            .fail(function (jqXHR, textStatus, errorThrown) {
                displayMessage(
                    'error',
                    'Unable to save your review: ' +
                        buildErrorMessage(jqXHR, textStatus, errorThrown),
                    'transcription-review-result',
                );
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
                                <button type="button" class="close" data-dismiss="alert" aria-label="Remove previous tag"> \
                                    <span aria-hidden="true" class="fas fa-times"></span> \
                                </button> \
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
                $transcriptionEditor.data({
                    transcriptionId: extra.responseData.id,
                    unsavedChanges: false,
                });
                $transcriptionEditor
                    .find('input[name="supersedes"]')
                    .val(extra.responseData.id);
                $transcriptionEditor.data(
                    'submitUrl',
                    extra.responseData.submissionUrl,
                );
                $transcriptionEditor
                    .find('textarea[name="text"]')
                    .val(extra.responseData.text);
                $ocrLoading.attr('hidden', 'hidden');
                $('#transcription-status-display')
                    .children()
                    .attr('hidden', 'hidden')
                    .filter('#display-inprogress')
                    .removeAttr('hidden');
                let messageChildren = $(
                    '#transcription-status-message',
                ).children();
                messageChildren
                    .attr('hidden', 'hidden')
                    .filter('#message-inprogress')
                    .removeAttr('hidden');
                messageChildren
                    .filter('#message-contributors')
                    .removeAttr('hidden')
                    .find('#message-contributors-num')
                    .html(extra.responseData.asset.contributors);
                $transcriptionEditor.trigger('update-ui-state');
                $ocrForm
                    .find('input[name="supersedes"]')
                    .val(extra.responseData.id);
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

setupPage();
