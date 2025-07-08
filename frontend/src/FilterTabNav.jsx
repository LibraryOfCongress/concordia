export default function FilterTabNav() {
    return (
        <ul
            className="d-inline-flex mt-1 btn-group nav nav-tabs"
            role="tablist"
        >
            <li className="nav-item" role="presentation">
                <button
                    id="viewer-gamma"
                    className="btn btn-dark nav-link active"
                    title="Adjust gamma"
                    data-bs-toggle="tab"
                    data-bs-target="#gamma-filter"
                    role="tab"
                >
                    Brightness
                </button>
            </li>
            <li className="nav-item" role="presentation">
                <button
                    id="viewer-invert"
                    className="btn btn-dark nav-link"
                    title="Invert colors"
                    data-bs-toggle="tab"
                    data-bs-target="#invert-filter"
                    role="tab"
                >
                    Invert
                </button>
            </li>
            <li className="nav-item" role="presentation">
                <button
                    id="viewer-threshold"
                    className="btn btn-dark nav-link"
                    title="Adjust threshold"
                    data-bs-toggle="tab"
                    data-bs-target="#threshold-filter"
                    role="tab"
                >
                    Contrast
                </button>
            </li>
        </ul>
    );
}
