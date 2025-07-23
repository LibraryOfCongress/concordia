import React from 'react';

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
