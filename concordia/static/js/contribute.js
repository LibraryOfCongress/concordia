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

    $form.on('click', '[type=submit]', function(evt) {
        $form.data('submit-name', evt.target.name);
        $form.data('submit-value', evt.target.value);
    });

    $form.on('submit', function(evt) {
        evt.preventDefault();

        lockControls($form);

        var formData = $form.serializeArray();

        var submitName = $form.data('submit-name'),
            submitValue = $form.data('submit-value');
        if (submitName) {
            formData.push({name: submitName, value: submitValue});
        }

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
                unlockControls($form);

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

var $transcriptionEditor = $('#transcription-editor')
    .on('form-submit-success', function(evt, extra) {
        var status = extra.responseData.status;
        if (status == 'Edit') {
            unlockControls(extra.$form);
            displayMessage(
                'info',
                "Successfully saved your work. Submit it for review when you're done",
                'transcription-save-result'
            );
        } else if (status == 'Submitted') {
            displayMessage(
                'info',
                'Successfully submitted your work for review. After you are done tagging, go to the next page',
                'transcription-save-result'
            );
        } else {
            displayMessage(
                'info',
                'Submit successful. Implement the next stage for ' +
                    status +
                    '!',
                'transcription-save-result'
            );
        }
    })
    .on('form-submit-failure', function(evt, info) {
        displayMessage(
            'error',
            'Unable to save your work: ' + info.textStatus + info.errorThrown,
            'transcription-save-result'
        );
    });

$transcriptionEditor
    .find('textarea')
    .each(function(idx, textarea) {
        textarea.value = $.trim(textarea.value);
    })
    .on('change input', function() {
        var $submitButtons = $transcriptionEditor.find('[type="submit"]');
        if (!this.value) {
            $submitButtons.attr('disabled', 'disabled');
        } else {
            $submitButtons.removeAttr('disabled');
        }
    })
    .trigger('change');

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
    if (evt.which == '13') {
        // Enter key
        evt.preventDefault();
        addNewTag();
    } else if (evt.which == '32') {
        // Spacebar
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
