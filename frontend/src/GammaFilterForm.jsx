export default function GammaFilterForm() {
    return (
        <div
            id="gamma-filter"
            className="tab-pane pt-1 ps-3 show active"
            role="tabpanel"
        >
            <form
                id="gamma-form"
                className="d-flex align-items-center"
                onSubmit={(e) => {
                    e.preventDefault();
                }}
            >
                <div className="row ms-0 me-3 number-input">
                    <div className="col p-1">
                        <input
                            type="number"
                            id="gamma"
                            name="gamma"
                            min="0"
                            max="5"
                            step="0.01"
                            defaultValue="1.00"
                        />
                        <label className="visually-hidden" htmlFor="gamma">
                            Gamma
                        </label>
                    </div>
                    <div className="col p-0 filter-buttons">
                        <div className="row m-0">
                            <button
                                id="gamma-up"
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
                                id="gamma-down"
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
                    id="gamma-range"
                    name="gamma-range"
                    min="0"
                    max="5"
                    step="0.01"
                    defaultValue="1.00"
                    className="filter-slider flex-grow-1"
                />
                <label className="visually-hidden" htmlFor="gamma-range">
                    Gamma
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
