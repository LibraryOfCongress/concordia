import React from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';

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
