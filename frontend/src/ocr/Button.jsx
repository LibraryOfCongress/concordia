import React from 'react';
import Button from 'react-bootstrap/Button';

/**
 * OCR action UI: a help link that opens the OCR help modal
 * and a primary button that starts OCR transcription.
 *
 * Notes:
 * - The help link triggers the Bootstrap modal with id "#ocr-help-modal"
 *   via data attributes. Ensure that modal exists in the DOM.
 * - Requires Bootstrap's modal JavaScript to be loaded.
 *
 * @param {Object} props
 * @param {() => void} props.onClick - Handler to begin the OCR flow.
 * @returns {JSX.Element}
 */
export default function OcrButton({onClick}) {
    return (
        <div className="d-flex flex-row align-items-center justify-content-end mt-1">
            <a
                tabIndex={0}
                className="btn btn-link d-inline p-0"
                role="button"
                data-bs-placement="top"
                data-bs-trigger="focus click hover"
                title="When to use OCR"
                data-bs-toggle="modal"
                data-bs-target="#ocr-help-modal"
            >
                <span className="underline-link fw-bold">What is OCR</span>{' '}
                <span
                    className="fas fa-question-circle"
                    aria-label="When to use OCR"
                ></span>
            </a>
            <Button className="mx-1" variant="primary" onClick={onClick}>
                Transcribe with OCR
            </Button>
        </div>
    );
}
