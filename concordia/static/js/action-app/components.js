/* global jQuery */

import {$, $$} from './utils/dom.js';

import {
    html,
    text,
    list,
    mount,
    unmount,
    setChildren,
    setAttr,
    List
} from 'https://cdnjs.cloudflare.com/ajax/libs/redom/3.18.0/redom.es.min.js';

export class AssetTooltip {
    constructor() {
        this.el = html('.asset-tooltip.text-white.p-2', [
            html('.item-title'),
            html('.asset-title'),
            html('.difficulty-score-container', [
                text('Difficulty Score: '),
                html('span.difficulty-score')
            ]),
            html('.asset-year-container', [
                text('Year: '),
                html('span.asset-year')
            ])
        ]);
    }
    update(asset) {
        $('.item-title', this.el).textContent = asset.item.title;
        $('.asset-title', this.el).textContent = 'Image ' + asset.sequence;
        $('.difficulty-score', this.el).textContent = asset.difficulty;
        $('.asset-year', this.el).textContent = asset.year;
    }
}

export class MetadataPanel {
    /* Displays deep metadata for an asset inside a modal dialog */

    constructor(asset) {
        this.campaignMetadata = new CampaignMetadataDetails(
            'Campaign',
            asset.campaign
        );
        this.projectMetadata = new MetadataDetails('Project', asset.project);
        this.itemMetadata = new ItemMetadataDetails('Item', asset.item);

        this.el = html(
            'div',
            this.campaignMetadata,
            this.projectMetadata,
            this.itemMetadata
        );
    }
}

class MetadataDetails {
    constructor(sectionName, initialData) {
        this.children = [
            html('summary.h3', [
                text(`${sectionName}: `),
                html('span.title', text(initialData.title))
            ]),
            html('div.details-body')
        ];
        this.el = html('details', {open: true}, this.children);
    }
    update(data) {
        $('.details-body', this.el).textContent = data.description || '';
    }
}

class CampaignMetadataDetails extends MetadataDetails {
    constructor(sectionName, initialData) {
        super(sectionName, initialData);

        this.relatedLinkTable = new RelatedLinkTable();
    }

    onmount() {
        mount(this.el, this.relatedLinkTable);
    }

    onunmount() {
        unmount(this.el, this.relatedLinkTable);
    }

    update(data) {
        super.update(data);

        this.relatedLinkTable.update(data.related_links);
    }
}

class RelatedLinkTableRow {
    constructor() {
        this.el = html('tr', html('th'), html('td'));
    }
    update(relatedLink) {
        this.el.querySelector('th').textContent = relatedLink.title;
        setChildren(
            this.el.querySelector('td'),
            html('a', {href: relatedLink.url}, text(relatedLink.url))
        );
    }
}

class RelatedLinkTable {
    constructor() {
        this.tbody = list('tbody', RelatedLinkTableRow);
        this.el = html(
            'table.related-links.table-sm',
            {hidden: true},
            html('caption', text('Related Links')),
            this.tbody
        );
    }
    update(data) {
        this.tbody.update(data);
        setAttr(this.el, {hidden: data.length < 1});
    }
}

class ItemMetadataDetails extends MetadataDetails {
    constructor(sectionName, initialData) {
        super(sectionName, initialData);

        this.featuredMetadata = new FeaturedMetadata();
        this.rawMetadataDisplay = new RawMetadataDisplay();

        this.children.push([this.featuredMetadata, this.rawMetadataDisplay]);
        setChildren(this.el, this.children);
    }

    update(data) {
        super.update(data);

        this.featuredMetadata.update(data.metadata.item || {});
        this.rawMetadataDisplay.update(data.metadata);
    }
}

class RawMetadataDisplay {
    constructor() {
        this.el = html(
            'details',
            html('summary', text('Raw Metadata')),
            html('pre.raw-metadata')
        );
    }
    update(data) {
        // TODO: JSON key sorting, highlighting, URL -> link conversion, etc.?
        this.el.querySelector('pre').textContent = !data
            ? ''
            : JSON.stringify(data, null, 2);
    }
}

