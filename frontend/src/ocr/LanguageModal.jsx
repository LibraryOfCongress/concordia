import React, {useState} from 'react';
import Modal from 'react-bootstrap/Modal';
import Button from 'react-bootstrap/Button';

export default function OcrLanguageModal({
    show,
    onClose,
    onSubmit,
    languages,
    supersedes,
}) {
    const [selectedLanguage, setSelectedLanguage] = useState(
        languages.find(([code]) => code === 'eng')?.[0] ||
            languages[0]?.[0] ||
            '',
    );

    const handleChange = (e) => {
        setSelectedLanguage(e.target.value);
    };

    const handleSubmit = () => {
        if (selectedLanguage) {
            onSubmit({
                language: selectedLanguage,
                supersedes,
            });
        }
    };

    return (
        <Modal show={show} onHide={onClose} centered>
            <Modal.Header closeButton />
            <Modal.Body>
                <div className="bg-light p-3">
                    <h5 className="modal-title mb-3">Select language</h5>
                    <p>
                        Select the language the transcription is in from the
                        list below.
                    </p>
                    <div className="text-center pb-1">
                        <select
                            id="language"
                            name="language"
                            size={7}
                            className="form-select"
                            value={selectedLanguage}
                            onChange={handleChange}
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
                    disabled={!selectedLanguage}
                    onClick={handleSubmit}
                >
                    Replace Text
                </Button>
            </Modal.Footer>
        </Modal>
    );
}
