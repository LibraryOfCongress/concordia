/**
 * OCR section wrapper for the viewer column.
 *
 * Purpose:
 * - Hosts the OCR entrypoint UI.
 * - Forwards asset context and handlers to the OCR flow.
 *
 * Integration:
 * - Rendered by ViewerSplit alongside the image viewer.
 * - Delegates all OCR actions to OcrHandler.
 *
 * Usage:
 * <OcrSection
 *   assetId={asset.id}
 *   transcription={asset.transcription}
 *   onTranscriptionUpdate={handleTranscriptionUpdate}
 *   languages={asset.languages}
 * />
 */

import React from 'react';

import OcrHandler from './Handler';

/**
 * Lightweight container that places the OCR controls in the viewer column.
 *
 * Props:
 * @param {Object} props
 * @param {number} props.assetId
 *   The current asset id used by API calls.
 * @param {{ id?: number, text?: string } | null} props.transcription
 *   The current transcription object or null if none exists.
 * @param {function(Object):void} props.onTranscriptionUpdate
 *   Callback invoked with the API response after OCR creates a transcription.
 * @param {Array<[string,string]>} props.languages
 *   Array of [code, label] language tuples for OCR selection.
 *
 * Returns:
 * @returns {JSX.Element}
 */
export default function OcrSection({
    assetId,
    transcription,
    onTranscriptionUpdate,
    languages,
}) {
    return (
        <div id="ocr-section" className="row ps-3 pb-4 bg-white print-none">
            <div className="d-flex flex-row align-items-center justify-content-end mt-1">
                <OcrHandler
                    assetId={assetId}
                    transcription={transcription}
                    onTranscriptionUpdate={onTranscriptionUpdate}
                    languages={languages}
                />
            </div>
        </div>
    );
}
