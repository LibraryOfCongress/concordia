import React from 'react';

export default function EditorButtonUndo({disabled, onClick}) {
    return (
        <button
            className="btn btn-outline-primary mx-1 mb-2"
            disabled={disabled}
            onClick={onClick}
            title="Undo not yet implemented"
        >
            <span className="fas fa-undo"></span> Undo
        </button>
    );
}
