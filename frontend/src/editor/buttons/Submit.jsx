import React from 'react';

/**
 * Submit button for the transcription editor.
 *
 * Renders a primary button that calls `onSubmit`. The button is disabled
 * while a submit request is in flight or when submission is not allowed.
 *
 * @param {Object} props
 * @param {() => void} props.onSubmit - Click handler to submit the draft for review.
 * @param {boolean} props.isSubmitting - True while a submit request is in flight.
 * @param {boolean} props.submitEnabled - True when the current draft can be submitted.
 * @returns {JSX.Element}
 */
export default function EditorButtonSubmit({
    onSubmit,
    isSubmitting,
    submitEnabled,
}) {
    return (
        <button
            className="btn btn-primary mx-1 mb-2"
            onClick={onSubmit}
            disabled={!submitEnabled || isSubmitting}
            title="Request another volunteer to review the text you entered above"
        >
            {isSubmitting ? 'Submitting...' : 'Submit for Review'}
        </button>
    );
}
