export default function ThresholdFilterForm() {
    return (
        <div
            id="threshold-filter"
            className="tab-pane pt-1 ps-3"
            role="tabpanel"
        >
            <form
                id="threshold-form"
                className="d-flex align-items-center"
                onSubmit={(e) => {
                    e.preventDefault();
                }}
            >
                <div className="row ms-0 me-3 number-input">
                    <div className="col p-1">
                        <input
                            type="number"
                            id="threshold"
                            name="threshold"
                            min="0"
                            max="255"
                            step="1"
                            defaultValue="0"
                        />
                        <label className="visually-hidden" htmlFor="threshold">
                            Threshold
                        </label>
                    </div>
                    <div className="col p-0 filter-buttons">
                        <div className="row m-0">
                            <button
                                id="threshold-up"
                                type="button"
                                className="arrow-button"
                            >
                                <span className="fas fa-chevron-up" />
                                <span className="visually-hidden">
                                    Increase
                                </span>
                            </button>
                        </div>
                        <div className="row m-0">
                            <button
                                id="threshold-down"
                                type="button"
                                className="arrow-button"
                            >
                                <span className="fas fa-chevron-down" />
                                <span className="visually-hidden">
                                    Decrease
                                </span>
                            </button>
                        </div>
                    </div>
                </div>
                <input
                    type="range"
                    id="threshold-range"
                    name="threshold-range"
                    min="0"
                    max="255"
                    step="1"
                    defaultValue="0"
                    className="filter-slider flex-grow-1"
                />
                <label className="visually-hidden" htmlFor="threshold-range">
                    Threshold
                </label>
                <input
                    type="reset"
                    className="btn btn-link underline-link fw-bold"
                    defaultValue="Reset filter"
                />
            </form>
        </div>
    );
}
