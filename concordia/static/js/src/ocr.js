import $ from 'jquery';

function selectLanguage() {
    $('#ocr-transcription-modal').modal('hide');
    $('#language-selection-modal').modal('show');
}

$('#select-language-button').on('click', selectLanguage);

export {selectLanguage};
