/**
 * InvertFilterForm
 *
 * Simple on/off control for an invert color filter. Parent manages state and
 * passes the current value plus a setter.
 *
 * @component
 * @param {Object} props
 * @param {boolean} props.invert - Current invert state
 * @param {(value: boolean) => void} props.setInvert - Setter for invert state
 */
export default function InvertFilterForm({invert, setInvert}) {
    const handleChange = (e) => {
        setInvert(e.target.checked);
    };

    const handleReset = () => {
        setInvert(false);
    };

    return (
        <div
            id="invert-filter"
            className="tab-pane pt-2"
            role="tabpanel"
            style={{backgroundColor: 'white'}}
        >
            <form
                id="invert-form"
                onSubmit={(e) => e.preventDefault()}
                onReset={handleReset}
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
                        checked={invert}
                        onChange={handleChange}
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