class FeaturedMetadata extends List {
    constructor() {
        super('ul.list-unstyled.metadata-list', FeaturedMetadataEntry);
    }
    update(data) {
        const FEATURED_KEYS = [
            'dates',
            'contributor_names',
            'subject_headings'
        ];

        let featured = Object.entries(data)
            .filter(([key]) => FEATURED_KEYS.includes(key))
            // We'll sort the list after filtering because mapping will convert
            // the keys to display titles:
            .sort(
                (a, b) =>
                    FEATURED_KEYS.indexOf(a[0]) - FEATURED_KEYS.indexOf(b[0])
            )
            .map(([key, value]) => {
                let values = [];

                // value can be a string, an array of strings, or an array of
                // objects. We have not yet needed to handle unnested objects or
                // arrays with mixed data-types but the code below attempts to
                // be defensive in the latter case.
                if (Array.isArray(value)) {
                    value.forEach(i => {
                        if (typeof i == 'string') {
                            values.push(i);
                        } else {
                            values.push(...Object.keys(i));
                        }
                    });
                } else {
                    values.push(value);
                }

                return [this.makeTitleFromKey(key), values];
            });

        super.update(featured);
    }

    makeTitleFromKey(key) {
        return key.replace('_', ' ');
    }
}

class FeaturedMetadataEntry {
    /*
        This is a nested list entry which will be given data in arrays of
        (title, list of strings) elements
     */

    constructor() {
        this.values = list('ul', Li);
        this.title = html('h2.title');
        this.el = html('li', this.title, this.values);
    }
    update([title, values]) {
        this.title.textContent = title;
        this.values.update(values);
    }
}

class Li {
    constructor() {
        this.el = html('li');
    }
    update(data) {
        this.el.textContent = data;
    }
}

class AssetListItem {
    constructor([assetListObserver]) {
        this.el = html('li', {
            class: 'asset rounded border',
            tabIndex: 0
        });

        assetListObserver.observe(this.el);
    }

    update(assetData) {
        let thumbnailUrl = assetData.thumbnailUrl;
        if (thumbnailUrl.includes('/iiif/')) {
            // We'll adjust the IIIF image URLs not to return something larger
            // than we're going to use:
            // FIXME: this is an ugly, ugly kludge and should be replaced with something like https://www.npmjs.com/package/iiif-image
            thumbnailUrl = thumbnailUrl.replace(
                /([/]iiif[/].+[/]full)[/]pct:100[/](0[/]default.jpg)$/,
                '$1/!512,512/$2'
            );
        }

        this.el.id = assetData.id;
        this.el.classList.add('asset', 'rounded', 'border');
        this.el.dataset.image = thumbnailUrl;
        this.el.dataset.id = assetData.id;
        this.el.dataset.difficulty = assetData.difficulty;
        this.el.dataset.status = assetData.status;
        this.el.title = `${assetData.title} (${assetData.project.title})`;
    }
}

export class AssetList extends List {
    constructor(assets, callbacks) {
        // TODO: refactor this into a utility function
        let assetListObserver = new IntersectionObserver(entries => {
            entries
                .filter(i => i.isIntersecting)
                .forEach(entry => {
                    let target = entry.target;
                    target.style.backgroundImage = `url(${
                        target.dataset.image
                    })`;
                    assetListObserver.unobserve(target);
                });
        });

        /*
        This is used to lazy-load asset images. Note that we use the image
        as the background-image value because browsers load/unload invisible
        images from memory for us, unlike a regular <img> tag.
        */

        super('ul#asset-list.list-unstyled', AssetListItem, 'id', [
            assetListObserver
        ]);

        let assetOpenHandler = event => {
            let target = event.target;
            if (target && target.classList.contains('asset')) {
                callbacks.open(target);
                return false;
            }
        };

        this.el.addEventListener('click', assetOpenHandler);
        this.el.addEventListener('keydown', event => {
            if (event.key == 'Enter' || event.key == ' ') {
                return assetOpenHandler(event);
            }
        });

        this.setupTooltip(assets);
    }

