import React from 'react';

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
            {isSubmitting ? 'Submitting…' : 'Submit for Review'}
        </button>
    );
}
