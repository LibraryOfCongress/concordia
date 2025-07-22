import React from 'react';

export default function EditorButtonRedo({redoAvailable}) {
    return (
        <button
            className="btn btn-outline-primary mx-1 mb-2"
            disabled={!redoAvailable}
            title="Redo not yet implemented"
        >
            Redo <span className="fas fa-redo"></span>
        </button>
    );
}
