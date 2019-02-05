/* global $ displayMessage buildErrorMessage Raven */

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

$(document).on('keydown', function(evt) {
    /*
        Global keyboard event handlers

        * F1 and ? open help
        * Control-I focuses on the image viewer
        * Control-T focuses on the transcription text field

        n.b. jQuery interferes with setting the focus so our handlers use the
        DOM directly
    */

    if (
        (evt.which == 112 || evt.which == 191) &&
        !evt.target.tagName.match(/(INPUT|TEXTAREA)/i)
    ) {
        // Either the F1 or ? keys were pressed outside of a text field so we'll show help:
        $('#keyboard-help-modal').modal('show');
        return false;
    } else if (evt.which == 73 && evt.ctrlKey) {
        // Control-I == switch to the image viewer
        document.querySelector('#asset-image .openseadragon-canvas').focus();
        return false;
    } else if (evt.which == 84 && evt.ctrlKey) {
        // Control-T == switch to the transcription field
        document.getElementById('transcription-input').focus();
        return false;
    }
});

var $captchaModal = $('#captcha-modal');
var $captchaForm = $captchaModal.find('form').on('submit', function(evt) {
    evt.preventDefault();

    var formData = $captchaForm.serializeArray();

    $.ajax({
        url: $captchaForm.attr('action'),
        method: 'POST',
        dataType: 'json',
        data: $.param(formData)
    })
        .done(function() {
            $captchaModal.modal('hide');
        })
        .fail(function(jqXHR) {
            if (jqXHR.status == 401) {
                $captchaModal.find('[name=key]').val(jqXHR.responseJSON.key);
                $captchaModal
                    .find('#captcha-image')
                    .attr('src', jqXHR.responseJSON.image);
            }
        });
});

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
            dataType: 'json',
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
                if (jqXHR.status == 401) {
                    $captchaModal
                        .find('[name=key]')
                        .val(jqXHR.responseJSON.key);
                    $captchaModal
                        .find('#captcha-image')
                        .attr('src', jqXHR.responseJSON.image);
                    $captchaModal.modal();
                }
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
        if (this.checked) {
            if ($textarea.val()) {
                if (
                    confirm(
                        'You currently have entered text which will not be saved because “Nothing to transcribe” is checked. Do you want to discard that text?'
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

        if (
            !data.hasReservation ||
            (data.transcriptionStatus != 'in_progress' &&
                data.transcriptionStatus != 'not_started')
        ) {
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

        if (
            !data.hasReservation &&
            (data.transcriptionStatus == 'in_progress' ||
                data.transcriptionStatus == 'not_started')
        ) {
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
        method: 'POST',
        dataType: 'json'
    })
        .done(function() {
            $('.tx-status-display')
                .children()
                .attr('hidden', 'hidden')
                .filter('.tx-submitted')
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
        dataType: 'json',
        data: {
            action: status
        }
    })
        .done(function() {
            if (status == 'reject') {
                window.location.reload(true);
            } else {
                $('#review-accepted-modal')
                    .modal()
                    .on('hidden.bs.modal', function() {
                        window.location.reload(true);
                    });
            }
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

        var message = 'Unable to save your tags: ';
        message += buildErrorMessage(
            info.jqXHR,
            info.textStatus,
            info.errorThrown
        );

        displayMessage('error', message, 'tags-save-result');
    });

var hideTooltipCallback = function() {
    // wait a couple seconds and then hide the tooltip.
    var hideTooltip = function(tooltipButton) {
        return function() {
            tooltipButton.tooltip('hide');
        };
    };
    setTimeout(hideTooltip($(this)), 3000);
};
var $copyUrlButton = $('#copy-url-button');
$copyUrlButton.on('click', function() {
    var $currentAssetUrl = $('#currentAssetUrl');
    $currentAssetUrl.removeClass('d-none');
    var currentAssetUrl = document.getElementById('currentAssetUrl');
    currentAssetUrl.select();
    var tooltipMessage = '';
    try {
        document.execCommand('copy');
        // Show the tooltip with a success message
        tooltipMessage = 'This link has been copied to your clipboard';
        $currentAssetUrl.addClass('d-none');
        $copyUrlButton
            .tooltip('dispose')
            .tooltip({title: tooltipMessage})
            .tooltip('show')
            .on('shown.bs.tooltip', hideTooltipCallback);
    } catch (e) {
        if (typeof Raven != 'undefined') {
            Raven.captureException(e);
        }
        // Display an error message in the tooltip
        tooltipMessage =
            '<p>Could not access your clipboard.</p><button class="btn btn-light btn-sm" id="dismiss-tooltip-button">Close</button>';
        $currentAssetUrl.addClass('d-none');
        $copyUrlButton
            .tooltip('dispose')
            .tooltip({title: tooltipMessage, html: true})
            .tooltip('show');
        $('#dismiss-tooltip-button').on('click', function() {
            $copyUrlButton.tooltip('hide');
        });
    }
});
