import React, {useState} from 'react';

import OcrButton from './Button';
import OcrConfirmModal from './ConfirmModal';
import OcrLanguageModal from './LanguageModal';
import OcrHelpModal from './HelpModal';

export default function OcrHandler({
    assetId,
    transcription,
    languages,
    onTranscriptionUpdate,
}) {
    const [showConfirm, setShowConfirm] = useState(false);
    const [showLanguage, setShowLanguage] = useState(false);
    const [selectedLang, setSelectedLang] = useState('eng');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState(null);

    const handleOcrClick = () => {
        setShowConfirm(true);
    };

    const handleConfirm = () => {
        setShowConfirm(false);
        setShowLanguage(true);
    };

    const handleCancelLanguage = () => {
        setShowLanguage(false);
        setSelectedLang('eng');
    };

    const handleLanguageChange = (lang) => {
        setSelectedLang(lang);
    };

    const handleLanguageSubmit = async () => {
        setIsSubmitting(true);
        setError(null);
        try {
            const response = await fetch(
                `/api/assets/${assetId}/transcriptions/ocr`,
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        language: selectedLang,
                        supersedes: transcription?.id || null,
                    }),
                },
            );

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || data.error || 'OCR failed');
            }

            const updated = await response.json();
            setShowLanguage(false);
            if (onTranscriptionUpdate) onTranscriptionUpdate(updated);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <>
            <OcrHelpModal />
            <OcrButton onClick={handleOcrClick} />
            <OcrConfirmModal
                show={showConfirm}
                onClose={() => setShowConfirm(false)}
                onConfirm={handleConfirm}
            />
            <OcrLanguageModal
                show={showLanguage}
                selectedLang={selectedLang}
                onChange={handleLanguageChange}
                onClose={handleCancelLanguage}
                onSubmit={handleLanguageSubmit}
                disabled={isSubmitting}
                error={error}
                languages={languages}
            />
        </>
    );
}
