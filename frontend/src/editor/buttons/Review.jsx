import React from 'react';

/**
 * Review action buttons for the transcription editor.
 *
 * Renders two primary buttons:
 * - "Edit" triggers the reject flow so a reviewer can make changes
 * - "Accept" confirms the transcription is accurate
 *
 * @param {Object} props
 * @param {boolean} props.isReviewing
 *   True while a review API call is active which disables the buttons.
 * @param {() => void} props.onAccept
 *   Handler to accept the current transcription.
 * @param {() => void} props.onReject
 *   Handler to send the transcription back for edits.
 */
export default function EditorButtonsReview({isReviewing, onAccept, onReject}) {
    return (
        <>
            <button
                className="btn btn-primary mx-1 mb-2"
                onClick={onReject}
                disabled={isReviewing}
                title="Correct errors you see in the text"
            >
                Edit
            </button>
            <button
                className="btn btn-primary mx-1 mb-2"
                onClick={onAccept}
                disabled={isReviewing}
                title="Confirm that the text is accurately transcribed"
            >
                Accept
            </button>
        </>
    );
}
