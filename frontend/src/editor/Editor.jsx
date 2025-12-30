import React from 'react';
import EditorHeader from './Header';
import TranscriptionTextarea from './TranscriptionTextarea';
import EditorStatusMessages from './StatusMessages';
import EditorButtons from './Buttons';

/**
 * Editor panel for the React transcription page.
 *
 * Renders the header, textarea and action buttons. Manages save, submit,
 * accept, reject, undo and redo flows against the API, then emits updates
 * to the parent via `onTranscriptionUpdate`.
 *
 * Status mapping:
 * - "not_started" or "in_progress" -> editable with submit option visible
 * - "submitted" -> review controls visible
 *
 * This code is functional but not final. The API surface and UX may change.
 */

/**
 * Submit a draft transcription for review.
 *
 * @param {number} transcriptionId
 * @returns {Promise<Object>} JSON payload from the API
 * @throws {Error} when the response is not OK
 */
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

/**
 * Review a submitted transcription.
 *
 * @param {number} transcriptionId
 * @param {'accept'|'reject'} action
 * @returns {Promise<Object>} JSON payload from the API
 * @throws {Error} when the response is not OK
 */
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

/**
 * Accept helper.
 *
 * @param {number} transcriptionId
 * @returns {Promise<Object>}
 */
async function acceptTranscription(transcriptionId) {
    return await reviewTranscription(transcriptionId, 'accept');
}

/**
 * Reject helper.
 *
 * @param {number} transcriptionId
 * @returns {Promise<Object>}
 */
async function rejectTranscription(transcriptionId) {
    return await reviewTranscription(transcriptionId, 'reject');
}

/**
 * Editor container component.
 *
 * Orchestrates UI state, calls API endpoints for save, submit, accept,
 * reject, undo and redo, then forwards the updated payload upstream.
 *
 * @param {Object} props
 * @param {number} props.assetId
 *   Asset id used for API calls.
 * @param {Object|null} props.transcription
 *   Current transcription object, or null when none exists.
 * @param {'not_started'|'in_progress'|'submitted'} props.transcriptionStatus
 *   Current workflow status for the asset.
 * @param {number} props.registeredContributors
 *   Count of registered contributors for the asset.
 * @param {boolean} props.undoAvailable
 *   Whether an undo target exists.
 * @param {boolean} props.redoAvailable
 *   Whether a redo target exists.
 * @param {(updated:Object) => void} props.onTranscriptionUpdate
 *   Callback fired with the API response after any change.
 * @param {(text:string) => void} props.onTranscriptionTextChange
 *   Callback fired when the textarea value changes.
 */
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
