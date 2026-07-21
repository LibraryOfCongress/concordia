/**
 * Custom file picker callback for TinyMCE inside the Concordia admin panel.
 * Routes administrators directly to the interactive Media Library Manager overview.
 *
 * @param {Function} callback - TinyMCE callback function to pass back asset metadata.
 * @param {string} value - Current value of the input field.
 * @param {Object} meta - Metadata object containing filetype and control details.
 */
function concordiaTinyMcePicker(callback, value, meta) {
    if (meta.filetype !== 'image') {
        alert('This picker only supports image uploads.');
        return;
    }

    // Capture standard mapping fields securely from frame interactions
    window.tinymce_callback = function (url, titleText = '') {
        callback(url, {alt: titleText, title: titleText});
    };

    // Route to the changelist view to open the asset gallery view
    const adminLibraryUrl = '/admin/concordia/concordiafile/?_popup=1';

    window.open(
        adminLibraryUrl,
        'concordia_upload_popup',
        'width=950,height=700,resizable=yes,scrollbars=yes,status=no',
    );
}

// Bind directly to window and globalThis to guarantee exposure across ES Module bundler wrappers
if (typeof window !== 'undefined') {
    window.concordiaTinyMcePicker = concordiaTinyMcePicker;
}
if (typeof globalThis !== 'undefined') {
    globalThis.concordiaTinyMcePicker = concordiaTinyMcePicker;
}
