import React from 'react';

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

export default function EditorHeader({status, registeredContributors}) {
    const statusLabel = statusMap[status] || 'Unknown status';
    const instructions = instructionsMap[status] || '';

    return (
        <div className="mb-2">
            <h2>{statusLabel}</h2>
            {status !== 'not_started' && (
                <h2>
                    Registered Contributors:{' '}
                    <span className="fw-normal">{registeredContributors}</span>
                </h2>
            )}
            <p>{instructions}</p>
        </div>
    );
}
