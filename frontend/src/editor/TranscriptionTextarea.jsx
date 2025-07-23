import React from 'react';

export default function TranscriptionTextarea({value, onChange, editable}) {
    return (
        <textarea
            className="form-control flex-grow-1 mb-3"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            readOnly={!editable}
            placeholder={
                editable
                    ? 'Go ahead, start typing. You got this!'
                    : 'Nothing to transcribe'
            }
            aria-label="Transcription input"
            style={{minHeight: '200px'}}
        />
    );
}
