import KeyboardShortcutRow from './KeyboardShortcutRow';

/*
KeyboardHelpModal

Bootstrap modal that lists viewer keyboard shortcuts. Rows are rendered
with KeyboardShortcutRow.

Usage:
- Trigger with data-bs-target="#keyboard-help-modal"
- Presentational only

Accessibility:
- Uses role="dialog" and Bootstrap aria attributes
- Close button has aria-label
*/
export default function KeyboardHelpModal() {
    return (
        <div
            id="keyboard-help-modal"
            className="modal"
            tabIndex={-1}
            role="dialog"
        >
            <div className="modal-dialog modal-dialog-centered" role="document">
                <div className="modal-content">
                    <div className="modal-header">
                        <h5 className="modal-title">Keyboard Shortcuts</h5>
                        <button
                            type="button"
                            className="btn-close"
                            data-bs-dismiss="modal"
                            aria-label="Close"
                        ></button>
                    </div>
                    <div className="modal-body">
                        <h6>Viewer Shortcuts</h6>
                        <table className="table table-compact table-responsive">
                            <tbody>
                                <KeyboardShortcutRow
                                    keys={[
                                        {text: 'w', wrap: true},
                                        {text: 'up arrow', wrap: false},
                                    ]}
                                    description="Scroll the viewport up"
                                />
                                <KeyboardShortcutRow
                                    keys={[
                                        {text: 's', wrap: true},
                                        {text: 'down arrow', wrap: false},
                                    ]}
                                    description="Scroll the viewport down"
                                />
                                <KeyboardShortcutRow
                                    keys={[
                                        {text: 'a', wrap: true},
                                        {text: 'left arrow', wrap: false},
                                    ]}
                                    description="Scroll the viewport left"
                                />
                                <KeyboardShortcutRow
                                    keys={[
                                        {text: 'd', wrap: true},
                                        {text: 'right arrow', wrap: false},
                                    ]}
                                    description="Scroll the viewport right"
                                />
                                <KeyboardShortcutRow
                                    keys={[{text: '0', wrap: true}]}
                                    description="Fit the entire image to the viewport"
                                />
                                <KeyboardShortcutRow
                                    keys={[
                                        {text: '-', wrap: true},
                                        {text: '_', wrap: true},
                                        {text: 'Shift+W', wrap: false},
                                        {text: 'Shift+Up arrow', wrap: false},
                                    ]}
                                    description="Zoom the viewport out"
                                />
                                <KeyboardShortcutRow
                                    keys={[
                                        {text: '=', wrap: true},
                                        {text: '+', wrap: true},
                                        {text: 'Shift+S', wrap: false},
                                        {text: 'Shift+Down arrow', wrap: false},
                                    ]}
                                    description="Zoom the viewport in"
                                />
                                <KeyboardShortcutRow
                                    keys={[{text: 'r', wrap: true}]}
                                    description="Rotate the viewport clockwise"
                                />
                                <KeyboardShortcutRow
                                    keys={[{text: 'R', wrap: true}]}
                                    description="Rotate the viewport counterclockwise"
                                />
                                <KeyboardShortcutRow
                                    keys={[{text: 'f', wrap: true}]}
                                    description="Flip the viewport horizontally"
                                />
                            </tbody>
                        </table>
                    </div>
                    <div className="modal-footer">
                        <button
                            type="button"
                            className="btn btn-primary"
                            data-bs-dismiss="modal"
                        >
                            Close
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
