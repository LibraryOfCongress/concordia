import React, {useEffect, useState} from 'react';
import {HashRouter, Routes, Route, Link, useParams} from 'react-router-dom';

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

    if (error) return <div style={{color: 'red'}}>Error: {error}</div>;
    if (!assetData) return <div>Loading asset data...</div>;

    return children({assetData});
}

function AssetRoutes({assetData}) {
    return (
        <>
            <NavLinks assetData={assetData} />
            <Routes>
                <Route path="" element={<AssetView assetData={assetData} />} />
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

function AssetView({assetData}) {
    return (
        <div>
            <h2>Asset Data</h2>
            <pre>{JSON.stringify(assetData, null, 2)}</pre>
        </div>
    );
}

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

function NotFound() {
    return <h2 style={{color: 'red'}}>404 Not Found</h2>;
}

function Transcriptions() {
    const {assetId} = useParams();
    const endpoint = `/api/assets/${assetId}/transcriptions`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

function OCRTranscription() {
    const {assetId} = useParams();
    const endpoint = `/api/assets/${assetId}/transcriptions/ocr`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

function Rollback() {
    const {assetId} = useParams();
    const endpoint = `/api/assets/${assetId}/transcriptions/rollback`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

function Rollforward() {
    const {assetId} = useParams();
    const endpoint = `/api/assets/${assetId}/transcriptions/rollforward`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

function Submit() {
    const {transcriptionId} = useParams();
    const endpoint = `/api/transcriptions/${transcriptionId}/submit`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

function Review() {
    const {transcriptionId} = useParams();
    const endpoint = `/api/transcriptions/${transcriptionId}/review`;
    return <FetchAndDisplay endpoint={endpoint} />;
}

export default function App() {
    return (
        <HashRouter>
            <Routes>
                <Route
                    path="/:assetId/*"
                    element={
                        <AssetLoader>
                            {({assetData}) => (
                                <AssetRoutes assetData={assetData} />
                            )}
                        </AssetLoader>
                    }
                />
                <Route
                    path="/:campaignSlug/:projectSlug/:itemId/:assetSlug/*"
                    element={
                        <AssetLoader>
                            {({assetData}) => (
                                <AssetRoutes assetData={assetData} />
                            )}
                        </AssetLoader>
                    }
                />
                <Route path="*" element={<NotFound />} />
            </Routes>
        </HashRouter>
    );
}
