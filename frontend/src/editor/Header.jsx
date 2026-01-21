import React from 'react';

/**
 * Editor header for the React transcription page.
 *
 * Shows a human friendly status label, task instructions and, when applicable,
 * the count of registered contributors. This module is functional but in flux.
 * It is part of the React transcription UI and may change as the API and UX
 * are refined.
 */

/**
 * Maps workflow status codes to display labels.
 * Keys must match backend status values.
 * @type {Record<'submitted'|'completed'|'not_started'|'in_progress', string>}
 */
const statusMap = {
    submitted: 'Needs review',
    completed: 'Completed',
    not_started: 'Not started',
    in_progress: 'In progress',
};

/**
 * Maps workflow status codes to short user instructions.
 * Copy is provisional and may change.
 * @type {Record<'submitted'|'completed'|'not_started'|'in_progress', string>}
 */
const instructionsMap = {
    not_started: 'Transcribe this page.',
    in_progress: 'Someone started this transcription. Can you finish it?',
    submitted: 'Check this transcription thoroughly. Accept if correct!',
    completed: 'This transcription is finished! You can read and add tags.',
};

/**
 * Header section for the editor column.
 *
 * @param {Object} props
 * @param {'not_started'|'in_progress'|'submitted'|'completed'} props.status
 *   Current workflow status for the asset.
 * @param {number} props.registeredContributors
 *   Count of registered contributors. Shown for all states except not_started.
 */
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
