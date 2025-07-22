import React from 'react';

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
