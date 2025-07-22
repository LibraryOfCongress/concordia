import React from 'react';
import EditorButtonSave from './EditorButtonSave';
import EditorButtonUndo from './EditorButtonUndo';
import EditorButtonRedo from './EditorButtonRedo';

export default function EditorButtonsEditable({
    isSaving,
    text,
    undoAvailable,
    redoAvailable,
    onSave,
}) {
    return (
        <>
            <EditorButtonSave isSaving={isSaving} text={text} onSave={onSave} />
            <EditorButtonUndo undoAvailable={undoAvailable} />
            <EditorButtonRedo redoAvailable={redoAvailable} />
        </>
    );
}
