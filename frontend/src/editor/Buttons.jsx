import React from 'react';
import EditableButtons from './buttons/Editable';
import SubmitButton from './buttons/Submit';
import ReviewButton from './buttons/Review';

/**
 * Render the editor button row.
 *
 * Shows:
 * - <EditableButtons> when `isEditable` is true
 * - <SubmitButton> when `submitVisible` is true
 * - <ReviewButton> when `inReview` is true
 *
 * If none of the sections are visible, the component returns null.
 *
 * Layout: a centered flex container with wrap to handle narrow viewports.
 *
 * @param {Object} props
 * @param {boolean} props.isEditable
 *   Whether the draft editing controls should be shown.
 * @param {boolean} props.submitVisible
 *   Whether the submit control should be shown.
 * @param {boolean} props.inReview
 *   Whether accept and reject controls should be shown.
 * @param {boolean} props.undoAvailable
 *   Whether undo is available for the current asset.
 * @param {boolean} props.redoAvailable
 *   Whether redo is available for the current asset.
 * @param {string} props.text
 *   Current transcription text, passed to <EditableButtons>.
 * @param {boolean} props.isSaving
 *   True while a save is in flight.
 * @param {boolean} props.isSubmitting
 *   True while a submit is in flight.
 * @param {boolean} props.isReviewing
 *   True while a review action is in flight.
 * @param {boolean} props.submitEnabled
 *   Whether the submit button should be enabled.
 * @param {() => void} props.onSave
 *   Handler for saving a draft transcription.
 * @param {() => void} props.onSubmit
 *   Handler for submitting a transcription for review.
 * @param {() => void} props.onAccept
 *   Handler for accepting a submitted transcription.
 * @param {() => void} props.onReject
 *   Handler for rejecting a submitted transcription.
 * @param {() => void} props.onUndo
 *   Handler to trigger an undo action.
 * @param {() => void} props.onRedo
 *   Handler to trigger a redo action.
 */
export default function EditorButtons({
    isEditable,
    submitVisible,
    inReview,
    undoAvailable,
    redoAvailable,
    text,
    isSaving,
    isSubmitting,
    isReviewing,
    submitEnabled,
    onSave,
    onSubmit,
    onAccept,
    onReject,
    onUndo,
    onRedo,
}) {
    if (!isEditable && !submitVisible && !inReview) return null;

    return (
        <div className="d-flex justify-content-center mt-3 flex-wrap">
            {isEditable && (
                <EditableButtons
                    onSave={onSave}
                    isSaving={isSaving}
                    text={text}
                    undoAvailable={undoAvailable}
                    redoAvailable={redoAvailable}
                    onUndo={onUndo}
                    onRedo={onRedo}
                />
            )}
            {submitVisible && (
                <SubmitButton
                    onSubmit={onSubmit}
                    isSubmitting={isSubmitting}
                    submitEnabled={submitEnabled}
                />
            )}
            {inReview && (
                <ReviewButton
                    onAccept={onAccept}
                    onReject={onReject}
                    isReviewing={isReviewing}
                />
            )}
        </div>
    );
}
