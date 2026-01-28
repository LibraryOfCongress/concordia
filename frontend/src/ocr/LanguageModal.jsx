import React, {useState} from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';

/**
 * Language picker modal for OCR.
 *
 * Behavior:
 * - Presents a scrollable list of languages from `languages`.
 * - Calls `onSubmit({ language, supersedes })` when the user confirms.
 *
 * Accessibility:
 * - Uses react-bootstrap Modal roles. The select has an associated label.
 *
 * Props:
 * @param {boolean} show
 *   Whether the modal is visible.
 * @param {function} onClose
 *   Called to dismiss the modal.
 * @param {function} onSubmit
 *   Called on confirmation. Receives `{ language, supersedes }`.
 * @param {Array<[string,string]>} languages
 *   Array of `[code, label]` tuples, e.g. `[["eng","English"], ...]`.
 * @param {string} [supersedes]
 *   Transcription id that the OCR result will supersede.
 * @param {string} [selectedLang]
 *   Controlled selected language code.
 * @param {function} [onChange]
 *   Controlled change handler: `onChange(code)`.
 * @param {boolean} [disabled]
 *   Disable the confirm button while submitting.
 * @param {string|null} [error]
 *   Optional error message to display.
 *
 * Usage:
 * <OcrLanguageModal
 *   show={show}
 *   languages={languages}
 *   selectedLang={selectedLang}
 *   onChange={setSelectedLang}
 *   onClose={handleClose}
 *   onSubmit={handleSubmit}
 *   disabled={isSubmitting}
 *   error={error}
 * />
 */
export default function OcrLanguageModal({
    show,
    onClose,
    onSubmit,
    languages,
    supersedes,
    selectedLang,
    onChange,
    disabled = false,
    error = null,
}) {
    // Uncontrolled fallback state
    const [localLang, setLocalLang] = useState(() => {
        const eng = languages.find(([code]) => code === 'eng')?.[0];
        return eng || languages[0]?.[0] || '';
    });

    const isControlled =
        typeof selectedLang === 'string' && typeof onChange === 'function';
    const value = isControlled ? selectedLang : localLang;

    const handleChange = (e) => {
        const code = e.target.value;
        if (isControlled) {
            onChange(code);
        } else {
            setLocalLang(code);
        }
    };

    const handleSubmit = () => {
        if (!value) return;
        onSubmit({language: value, supersedes});
    };

    return (
        <Modal show={show} onHide={onClose} centered>
            <Modal.Header closeButton />
            <Modal.Body>
                <div className="bg-light p-3">
                    <h5 className="modal-title mb-3">Select language</h5>
                    <p>
                        Select the language of the transcription from the list
                        below.
                    </p>

                    {error && (
                        <div className="alert alert-danger" role="alert">
                            {error}
                        </div>
                    )}

                    <div className="text-center pb-1">
                        <label htmlFor="language" className="form-label">
                            Language
                        </label>
                        <select
                            id="language"
                            name="language"
                            size={7}
                            className="form-select"
                            value={value}
                            onChange={handleChange}
                            aria-label="Select OCR language"
                        >
                            {languages.map(([code, label]) => (
                                <option key={code} value={code}>
                                    {label}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>
            </Modal.Body>
            <Modal.Footer>
                <Button variant="primary" onClick={onClose}>
                    Cancel
                </Button>
                <Button
                    className="underline-link fw-bold"
                    variant="link"
                    disabled={!value || disabled}
                    onClick={handleSubmit}
                >
                    Replace Text
                </Button>
            </Modal.Footer>
        </Modal>
    );
}
