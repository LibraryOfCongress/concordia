import React, {useState} from 'react';

export default function Editor({
    assetId,
    transcription,
    transcriptionStatus,
    undoAvailable,
    redoAvailable,
}) {
    const [text, setText] = useState(transcription?.text || '');
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);

    const isEditable = ['not_started', 'in_progress'].includes(
        transcriptionStatus,
    );
    const supersedes = transcription?.id;

    const handleSave = async () => {
        setIsSaving(true);
        setError(null);
        setSuccess(false);

        try {
            const response = await fetch(
                `/api/assets/${assetId}/transcriptions`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        text,
                        ...(supersedes ? {supersedes} : {}),
                    }),
                },
            );

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.error || response.statusText);
            }

            await response.json(); // Don't need data right now
            setSuccess(true);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsSaving(false);
        }
    };

    const statusMap = {
        submitted: 'Needs review',
        completed: 'Completed',
        not_started: 'Not started',
        in_progress: 'In progress',
    };

    const instructionsMap = {
        not_started: 'Transcribe this page.',
        in_progress: 'Someone started this transcription. Can you finish it?',
        submitted: 'Check this transcription thoroughly. Accept if correct!',
        completed: 'This transcription is finished! You can read and add tags.',
    };

    return (
        <div className="editor p-3 d-flex flex-column flex-grow-1">
            <div className="mb-2">
                <h2>{statusMap[transcriptionStatus] || 'Unknown status'}</h2>
                <p>{instructionsMap[transcriptionStatus]}</p>
            </div>

            <textarea
                className="form-control flex-grow-1 mb-3"
                value={text}
                onChange={(e) => setText(e.target.value)}
                readOnly={!isEditable}
                placeholder={
                    isEditable
                        ? 'Go ahead, start typing. You got this!'
                        : 'Nothing to transcribe'
                }
                aria-label="Transcription input"
                style={{minHeight: '200px'}}
            />

            {error && <div className="text-danger">Error: {error}</div>}
            {success && (
                <div className="text-success">Transcription saved.</div>
            )}

            {isEditable && (
                <div className="d-flex justify-content-center mt-3 flex-wrap">
                    <button
                        className="btn btn-primary mx-1 mb-2"
                        onClick={handleSave}
                        disabled={isSaving || !text.trim()}
                    >
                        Save
                    </button>
                    <button
                        className="btn btn-outline-primary mx-1 mb-2"
                        disabled={!undoAvailable}
                        title="Undo not yet implemented"
                    >
                        <span className="fas fa-undo"></span> Undo
                    </button>
                    <button
                        className="btn btn-outline-primary mx-1 mb-2"
                        disabled={!redoAvailable}
                        title="Redo not yet implemented"
                    >
                        Redo <span className="fas fa-redo"></span>
                    </button>
                </div>
            )}
        </div>
    );
}
