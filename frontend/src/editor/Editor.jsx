import React from 'react';
import EditorHeader from './Header';
import TranscriptionTextarea from './TranscriptionTextarea';
import EditorStatusMessages from './StatusMessages';
import EditorButtons from './Buttons';

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

export default function Editor(props) {
    const {
        assetId,
        transcription,
        transcriptionStatus,
        registeredContributors,
        undoAvailable,
        redoAvailable,
        onTranscriptionUpdate,
        onTranscriptionTextChange,
    } = props;

    const [isSaving, setIsSaving] = React.useState(false);
    const [isSubmitting, setIsSubmitting] = React.useState(false);
    const [isReviewing, setIsReviewing] = React.useState(false);
    const [error, setError] = React.useState(null);
    const [success, setSuccess] = React.useState(false);
    const [submitSuccess, setSubmitSuccess] = React.useState(false);

    const status = transcriptionStatus;
    const isEditable = ['not_started', 'in_progress'].includes(status);
    const submitVisible = ['not_started', 'in_progress'].includes(status);
    const submitEnabled = status === 'in_progress' && transcription?.id;
    const inReview = status === 'submitted';
    const supersedes = transcription?.id;
    const text = transcription?.text || '';

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

    const handleUndo = async () => {
        setIsSaving(true);
        setError(null);
        try {
            const response = await fetch(
                `/api/assets/${assetId}/transcriptions/rollback`,
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                },
            );
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || data.error || 'Undo failed');
            }
            const updated = await response.json();
            if (onTranscriptionUpdate) onTranscriptionUpdate(updated);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsSaving(false);
        }
    };

    const handleRedo = async () => {
        setIsSaving(true);
        setError(null);
        try {
            const response = await fetch(
                `/api/assets/${assetId}/transcriptions/rollforward`,
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                },
            );
            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || data.error || 'Redo failed');
            }
            const updated = await response.json();
            if (onTranscriptionUpdate) onTranscriptionUpdate(updated);
        } catch (err) {
            setError(err.message);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="editor p-3 d-flex flex-column flex-grow-1">
            <EditorHeader
                status={status}
                registeredContributors={registeredContributors}
            />

            <TranscriptionTextarea
                value={text}
                onChange={onTranscriptionTextChange}
                editable={isEditable}
            />

            <EditorStatusMessages
                error={error}
                success={success}
                submitSuccess={submitSuccess}
            />

            <EditorButtons
                isEditable={isEditable}
                submitVisible={submitVisible}
                inReview={inReview}
                undoAvailable={undoAvailable}
                redoAvailable={redoAvailable}
                text={text}
                isSaving={isSaving}
                isSubmitting={isSubmitting}
                isReviewing={isReviewing}
                submitEnabled={submitEnabled}
                onSave={handleSave}
                onSubmit={handleSubmit}
                onAccept={handleAccept}
                onReject={handleReject}
                onUndo={handleUndo}
                onRedo={handleRedo}
            />
        </div>
    );
}
