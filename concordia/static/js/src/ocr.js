import 'bootstrap/dist/css/bootstrap.min.css';
import {Modal} from 'bootstrap';

document.addEventListener('DOMContentLoaded', function () {
    const link = document.getElementById('ocr-transcription-link');
    if (link) {
        if (link.dataset.authenticated === 'true') {
            // Enable the button
            link.classList.remove('disabled');
            link.removeAttribute('aria-disabled');
            link.removeAttribute('tabindex');

            link.dataset.bsToggle = 'modal';
            link.dataset.bsTarget = '#ocr-transcription-modal';
            link.setAttribute('title', 'Transcribe with OCR');
        } else {
            link.classList.add('disabled');
            link.setAttribute('aria-disabled', 'true');

            link.setAttribute(
                'href',
                '/accounts/login/?next=' +
                    encodeURIComponent(window.location.pathname),
            );
            link.setAttribute('title', 'Log in to use "Transcribe with OCR"');

            delete link.dataset.bsToggle;
            delete link.dataset.bsTarget;
        }
    }
});

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

const selectLanguageButton = document.getElementById('select-language-button');
if (selectLanguageButton) {
    selectLanguageButton.addEventListener('click', selectLanguage);
}

export {selectLanguage};