    setupTooltip(assets) {
        /* Tooltips */
        let tooltip = new AssetTooltip();

        const handleTooltipShowEvent = event => {
            let target = event.target;
            if (target && target.classList.contains('asset')) {
                const asset = assets.get(target.dataset.id);
                tooltip.update(asset);
                mount(target, tooltip);
            }
        };

        const handleTooltipHideEvent = () => {
            if (tooltip.el.parentNode) {
                unmount(tooltip.el.parentNode, tooltip);
            }
        };

        // We want to handle both mouse hover events and keyboard/tap focus
        // changes. We'll use "focusin" which bubbles instead of “focus”, which
        // does not.

        this.el.addEventListener('mouseover', handleTooltipShowEvent);
        this.el.addEventListener('focusin', handleTooltipShowEvent);

        this.el.addEventListener('mouseout', handleTooltipHideEvent);
        this.el.addEventListener('focusout', handleTooltipHideEvent);

        $('#asset-list-thumbnail-size').addEventListener('input', event => {
            this.el.style.setProperty(
                '--asset-thumbnail-size',
                event.target.value + 'px'
            );
            this.attemptAssetLazyLoad();
        });
    }

    update(assets) {
        super.update(assets);
    }

    scrollToActiveAsset() {
        let activeAsset = $('.asset-active', this.el);
        if (activeAsset) {
            // We want to push this update back after any CSS reflows complete
            // since that will affect the target scroll position:
            window.requestIdleCallback(() => {
                window.requestIdleCallback(() => {
                    activeAsset.scrollIntoView({
                        behavior: 'smooth',
                        block: 'center',
                        inline: 'nearest'
                    });
                });
            });
        }
    }

    setActiveAsset(assetElement) {
        // TODO: stop using Bootstrap classes directly and toggle semantic classes only
        $$('.asset.asset-active', this.el).forEach(element => {
            if (element != assetElement) {
                element.classList.remove('asset-active', 'border-primary');
            }
        });

        assetElement.classList.add('asset-active', 'border-primary');

        this.scrollToActiveAsset();
    }
}

class ConditionalToolbar {
    /*
        This provides the behaviour used on the reviewer and asset views’
        toolbars which either display buttons or a message explaining why you
        cannot make changes
    */

    constructor(children) {
        this.active = false;
        this.children = children;
        this.message = html('div.text-center');

        this.el = html('.control-toolbar.my-3.d-print-none.btn-row');
    }

    update(active, reason) {
        this.active = active;

        this.message.textContent = reason;

        this.el.classList.toggle('active', active);

        if (active) {
            setChildren(this.el, this.children);
        } else {
            setChildren(this.el, [this.message]);
        }
    }
}

class ReviewerView {
    constructor(submitActionCallback) {
        this.el = html(
            'div#reviewer-column.flex-column.flex-grow-1',
            (this.displayText = html('#review-transcription-text')),
            (this.toolbar = new ConditionalToolbar([
                (this.rejectButton = html(
                    'button',
                    {
                        id: 'reject-transcription-button',
                        type: 'button',
                        class: 'btn btn-primary',
                        title: 'Correct errors you see in the text'
                    },
                    text('Edit')
                )),
                (this.acceptButton = html(
                    'button',
                    {
                        id: 'accept-transcription-button',
                        type: 'button',
                        class: 'btn btn-primary',
                        title: 'Confirm that the text is accurately transcribed'
                    },
                    text('Accept')
                ))
            ]))
        );

        this.rejectButton.addEventListener('click', event => {
            event.preventDefault();
            submitActionCallback('reject');
            return false;
        });

        this.acceptButton.addEventListener('click', event => {
            event.preventDefault();
            submitActionCallback('accept');
            return false;
        });
    }

