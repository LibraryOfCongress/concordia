import React from 'react';

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
