export default function InvertFilterForm() {
    return (
        <div
            id="invert-filter"
            className="tab-pane pt-2"
            role="tabpanel"
            style={{backgroundColor: 'white'}}
        >
            <form
                id="invert-form"
                onSubmit={(e) => {
                    e.preventDefault();
                }}
                className="d-flex justify-content-center"
            >
                <label className="ms-2 align-middle">Off</label>
                <div className="form-check form-switch custom-control-inline">
                    <input
                        type="checkbox"
                        id="invert"
                        name="invert"
                        className="form-check-input"
                        role="switch"
                    />
                    <label className="form-check-label" htmlFor="invert">
                        <span className="visually-hidden">Invert</span>
                    </label>
                </div>
                <label className="align-middle">On</label>
            </form>
        </div>
    );
}
