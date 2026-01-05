/**
 * Application entry point for the React transcription UI.
 *
 * Mounts <App /> into the DOM element with id "app" and enables React
 * StrictMode.
 *
 * Behavior notes:
 * - StrictMode turns on extra checks in development and may invoke some
 *   render effects twice -- this is expected.
 * - No globals are exported. Side effects are limited to mounting React.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

ReactDOM.createRoot(document.getElementById('app')).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
);
