import React from 'react';

/**
 * Save button for the transcription editor.
 *
 * Renders a primary button that calls `onSave`. The button is disabled while a
 * save is in progress or when the current text is empty after trimming.
 *
 * @param {Object} props
 * @param {() => void} props.onSave - Click handler to persist the draft.
 * @param {boolean} props.isSaving - True while a save request is in flight.
 * @param {string} props.text - Current transcription text used to gate enable state.
 * @returns {JSX.Element}
 */
export default function EditorButtonSave({onSave, isSaving, text}) {
    return (
        <button
            className="btn btn-primary mx-1 mb-2"
            onClick={onSave}
            disabled={isSaving || !text.trim()}
        >
            Save
        </button>
    );
}
