import React, {useState} from 'react';

import OcrButton from './Button';
import OcrConfirmModal from './ConfirmModal';
import OcrLanguageModal from './LanguageModal';
import OcrHelpModal from './HelpModal';

/**
 * Orchestrates the OCR flow for the transcription editor.
 *
 * Flow:
 * 1) User clicks "Transcribe with OCR" button which opens a confirm modal.
 * 2) Confirm opens a language selection modal.
 * 3) Submit posts to `/api/assets/{assetId}/transcriptions/ocr` with
 *    `{language, supersedes}` then calls `onTranscriptionUpdate` with
 *    the server response.
 *
 * State:
 * - showConfirm: controls the confirm modal.
 * - showLanguage: controls the language modal.
 * - selectedLang: ISO 639-3 code, defaults to "eng".
 * - isSubmitting: disables inputs during the request.
 * - error: displays server or network errors in the language modal.
 *
 * Notes:
 * - OCR replaces existing text.
 * - Expects the API to return a TranscriptionOut payload with an `asset`
 *   object used to refresh editor state.
 *
 * Accessibility:
 * - Modals come from react-bootstrap which handles focus and aria attributes.
 *
 * @param {Object} props
 * @param {number} props.assetId - Asset primary key for API calls.
 * @param {Object|null} props.transcription - Current transcription or null.
 * @param {Array<[string,string]>} props.languages - OCR languages as
 *   `[code, label]`.
 * @param {(updated: Object) => void} props.onTranscriptionUpdate - Called with
 *   the API response after a successful OCR request.
 * @returns {JSX.Element}
 */
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
