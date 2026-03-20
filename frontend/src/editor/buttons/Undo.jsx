import React from 'react';

/**
 * Undo button for the transcription editor.
 *
 * Renders an outline button that calls `onClick`. The button is disabled
 * when `undoAvailable` is false.
 *
 * @param {Object} props
 * @param {boolean} props.undoAvailable - True if a prior version exists to undo to.
 * @param {() => void} props.onClick - Click handler to perform the undo action.
 * @returns {JSX.Element}
 */
export default function EditorButtonUndo({undoAvailable, onClick}) {
    return (
        <button
            className="btn btn-outline-primary mx-1 mb-2"
            disabled={!undoAvailable}
            onClick={onClick}
        >
            <span className="fas fa-undo"></span> Undo
        </button>
    );
}
