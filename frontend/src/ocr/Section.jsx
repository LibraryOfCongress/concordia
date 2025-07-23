import React from 'react';

import OcrHandler from './Handler';

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
