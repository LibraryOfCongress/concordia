import React, {useEffect, useState} from 'react';
import {HashRouter, Routes, Route, Link, useParams} from 'react-router-dom';
import ViewerSplit from './ViewerSplit';

/**
 * Fetches a JSON endpoint and displays the response.
 *
 * Useful as a temporary inspector while APIs and UI are evolving.
 *
 * @param {Object} props
 * @param {string} props.endpoint
 *   Relative or absolute API URL to request.
 * @param {string} [props.method="GET"]
 *   HTTP method to use.
 * @returns {JSX.Element}
 */
function FetchAndDisplay({endpoint, method = 'GET'}) {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetch(endpoint, {
            method,
            headers: {'Content-Type': 'application/json'},
        })
            .then((response) => {
                if (!response.ok) throw new Error(response.statusText);
                return response.json();
            })
            .then(setData)
            .catch((err) => setError(err.toString()));
    }, [endpoint, method]);

    return (
        <div>
            <h2>
                {method} {endpoint}
            </h2>
            {error && <div style={{color: 'red'}}>Error: {error}</div>}
            <pre>{JSON.stringify(data, null, 2)}</pre>
        </div>
    );
}

/**
 * Loads asset JSON by id or by slugs, then renders children with the data.
 *
 * Route params are read from the current URL. If params describe either
 * `/assets/:assetId` or the slug form, the component fetches the asset
 * from the API and passes results to a render prop.
 *
 * Children receive an object with:
 *   - `assetData`: the latest asset payload
 *   - `handleTranscriptionUpdate`: callback to merge a server response from
 *     a transcription action back into `assetData`
 *
 * @param {Object} props
 * @param {Function} props.children
 *   Render prop called as `children({ assetData, handleTranscriptionUpdate })`.
 * @returns {JSX.Element}
 */
function AssetLoader({children}) {
    const params = useParams();
    const [assetData, setAssetData] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        let endpoint;
        if (params.assetId) {
            endpoint = `/api/assets/${params.assetId}`;
        } else if (
            params.campaignSlug &&
            params.projectSlug &&
            params.itemId &&
            params.assetSlug
        ) {
            endpoint = `/api/assets/${params.campaignSlug}/${params.projectSlug}/${params.itemId}/${params.assetSlug}/`;
        } else {
            setError('Missing asset parameters');
            return;
        }

        fetch(endpoint, {
            method: 'GET',
            headers: {'Content-Type': 'application/json'},
        })
            .then((response) => {
                if (!response.ok) throw new Error(response.statusText);
                return response.json();
            })
            .then(setAssetData)
            .catch((err) => setError(err.toString()));
    }, [params]);

    /**
     * Merge a transcription API response back into local asset state.
     *
     * Expects the server to return `{ id, text, ..., asset: <AssetOut> }`.
     * If the response is missing `asset`, the update is skipped.
     *
     * @param {Object} updatedTranscription
     */
    const handleTranscriptionUpdate = (updatedTranscription) => {
        if (!updatedTranscription?.asset) {
            console.error(
                'Missing asset on updatedTranscription:',
                updatedTranscription,
            );
            return;
        }

        setAssetData({
            ...updatedTranscription.asset,
            transcription: updatedTranscription,
            transcriptionStatus: updatedTranscription.asset.transcriptionStatus,
        });
    };

    if (error) return <div style={{color: 'red'}}>Error: {error}</div>;
    if (!assetData) return <div>Loading asset data...</div>;

    return children({assetData, handleTranscriptionUpdate});
}

/**
 * Defines nested routes for a single asset view.
 *
 * Renders the split viewer by default and wires routes for supporting
 * actions like OCR, rollback, rollforward, submit and review.
 *
 * @param {Object} props
 * @param {Object} props.assetData
 * @param {Function} props.handleTranscriptionUpdate
 * @returns {JSX.Element}
 */
function AssetRoutes({assetData, handleTranscriptionUpdate}) {
    return (
        <>
            <NavLinks assetData={assetData} />
            <Routes>
                <Route
                    path=""
                    element={
                        <ViewerSplit
                            assetData={assetData}
                            onTranscriptionUpdate={handleTranscriptionUpdate}
                        />
                    }
                />
                <Route path="transcriptions" element={<Transcriptions />} />
                <Route path="ocr" element={<OCRTranscription />} />
                <Route path="rollback" element={<Rollback />} />
                <Route path="rollforward" element={<Rollforward />} />
                <Route path="submit/:transcriptionId" element={<Submit />} />
                <Route path="review/:transcriptionId" element={<Review />} />
                <Route path="*" element={<NotFound />} />
            </Routes>
        </>
    );
}

