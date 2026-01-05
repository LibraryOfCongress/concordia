import React from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';

/**
 * Confirmation modal shown before running OCR that would replace the current
 * transcription text with machine generated text.
 *
 * Behavior:
 * - Appears when `show` is true. Hides when the backdrop or close button is
 *   activated or when `onClose` is called.
 * - Clicking "Yes, Select Language" calls `onConfirm`, which should advance to
 *   language selection and OCR.
 * - Uses react-bootstrap Modal. Ensure Bootstrap's JS bundle is loaded.
 *
 * Accessibility:
 * - Modal is centered and managed by react-bootstrap which handles focus trap
 *   and aria attributes.
 *
 * Design note:
 * - The potential destructive action is on a link styled as a button for visual
 *   prominence while "Cancel" is a primary button.
 *
 * @param {Object} props
 * @param {boolean} props.show - Whether the modal is visible.
 * @param {() => void} props.onClose - Called when the user cancels or closes.
 * @param {() => void} props.onConfirm - Called to proceed to OCR language select.
 * @returns {JSX.Element}
 */
export default function OcrConfirmModal({show, onClose, onConfirm}) {
    return (
        <Modal show={show} onHide={onClose} centered>
            <Modal.Header closeButton />
            <Modal.Body>
                <div className="bg-light p-3">
                    <h5 className="modal-title mb-3">Are you sure?</h5>
                    <p>
                        Clicking "Transcribe with OCR" will remove all existing
                        transcription text and replace it with automatically
                        generated text. Use the "Undo" button to restore
                        previous text.
                    </p>
                </div>
            </Modal.Body>
            <Modal.Footer>
                <Button variant="primary" onClick={onClose}>
                    Cancel
                </Button>
                <Button
                    variant="link"
                    className="underline-link fw-bold"
                    onClick={onConfirm}
                >
                    Yes, Select Language
                </Button>
            </Modal.Footer>
        </Modal>
    );
}
