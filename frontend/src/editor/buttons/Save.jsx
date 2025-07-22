import React from 'react';

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