/**
 * Renders navigation links for the current asset and optional
 * links for a specific transcription.
 *
 * @param {Object} props
 * @param {Object} props.assetData
 * @returns {JSX.Element|null}
 */
function NavLinks({assetData}) {
    if (!assetData) return null;

    const currentAssetId = assetData.id;
    const transcriptionId = assetData.transcription?.id;

    return (
        <nav>
            <Link to={`/${currentAssetId}`}>Asset</Link> |{' '}
            <Link to={`/${currentAssetId}/transcriptions`}>Transcriptions</Link>{' '}
            | <Link to={`/${currentAssetId}/ocr`}>OCR</Link> |{' '}
            <Link to={`/${currentAssetId}/rollback`}>Rollback</Link> |{' '}
            <Link to={`/${currentAssetId}/rollforward`}>Rollforward</Link>
            {transcriptionId && (
                <>
                    {' | '}
                    <Link to={`/${currentAssetId}/submit/${transcriptionId}`}>
                        Submit
                    </Link>{' '}
                    |{' '}
                    <Link to={`/${currentAssetId}/review/${transcriptionId}`}>
                        Review
                    </Link>
                </>
            )}
        </nav>
    );
}

/**
 * Fallback route for unknown paths.
 *
 * @returns {JSX.Element}
 */
function NotFound() {
    return <h2 style={{color: 'red'}}>404 Not Found</h2>;
}

/**
 * Debug route: show transcriptions list payload for an asset.
 *
 * @returns {JSX.Element}
 */
function Transcriptions() {
    const {assetId} = useParams();
    const endpoint = `/api/assets/${assetId}/transcriptions`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

/**
 * Debug route: trigger OCR transcription endpoint for an asset.
 *
 * @returns {JSX.Element}
 */
function OCRTranscription() {
    const {assetId} = useParams();
    const endpoint = `/api/assets/${assetId}/transcriptions/ocr`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

/**
 * Debug route: call rollback endpoint for an asset.
 *
 * @returns {JSX.Element}
 */
function Rollback() {
    const {assetId} = useParams();
    const endpoint = `/api/assets/${assetId}/transcriptions/rollback`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

/**
 * Debug route: call rollforward endpoint for an asset.
 *
 * @returns {JSX.Element}
 */
function Rollforward() {
    const {assetId} = useParams();
    const endpoint = `/api/assets/${assetId}/transcriptions/rollforward`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

/**
 * Debug route: submit a transcription by id.
 *
 * @returns {JSX.Element}
 */
function Submit() {
    const {transcriptionId} = useParams();
    const endpoint = `/api/transcriptions/${transcriptionId}/submit`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

/**
 * Debug route: review a transcription by id.
 *
 * @returns {JSX.Element}
 */
function Review() {
    const {transcriptionId} = useParams();
    const endpoint = `/api/transcriptions/${transcriptionId}/review`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

/**
 * Application router for the React transcription UI.
 *
 * Supports two entry patterns:
 *   1) `/:assetId/*` -- load by numeric id
 *   2) `/:campaignSlug/:projectSlug/:itemId/:assetSlug/*` -- load by slugs
 *
 * Both patterns use `AssetLoader`, which fetches JSON then renders nested
 * routes with `AssetRoutes`.
 *
 * @returns {JSX.Element}
 */
export default function App() {
    return (
        <HashRouter>
            <Routes>
                <Route
                    path="/:assetId/*"
                    element={
                        <AssetLoader>
                            {({assetData, handleTranscriptionUpdate}) => (
                                <AssetRoutes
                                    assetData={assetData}
                                    handleTranscriptionUpdate={
                                        handleTranscriptionUpdate
                                    }
                                />
                            )}
                        </AssetLoader>
                    }
                />
                <Route
                    path="/:campaignSlug/:projectSlug/:itemId/:assetSlug/*"
                    element={
                        <AssetLoader>
                            {({assetData, handleTranscriptionUpdate}) => (
                                <AssetRoutes
                                    assetData={assetData}
                                    handleTranscriptionUpdate={
                                        handleTranscriptionUpdate
                                    }
                                />
                            )}
                        </AssetLoader>
                    }
                />
                <Route path="*" element={<NotFound />} />
            </Routes>
        </HashRouter>
    );
}
