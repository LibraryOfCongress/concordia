import React from 'react';

/**
 * Bootstrap modal explaining the "Transcribe with OCR" feature.
 *
 * Behavior:
 * - Static content only. Shown and hidden by Bootstrap via data attributes.
 * - Triggered by an element using `data-bs-target="#ocr-help-modal"`.
 *
 * Accessibility:
 * - Uses Bootstrap modal roles and close button. Container has `role="dialog"`.
 *
 * @returns {JSX.Element}
 */
export default function OcrHelpModal() {
    return (
        <div id="ocr-help-modal" className="modal" tabIndex={-1} role="dialog">
            <div className="modal-dialog modal-dialog-centered" role="document">
                <div className="modal-content">
                    <div className="modal-header">
                        <h5 className="modal-title">
                            About Transcribe with OCR
                        </h5>
                        <button
                            type="button"
                            className="btn-close"
                            data-bs-dismiss="modal"
                            aria-label="Close"
                        ></button>
                    </div>
                    <div className="modal-body">
                        <h6 className="modal-title">What is OCR?</h6>
                        <p>
                            OCR stands for Optical Character Recognition. OCR is
                            a software tool that can extract print text from
                            some documents.
                        </p>

                        <h6>When will OCR work well?</h6>
                        <p>
                            OCR does not work on handwriting. It only works for
                            printed or typed text, meaning text created by a
                            typewriter, printing press or other mechanical
                            means. OCR will do best on consistent and clear
                            images of modern typefaces.
                        </p>

                        <h6>
                            Do I still need to review pages started with OCR?
                        </h6>
                        <p>
                            Yes. OCR is imperfect. It may not work well for some
                            or all parts of a typed page, but it can be a great
                            starting point. If you start a page with OCR you
                            should read the text closely before submitting. If
                            you are reviewing an OCR-ed page you still need to
                            review.
                        </p>

                        <h6>Who can use "Transcribe with OCR"?</h6>
                        <p>
                            <a href="/account/register/">
                                Register for an account
                            </a>{' '}
                            and <a href="/account/login/">log in</a> to use this
                            feature.
                        </p>

                        <h6>
                            Why does{' '}
                            <span className="fst-italic">By the People</span>{' '}
                            have this feature?
                        </h6>
                        <p>
                            We always want to use volunteer time effectively.
                            When the Library of Congress digitizes a large group
                            of printed pages it will usually OCR them. The
                            materials in By the People campaigns are not good
                            candidates for applying OCR at scale either because
                            they are handwritten, a mixed collection of
                            handwritten and print materials or printed on paper
                            or in a typeface that does not produce accurate OCR
                            results. However, OCR can still be a useful starting
                            point for some typed pages. Use it if you like it or
                            skip it if you do not.
                        </p>
                    </div>
                    <div className="modal-footer justify-content-center">
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
