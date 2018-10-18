/* global $ displayMessage */

function lockControls($container) {
    // Locks all of the controls in the provided jQuery element
    $container.find('input, textarea').attr('readonly', 'readonly');
    $container.find('button').attr('disabled', 'disabled');
}

function unlockControls($container) {
    // Locks all of the controls in the provided jQuery element
    $container.find('input, textarea').removeAttr('readonly');
    $container.find('button').removeAttr('disabled');
}

function buildErrorMessage(jqXHR, textStatus, errorThrown) {
    /* Construct a nice error message using optional JSON response context */
    var errMessage;
    if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
        errMessage = jqXHR.responseJSON.error;
    } else {
        errMessage = textStatus + ' ' + errorThrown;
    }
    return errMessage;
}

$('form.ajax-submission').each(function(idx, formElement) {
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
    */

    var $form = $(formElement);

    $form.on('submit', function(evt) {
        evt.preventDefault();

        lockControls($form);

        var formData = $form.serializeArray();

        $.ajax({
            url: $form.attr('action'),
            method: 'POST',
            data: $.param(formData)
        })
            .done(function(data, textStatus) {
                $form.trigger('form-submit-success', {
                    textStatus: textStatus,
                    requestData: formData,
                    responseData: data,
                    $form: $form
                });
            })
            .fail(function(jqXHR, textStatus, errorThrown) {
                $form.trigger('form-submit-failure', {
                    textStatus: textStatus,
                    errorThrown: errorThrown,
                    requestData: formData,
                    $form: $form,
                    jqXHR: jqXHR
                });
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
    .on('change', function() {
        var $textarea = $transcriptionEditor.find('textarea');
        if (this.checked && $textarea.val()) {
            if (
                confirm(
                    'You currently have entered text which will not be saved because “Nothing to transcribe” is checked. Do you want to discard that text?'
                )
            ) {
                $textarea.val('');
            } else {
                this.checked = false;
            }
        }
        $transcriptionEditor.trigger('update-ui-state');
    });

$transcriptionEditor
    .on('update-ui-state', function() {
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

        if (!data.hasReservation || data.transcriptionStatus != 'edit') {
            lockControls($transcriptionEditor);
        } else {
            var $textarea = $transcriptionEditor.find('textarea');

            if ($nothingToTranscribeCheckbox.prop('checked')) {
                $textarea.attr('readonly', 'readonly');
            } else {
                $textarea.removeAttr('readonly');
            }

            if (data.transcriptionId && !data.unsavedChanges) {
                // We have a transcription ID and it's not stale, so we can submit the transcription for review:
                $saveButton.attr('disabled', 'disabled');
                $submitButton.removeAttr('disabled');
                if (!$textarea.val()) {
                    $nothingToTranscribeCheckbox.prop('checked', true);
                }
            } else {
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

        if (!data.hasReservation && data.transcriptionStatus == 'edit') {
            $('.tx-status-display')
                .children()
                .attr('hidden', 'hidden')
                .filter('.tx-edit-conflict')
                .removeAttr('hidden');
        }
    })
    .on('form-submit-success', function(evt, extra) {
        displayMessage(
            'info',
            "Successfully saved your work. Submit it for review when you're done",
            'transcription-save-result'
        );
        $transcriptionEditor.data({
            transcriptionId: extra.responseData.id,
            unsavedChanges: false
        });
        $transcriptionEditor
            .find('input[name="supersedes"]')
            .val(extra.responseData.id);
        $transcriptionEditor.data(
            'submitUrl',
            extra.responseData.submissionUrl
        );
        $transcriptionEditor.trigger('update-ui-state');
    })
    .on('form-submit-failure', function(evt, info) {
        displayMessage(
            'error',
            'Unable to save your work: ' +
                buildErrorMessage(
                    info.jqXHR,
                    info.textStatus,
                    info.errorThrown
                ),
            'transcription-save-result'
        );
        $transcriptionEditor.trigger('update-ui-state');
    });

$submitButton.on('click', function(evt) {
    evt.preventDefault();

    $.ajax({
        url: $transcriptionEditor.data('submitUrl'),
        method: 'POST'
    })
        .done(function() {
            $('.tx-status-display')
                .children()
                .attr('hidden', 'hidden')
                .has('.tx-submitted')
                .removeAttr('hidden');
            $('#successful-submission-modal')
                .modal()
                .on('hidden.bs.modal', function() {
                    window.location.reload(true);
                });
        })
        .fail(function(jqXHR, textStatus, errorThrown) {
            displayMessage(
                'error',
                'Unable to save your work: ' +
                    buildErrorMessage(jqXHR, textStatus, errorThrown),
                'transcription-submit-result'
            );
        });
});

$transcriptionEditor
    .find('textarea')
    .each(function(idx, textarea) {
        textarea.value = $.trim(textarea.value);
    })
    .on('change input', function() {
        $transcriptionEditor.data('unsavedChanges', true);
        $transcriptionEditor.trigger('update-ui-state');
    });

function submitReview(status) {
    var reviewUrl = $transcriptionEditor.data('reviewUrl');
    $.ajax({
        url: reviewUrl,
        method: 'POST',
        data: {
            action: status
        }
    })
        .done(function() {
            $('#successful-review-modal')
                .modal()
                .on('hidden.bs.modal', function() {
                    window.location.reload(true);
                });
        })
        .fail(function(jqXHR, textStatus, errorThrown) {
            displayMessage(
                'error',
                'Unable to save your review: ' +
                    buildErrorMessage(jqXHR, textStatus, errorThrown),
                'transcription-review-result'
            );
        });
}

$('#accept-transcription-button')
    .removeAttr('disabled')
    .on('click', function(evt) {
        evt.preventDefault();
        submitReview('accept');
    });

$('#reject-transcription-button')
    .removeAttr('disabled')
    .on('click', function(evt) {
        evt.preventDefault();
        submitReview('reject');
    });

var $tagEditor = $('#tag-editor'),
    $currentTagList = $tagEditor.find('#current-tags'),
    $newTagInput = $('#new-tag-input');

function addNewTag() {
    if (!$newTagInput.get(0).checkValidity()) {
        $newTagInput.closest('form').addClass('was-validated');
        return;
    }

    var val = $.trim($newTagInput.val());
    if (val) {
        // Prevent adding tags which are already present:
        var dupeCount = $currentTagList
            .find('input[name="tags"]')
            .filter(function(idx, input) {
                return (
                    input.value.toLocaleLowerCase() == val.toLocaleLowerCase()
                );
            }).length;

        if (!dupeCount) {
            var $newTag = $tagEditor
                .find('#tag-template')
                .clone()
                .removeAttr('id')
                .removeAttr('hidden');
            $newTag
                .find('input')
                .removeAttr('disabled')
                .val(val);
            $newTag.find('label').append(document.createTextNode(val));
            $currentTagList.append($newTag);
        }
        $newTagInput.val('');
    }
}

$tagEditor.find('#new-tag-button').on('click', addNewTag);
$newTagInput.on('change', addNewTag);
$newTagInput.on('keydown', function(evt) {
    // See https://github.com/LibraryOfCongress/concordia/issues/159 for the source of these values:
    if (evt.which == '13') {
        // Enter key
        evt.preventDefault();
        addNewTag();
    } else if (evt.which == '188') {
        // Comma
        evt.preventDefault();
        addNewTag();
    }
});

$currentTagList.on('click', '.close', function() {
    $(this)
        .parents('li')
        .remove();
});

$tagEditor
    .on('form-submit-success', function() {
        unlockControls($tagEditor);
        displayMessage('info', 'Your tags have been saved', 'tags-save-result');
    })
    .on('form-submit-failure', function(evt, info) {
        unlockControls($tagEditor);

        var message = 'Unable to save your tags';
        var jqXHR = info.jqXHR;
        if (jqXHR.responseJSON) {
            var error = jqXHR.responseJSON.error;
            if (error) {
                message += ': ' + ('join' in error ? error.join(' ') : error);
            }
        }

        displayMessage('error', message, 'tags-save-result');
    });
