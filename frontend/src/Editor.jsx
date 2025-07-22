import React, {useState} from 'react';

async function submitTranscription(transcriptionId) {
    const response = await fetch(
        `/api/transcriptions/${transcriptionId}/submit`,
        {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
        },
    );

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to submit transcription');
    }

    return await response.json();
}

async function reviewTranscription(transcriptionId, action) {
    const response = await fetch(
        `/api/transcriptions/${transcriptionId}/review`,
        {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action}),
        },
    );

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to review transcription');
    }

    return await response.json();
}

async function acceptTranscription(transcriptionId) {
    return await reviewTranscription(transcriptionId, 'accept');
}

async function rejectTranscription(transcriptionId) {
    return await reviewTranscription(transcriptionId, 'reject');
}

export default function Editor({
    assetId,
    transcription,
    transcriptionStatus,
    registeredContributors,
    undoAvailable,
    redoAvailable,
    onTranscriptionUpdate,
}) {
    const [text, setText] = useState(transcription?.text || '');
    const [isSaving, setIsSaving] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isReviewing, setIsReviewing] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(false);
    const [submitSuccess, setSubmitSuccess] = useState(false);

    const status = transcriptionStatus;
    const isEditable = ['not_started', 'in_progress'].includes(status);
    const submitVisible = ['not_started', 'in_progress'].includes(status);
    const submitEnabled = status === 'in_progress' && transcription?.id;
    const inReview = status === 'submitted';
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
                    headers: {'Content-Type': 'application/json'},
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

            const updated = await response.json();
            setSuccess(true);
            if (onTranscriptionUpdate) onTranscriptionUpdate(updated);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsSaving(false);
        }
    };

    const handleSubmit = async () => {
        if (!transcription?.id) return;
        setIsSubmitting(true);
        setError(null);
        setSubmitSuccess(false);

        try {
            const updated = await submitTranscription(transcription.id);
            setSubmitSuccess(true);
            if (onTranscriptionUpdate) onTranscriptionUpdate(updated);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleAccept = async () => {
        if (!transcription?.id) return;
        setIsReviewing(true);
        setError(null);

        try {
            const updated = await acceptTranscription(transcription.id);
            if (onTranscriptionUpdate) onTranscriptionUpdate(updated);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsReviewing(false);
        }
    };

    const handleReject = async () => {
        if (!transcription?.id) return;
        setIsReviewing(true);
        setError(null);

        try {
            const updated = await rejectTranscription(transcription.id);
            if (onTranscriptionUpdate) onTranscriptionUpdate(updated);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsReviewing(false);
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
                <h2>{statusMap[status] || 'Unknown status'}</h2>
                {status !== 'not_started' && (
                    <h2>
                        Registered Contributors:{' '}
                        <span className="fw-normal">
                            {registeredContributors}
                        </span>
                    </h2>
                )}
                <p>{instructionsMap[status]}</p>
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
            {submitSuccess && (
                <div className="text-success">Transcription submitted.</div>
            )}

            {(isEditable || submitVisible || inReview) && (
                <div className="d-flex justify-content-center mt-3 flex-wrap">
                    {isEditable && (
                        <>
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
                        </>
                    )}
                    {submitVisible && (
                        <button
                            className="btn btn-primary mx-1 mb-2"
                            onClick={handleSubmit}
                            disabled={!submitEnabled || isSubmitting}
                            title="Request another volunteer to review the text you entered above"
                        >
                            {isSubmitting ? 'Submitting…' : 'Submit for Review'}
                        </button>
                    )}
                    {inReview && (
                        <>
                            <button
                                className="btn btn-primary mx-1 mb-2"
                                onClick={handleReject}
                                disabled={isReviewing}
                                title="Correct errors you see in the text"
                            >
                                Edit
                            </button>
                            <button
                                className="btn btn-primary mx-1 mb-2"
                                onClick={handleAccept}
                                disabled={isReviewing}
                                title="Confirm that the text is accurately transcribed"
                            >
                                Accept
                            </button>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
