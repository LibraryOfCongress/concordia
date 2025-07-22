import React from 'react';
import EditableButtons from './buttons/Editable';
import SubmitButton from './buttons/Submit';
import ReviewButton from './buttons/Review';

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
