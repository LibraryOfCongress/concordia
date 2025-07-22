import React from 'react';

export default function EditorButtonRedo({disabled}) {
    return (
        <button
            className="btn btn-outline-primary mx-1 mb-2"
            disabled={disabled}
            title="Redo not yet implemented"
        >
            Redo <span className="fas fa-redo"></span>
        </button>
    );
}
