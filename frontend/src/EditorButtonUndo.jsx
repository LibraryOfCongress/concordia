import React from 'react';

export default function EditorButtonUndo({undoAvailable, onClick}) {
    return (
        <button
            className="btn btn-outline-primary mx-1 mb-2"
            disabled={!undoAvailable}
            onClick={onClick}
            title="Undo not yet implemented"
        >
            <span className="fas fa-undo"></span> Undo
        </button>
    );
}