    update(asset) {
        this.currentAsset = asset;

        this.el.classList.toggle(
            'nothing-to-transcribe',
            !asset.latest_transcription
        );

        if (asset.latest_transcription) {
            this.displayText.textContent = asset.latest_transcription.text;
        } else {
            this.displayText.innerHTML = 'Nothing to transcribe';
        }
    }

    setEditorAvailability(enableEditing, reason) {
        this.toolbar.update(enableEditing, reason);
    }
}

class TranscriberView {
    constructor(submitActionCallback) {
        this.toolbar = new ConditionalToolbar([
            html(
                'div',
                {class: 'form-check w-100 text-center mt-0 mb-3'},
                (this.nothingToTranscribeCheckbox = html('input', {
                    id: 'nothing-to-transcribe',
                    type: 'checkbox',
                    class: 'form-check-input',
                    onchange: () => {
                        this.confirmNothingToTranscribeChange();
                    }
                })),
                html(
                    'label',
                    {
                        class: 'form-check-label',
                        for: 'nothing-to-transcribe'
                    },
                    text('Nothing to transcribe')
                ),
                html(
                    'a',
                    {
                        tabindex: '0',
                        class: 'btn btn-link d-inline',
                        role: 'button',
                        'data-toggle': 'popover',
                        'data-placement': 'top',
                        'data-trigger': 'focus click hover',
                        title: 'Help',
                        'data-html': 'true',
                        'data-content':
                            'If it looks like there’s nothing to transcribe, use this button and then Submit. Not sure? Check these tips: <a target="_blank" href="/help-center/how-to-transcribe/">how to transcribe</a>'
                    },
                    html('span', {
                        class: 'fas fa-question-circle',
                        'aria-label': 'Open Help'
                    })
                )
            ),
            (this.saveButton = html(
                'button',
                {
                    id: 'save-transcription-button',
                    type: 'submit',
                    class: 'btn btn-primary',
                    title: 'Save the text you entered above',
                    onclick: event => {
                        event.preventDefault();
                        this.lastLoadedText = this.textarea.value;
                        submitActionCallback('save', {
                            text: this.textarea.value
                        });
                        this.updateAvailableToolbarActions();
                        return false;
                    }
                },
                text('Save')
            )),
            (this.submitButton = html(
                'button',
                {
                    id: 'submit-transcription-button',
                    disabled: true,
                    type: 'button',
                    class: 'btn btn-primary',
                    title:
                        'Request another volunteer to review the text you entered above',
                    onclick: event => {
                        event.preventDefault();
                        submitActionCallback('submit');
                        return false;
                    }
                },
                text('Submit for Review')
            ))
        ]);

        this.el = html(
            '#transcriber-column',
            {class: 'flex-column flex-grow-1'},
            html(
                'form',
                {
                    id: 'transcription-editor',
                    class: 'flex-grow-1 d-flex flex-column'
                },
                (this.textarea = html('textarea', {
                    class:
                        'form-control w-100 rounded flex-grow-1 d-print-none',
                    name: 'text',
                    placeholder: 'Go ahead, start typing. You got this!',
                    id: 'transcription-input',
                    'aria-label': 'Transcription input',
                    onchange: () => this.updateAvailableToolbarActions(),
                    oninput: () => {
                        if (this.textarea.value) {
                            this.nothingToTranscribeCheckbox.checked = false;
                        }
                        this.updateAvailableToolbarActions();
                    }
                })),
                this.toolbar
            )
        );
    }

    onmount() {
        jQuery(this.el)
            .find('[data-toggle="popover"]')
            .popover();
    }

    update(asset) {
        this.currentAsset = asset;
        let text = '';
        if (asset.latest_transcription && asset.latest_transcription.text) {
            text = asset.latest_transcription.text;
            this.nothingToTranscribeCheckbox.checked = false;
        } else {
            this.nothingToTranscribeCheckbox.checked = true;
        }

        // <textarea> values will alter the input string related to
        // line-termination so we will store a copy of the *modified* version so
        // we can later check whether the user has altered it
        this.textarea.value = text;
        this.lastLoadedText = this.textarea.value;
        this.updateAvailableToolbarActions();
    }

