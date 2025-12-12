import 'bootstrap/dist/css/bootstrap.min.css';
import {Modal} from 'bootstrap';

function selectLanguage() {
    const ocrModalElement = document.getElementById('ocr-transcription-modal');
    const langModalElement = document.getElementById(
        'language-selection-modal',
    );

    const ocrModal = Modal.getOrCreateInstance(ocrModalElement);
    const langModal = Modal.getOrCreateInstance(langModalElement);

    ocrModal.hide();
    langModal.show();
}

document
    .getElementById('select-language-button')
    .addEventListener('click', selectLanguage);

export {selectLanguage};
