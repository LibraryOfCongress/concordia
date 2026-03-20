import React from 'react';
import EditorButtonSave from './Save';
import EditorButtonUndo from './Undo';
import EditorButtonRedo from './Redo';

/**
 * Button cluster for editable transcription state.
 *
 * Renders Save, Undo and Redo controls. Each child button receives only
 * the props it needs. This component does not manage any state.
 *
 * @param {Object} props
 * @param {boolean} props.isSaving
 *   True while a save request is in flight.
 * @param {string} props.text
 *   Current transcription text to validate save availability.
 * @param {boolean} props.undoAvailable
 *   True when an undo operation is possible.
 * @param {boolean} props.redoAvailable
 *   True when a redo operation is possible.
 * @param {() => void} props.onSave
 *   Called when the Save button is clicked.
 * @param {() => void} props.onUndo
 *   Called when the Undo button is clicked.
 * @param {() => void} props.onRedo
 *   Called when the Redo button is clicked.
 */
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
