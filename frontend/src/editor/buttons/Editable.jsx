import React from 'react';
import EditorButtonSave from './Save';
import EditorButtonUndo from './Undo';
import EditorButtonRedo from './Redo';

export default function EditorButtonsEditable({
    isSaving,
    text,
    undoAvailable,
    redoAvailable,
    onSave,
    onUndo,
    onRedo,
}) {
    return (
        <>
            <EditorButtonSave isSaving={isSaving} text={text} onSave={onSave} />
            <EditorButtonUndo undoAvailable={undoAvailable} onClick={onUndo} />
            <EditorButtonRedo redoAvailable={redoAvailable} onClick={onRedo} />
        </>
    );
}
