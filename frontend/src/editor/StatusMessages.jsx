import React from 'react';

/**
 * Status message area for the React transcription editor.
 *
 * Displays inline feedback for error, save success and submit success.
 * This module is part of the transcription UI and is in flux as the app
 * evolves.
 *
 * @param {Object} props
 * @param {string|null} props.error
 *   Error message to display. When truthy shows "Error: <message>".
 * @param {boolean} props.success
 *   When true shows "Transcription saved."
 * @param {boolean} props.submitSuccess
 *   When true shows "Transcription submitted."
 */
export default function EditorStatusMessages({error, success, submitSuccess}) {
    return (
        <>
            {error && <div className="text-danger">Error: {error}</div>}
            {success && (
                <div className="text-success">Transcription saved.</div>
            )}
            {submitSuccess && (
                <div className="text-success">Transcription submitted.</div>
            )}
        </>
    );
}
