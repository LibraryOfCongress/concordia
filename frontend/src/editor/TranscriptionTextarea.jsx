import React from 'react';

/**
 * Multiline textarea for transcription input.
 *
 * Renders a Bootstrap styled `<textarea>` bound to `value`, `onChange` and
 * an `editable` flag. When `editable` is false the field is readOnly and a
 * non editing placeholder is shown.
 *
 * @param {Object} props
 * @param {string} props.value
 *   Current transcription text.
 * @param {(value: string) => void} props.onChange
 *   Callback invoked with the updated text.
 * @param {boolean} props.editable
 *   When true the textarea is editable, otherwise it is readOnly.
 */
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
