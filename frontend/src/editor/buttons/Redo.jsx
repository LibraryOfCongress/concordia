import React from 'react';

/**
 * Redo button for the transcription editor.
 *
 * Presentational only. Disabled when no redo is available.
 *
 * @param {Object} props
 * @param {boolean} props.redoAvailable
 *   True when a redo operation can be performed.
 * @param {() => void} props.onClick
 *   Click handler invoked to trigger redo.
 */
export default function EditorButtonRedo({redoAvailable, onClick}) {
    return (
        <button
            className="btn btn-outline-primary mx-1 mb-2"
            disabled={!redoAvailable}
            onClick={onClick}
        >
            Redo <span className="fas fa-redo"></span>
        </button>
    );
}