    updateAvailableToolbarActions() {
        /*
            The Save button is available when the text input does not match the
            last saved transcription. The Submit button is available when the
            transcription has been saved and no further changes have been made.
        */

        let enableSave = false;
        let enableSubmit = false;
        let enableNTT = false;

        let transcription = this.currentAsset.latest_transcription;

        let saved = Boolean(transcription && transcription.id);
        let unmodified = saved && this.lastLoadedText === this.textarea.value;

        enableSave = !unmodified;
        enableSubmit = unmodified;
        enableNTT = true;

        setAttr(this.saveButton, {disabled: !enableSave});
        setAttr(this.submitButton, {disabled: !enableSubmit});
        setAttr(this.nothingToTranscribeCheckbox, {
            disabled: !enableNTT
        });
    }

    setEditorAvailability(enableEditing, reason) {
        this.toolbar.update(enableEditing, reason);
    }

    confirmNothingToTranscribeChange() {
        // Logic for event handlers when the “Nothing to Transcribe” control state is changed

        let nothingToTranscribe = this.nothingToTranscribeCheckbox.checked;
        if (nothingToTranscribe && this.textarea.value) {
            if (
                !confirm(
                    'You currently have entered text which will not be saved because “Nothing to transcribe” is checked. Do you want to discard that text?'
                )
            ) {
                nothingToTranscribe = false;
                setAttr(this.nothingToTranscribeCheckbox, {
                    checked: false
                });
            } else {
                // Clear the transcription text as requested:
                this.textarea.value = '';
            }
        }

        setAttr(this.textarea, {
            disabled: nothingToTranscribe
        });

        this.updateAvailableToolbarActions();
    }
}

function conditionalUnmount(component) {
    if (component.el.parentNode) {
        unmount(component.el.parentNode, component);
    }
}

export class AssetViewer {
    constructor(submitActionCallback) {
        this.submitActionCallback = submitActionCallback;

        // FIXME: add seadragon viewer
        this.reviewerView = new ReviewerView(this.submitAction.bind(this));
        this.transcriberView = new TranscriberView(
            this.submitAction.bind(this)
        );

        // FIXME: finish pulling in the rest of this structure so it will all be created normally
        let element = document.getElementById('asset-viewer');
        element.remove();
        this.el = element;

        setAttr(this.el, {class: 'initialized'});
    }

    submitAction(action, data) {
        this.submitActionCallback(action, data);
    }

    setMode(newMode) {
        if (this.mode == newMode) return;

        this.mode = newMode;

        if (this.mode == 'review') {
            this.activeView = this.reviewerView;
            conditionalUnmount(this.transcriberView);
        } else {
            this.activeView = this.transcriberView;
            conditionalUnmount(this.reviewerView);
        }

        mount($('#editor-column', this.el), this.activeView);
    }

    setEditorAvailability(enableEditing, reason) {
        // Set whether or not the ability to make changes should be globally
        // unavailable such as when we don't have a reservation or an AJAX
        // operation is in progress:

        this.activeView.setEditorAvailability(enableEditing, reason);
    }

    update({editable: {canEdit, reason}, mode, asset}) {
        this.setMode(mode);

        this.el.dataset.assetStatus = asset.status;

        this.activeView.update(asset);

        this.setEditorAvailability(canEdit, reason);

        $$('a.asset-external-view', this.el).forEach(i => {
            i.href = asset.resource_url;
        });

        [
            ['asset', asset],
            ['item', asset.item],
            ['project', asset.project],
            ['campaign', asset.campaign]
        ].forEach(([prefix, data]) => {
            $$(`a.${prefix}-url`, this.el).forEach(link => {
                link.href = data.url;
            });

            $$(`.${prefix}-title`, this.el).forEach(element => {
                element.textContent = data.title;
            });
        });

        $$('.asset-title', this.el).forEach(i => {
            i.textContent = 'Image ' + asset.sequence;
        });
    }
}
