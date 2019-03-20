/* global OpenSeadragon */
/* eslint-disable no-console */

import {
    mount,
    unmount
} from 'https://cdnjs.cloudflare.com/ajax/libs/redom/3.18.0/redom.es.min.js';

import {$, $$, emptyNode, sortChildren} from './utils/dom.js';
import {fetchJSON, getCachedData} from './utils/api.js';
import {AssetTooltip, MetadataPanel} from './components.js';

export class ActionApp {
    constructor(config) {
        /*
            Rough flow:
            1. Get references for key DOM elements
            2. Fetch the list of assets
            3. TODO: register for updates
            4. Populate the DOM with assets
            5. Add filtering & scroll event handlers
        */

        this.config = Object.assign({}, config);

        this.appElement = $('#action-app-main');

        /*
            These will store *all* metadata retrieved from the API so it can be
            easily queried and updated.

            Note that while the IDs returned from the server may currently be
            numeric we index them as strings to avoid surprises in the future
            and to avoid issues with DOM interfaces such as dataset which
            convert arguments to strings.
        */
        this.assets = new Map();
        this.items = new Map();
        this.projects = new Map();
        this.campaigns = new Map();

        this.setupGlobalKeyboardEvents();

        this.setupToolbars();

        this.setupModeSelector();
        this.setupAssetList();
        this.setupAssetViewer();

        this.connectAssetEventStream();

        this.refreshData();
    }

    setupGlobalKeyboardEvents() {
        // Register things which we need to handle in any context, such as
        // opening help or handling focus-shift events

        document.body.addEventListener('keydown', evt => {
            switch (evt.key) {
                case '?':
                case 'F1':
                    if (!evt.target.tagName.match(/(INPUT|TEXTAREA)/i))
                        // Either the F1 or ? keys were pressed outside of a
                        // text field so we'll open the global help modal:
                        window.jQuery('#help-modal').modal('show');
                    return false;

                case 'Escape':
                    this.closeViewer();
                    return false;
            }
        });
    }

    setupModeSelector() {
        this.modeSelection = $('#activity-mode-selection');

        $$('button', this.modeSelection).forEach(elem => {
            elem.addEventListener('click', evt => {
                $$('button', this.modeSelection).forEach(inactiveElem => {
                    inactiveElem.classList.remove('active');
                });
                evt.target.classList.add('active');
                this.closeViewer();
                this.refreshData();
            });
        });
    }

    getCurrentMode() {
        this.currentMode = this.modeSelection.querySelector('.active').value;
        this.appElement.dataset.mode = this.currentMode;
        $$('.current-mode').forEach(i => (i.innerText = this.currentMode));
    }

    setupToolbars() {
        let helpToggle = $('#help-toggle');
        let helpPanel = $('#help-panel');

        helpToggle.addEventListener('click', () => {
            helpPanel.toggleAttribute('hidden');
            return false;
        });
    }

    connectAssetEventStream() {
        let assetSocketURL = // FIXME: this path should not be hard-coded
            (document.location.protocol == 'https:' ? 'wss://' : 'ws://') +
            window.location.host +
            '/ws/asset/asset_updates/';
        console.log(`Connecting to ${assetSocketURL}`);
        let assetSocket = (this.assetSocket = new WebSocket(assetSocketURL));

        assetSocket.onmessage = rawMessage => {
            console.log('Asset socket message: ', rawMessage);

            let data = JSON.parse(rawMessage.data);
            let message = data.message;
            let message_sent = data.sent;
            let assetId = message.asset_pk.toString();
            let asset = this.assets.get(assetId);

            if (!asset) {
                console.warn(
                    `Asset ID ${assetId} has not been loaded yet. We are ignoring this message for now.`
                );
                return;
            }

            console.log('Asset before:', asset);
            switch (message.type) {
                case 'asset_update': {
                    asset.status = message.status; // FIXME: the UI does not currently handle status changes
                    asset.difficulty = message.difficulty;
                    asset.submitted_by = message.submitted_by; // FIXME: the UI needs to apply the same self-edit/approval rules
                    asset.sent = message_sent;
                    break;
                }
                case 'asset_reservation_obtained':
                    if (
                        this.config.currentUser &&
                        this.config.currentUser != message.user_pk
                    ) {
                        this.markAssetAsUnavailable(assetId);
                    }
                    break;
                case 'asset_reservation_released':
                    // FIXME: we need to test whether the user who reserved it is different than the user we're running as!
                    this.markAssetAsAvailable(assetId);
                    break;
                default:
                    console.warn(
                        `Unknown message type ${message.type}: ${message}`
                    );
            }
            console.log('Asset after:', asset);
        };

        assetSocket.onerror = evt => {
            console.error('Asset socket error occurred: ', evt);
        };

        assetSocket.onclose = evt => {
            console.warn('Asset socket closed: ', evt);
            window.setTimeout(this.connectAssetEventStream.bind(this), 1000);
        };
    }

    refreshData() {
        this.getCurrentMode();
        this.assets.clear();
        this.resetAssetList();
        this.fetchAssetData();
    }

    resetAssetList() {
        emptyNode(this.assetList);
    }

    setupAssetList() {
        this.assetList = $('#asset-list');

        /*
            This is used to lazy-load asset images. Note that we use the image
            as the background-image value because browsers load/unload invisible
            images from memory for us, unlike a regular <img> tag.
        */
        this.assetListObserver = new IntersectionObserver(entries => {
            entries
                .filter(i => i.isIntersecting)
                .forEach(entry => {
                    let target = entry.target;
                    target.style.backgroundImage = `url(${
                        target.dataset.image
                    })`;
                    this.assetListObserver.unobserve(target);
                });
        });

        // We have a simple queue of URLs for asset pages which have not yet
        // been fetched which fetchNextAssetPage will empty:
        this.queuedAssetPageURLs = [];

        let loadMoreButton = $('#load-more-assets');
        loadMoreButton.addEventListener('click', () =>
            this.fetchNextAssetPage()
        );
        new IntersectionObserver(entries => {
            if (entries.filter(i => i.isIntersecting)) {
                this.fetchNextAssetPage();
            }
        }).observe(loadMoreButton);

        let handleViewerOpenEvent = evt => {
            let target = evt.target;
            if (target && target.classList.contains('asset')) {
                this.openViewer(target);
                return false;
            }
        };
        this.assetList.addEventListener('click', handleViewerOpenEvent);
        this.assetList.addEventListener('keydown', evt => {
            if (evt.key == 'Enter' || evt.key == ' ') {
                return handleViewerOpenEvent(evt);
            }
        });

        /* List sorting */
        this.sortModeSelector = $('#sort-mode');
        this.sortMode = this.sortModeSelector.value;
        this.sortModeSelector.addEventListener('change', evt => {
            this.sortMode = evt.target.value;
            sortChildren(this.assetList, this.getAssetSortKeyGenerator());
            this.scrollToActiveAsset();
        });

        /* List filtering */
        this.campaignSelect = $('#selected-campaign');
        fetchJSON('/campaigns/') // FIXME: this URL should be an input variable!
            .then(data => {
                data.objects.forEach(campaign => {
                    let o = document.createElement('option');
                    o.value = campaign.id;
                    o.innerText = campaign.title;
                    this.campaignSelect.appendChild(o);
                });
            });
        this.campaignSelect.addEventListener('change', () =>
            this.filterAssets()
        );

        /* Tooltips */
        const tooltip = new AssetTooltip();

        const handleTooltipShowEvent = evt => {
            let target = evt.target;
            if (target && target.classList.contains('asset')) {
                const asset = this.assets.get(target.dataset.id);
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

        this.assetList.addEventListener('mouseover', handleTooltipShowEvent);
        this.assetList.addEventListener('focusin', handleTooltipShowEvent);

        this.assetList.addEventListener('mouseout', handleTooltipHideEvent);
        this.assetList.addEventListener('focusout', handleTooltipHideEvent);

        $('#asset-list-thumbnail-size').addEventListener('input', evt => {
            this.assetList.style.setProperty(
                '--asset-thumbnail-size',
                evt.target.value + 'px'
            );
        });
    }

    getAssetSortKeyGenerator() {
        /*
            Return a function for the current sort mode which will generate the
            appropriate sort key from a given .asset Element.
        */

        let int = str => parseInt(str, 10);

        switch (this.sortMode) {
            case 'hardest':
                return elem => -1 * int(elem.dataset.difficulty);
            case 'easiest':
                return elem => int(elem.dataset.difficulty);
            case 'campaign':
                // Sort by Campaign using sub-values for stable ordering
                return elem => {
                    let asset = this.assets.get(elem.dataset.id);
                    return [
                        asset.campaign.title,
                        asset.project.title,
                        asset.item.title,
                        asset.id
                    ];
                };
            case 'item-id':
                return elem => {
                    let asset = this.assets.get(elem.dataset.id);
                    return asset.item.item_id;
                };
            default:
                return elem => int(elem.id);
        }
    }

    setupAssetViewer() {
        this.assetViewer = $('#asset-viewer');
        this.seadragonViewer = new OpenSeadragon({
            id: 'asset-image',
            prefixUrl:
                'https://cdnjs.cloudflare.com/ajax/libs/openseadragon/2.4.0/images/',
            gestureSettingsTouch: {
                pinchRotate: true
            },
            showNavigator: true,
            showRotationControl: true,
            showReferenceStrip: true,
            sequenceMode: true,
            toolbar: 'viewer-controls',
            zoomInButton: 'viewer-zoom-in',
            zoomOutButton: 'viewer-zoom-out',
            homeButton: 'viewer-home',
            fullPageButton: 'viewer-full-page',
            rotateLeftButton: 'viewer-rotate-left',
            rotateRightButton: 'viewer-rotate-right',
            nextButton: 'viewer-next-page',
            previousButton: 'viewer-previous-page'
        });

        $('#close-viewer-button').addEventListener('click', () => {
            this.closeViewer();
        });
    }

    fetchAssetData() {
        let url = this.config.assetDataUrlTemplate.replace(
            /{action}/,
            this.currentMode
        );

        this.fetchAssetPage(url);
    }

    fetchAssetPage(url) {
        fetchJSON(url).then(data => {
            data.objects.forEach(i => this.createAsset(i, data.sent));

            $('#asset-count').innerText = this.assets.size;

            if (data.pagination.next) {
                this.queuedAssetPageURLs.push(data.pagination.next);
            }

            if (this.assets.size < 300) {
                // We like to have a fair number of items to start with
                this.fetchNextAssetPage();
            }
        });
    }

    fetchNextAssetPage() {
        if (this.queuedAssetPageURLs.length > 0) {
            this.fetchAssetPage(this.queuedAssetPageURLs.pop());
        }
    }

    getCachedItem(refObj) {
        return getCachedData(this.items, refObj, 'item');
    }

    getCachedProject(refObj) {
        return getCachedData(this.projects, refObj, 'project');
    }

    getCachedCampaign(refObj) {
        return getCachedData(this.campaigns, refObj, 'object');
    }

    createAsset(assetData, assetSent) {
        // n.b. although we are currently using numeric keys, we're coding under
        // the assumption that they will become opaque strings in the future:
        assetData.sent = assetSent;
        this.assets.set(assetData.id.toString(), assetData);

        let assetElement = document.createElement('li');
        assetElement.id = assetData.id;
        assetElement.classList.add('asset', 'rounded', 'border');
        assetElement.dataset.image = assetData.thumbnail;
        assetElement.dataset.id = assetData.id;
        assetElement.dataset.difficulty = assetData.difficulty;
        assetElement.title = `${assetData.title} (${assetData.project.title})`;
        assetElement.tabIndex = 0;

        this.assetListObserver.observe(assetElement);

        this.assetList.appendChild(assetElement);
    }

    markAssetAsAvailable(assetId) {
        console.log(`Marking asset ${assetId} available`);
        document.getElementById(assetId).classList.remove('available');
        this.checkViewerAvailability(assetId);
    }

    markAssetAsUnavailable(assetId) {
        console.log(`Marking asset ${assetId} unavailable`);
        document.getElementById(assetId).classList.add('unavailable');
        this.checkViewerAvailability(assetId);
    }

    filterAssets() {
        console.time('Filtering assets');
        let currentCampaignId = this.campaignSelect.value;

        if (!currentCampaignId) {
            $$('.asset[hidden]', this.assetList).forEach(i =>
                i.removeAttribute('hidden')
            );
        } else {
            $$('.asset', this.assetList).forEach(elem => {
                // FIXME: if we populated the filterable attributes as data values when we create the asset we could avoid this lookup entirely and test replacing this with querySelectorAll using attribute selectors
                // TODO: test whether iterating the list backwards and/or doing this in requestAnimationFrame would be more efficient interacting with our intersection observer
                let asset = this.assets.get(elem.dataset.id);
                if (asset.campaign.id == currentCampaignId) {
                    elem.removeAttribute('hidden');
                } else {
                    elem.setAttribute('hidden', 'hidden');
                }
            });
        }
        console.timeEnd('Filtering assets');
    }

    scrollToActiveAsset() {
        let activeAsset = $('.asset-active', this.assetList);
        if (activeAsset) {
            activeAsset.scrollIntoView({
                behavior: 'smooth',
                block: 'center',
                inline: 'nearest'
            });
        }
    }

    openViewer(assetElement) {
        let asset = this.assets.get(assetElement.dataset.id);

        // TODO: stop using Bootstrap classes directly and toggle semantic classes only
        $$('.asset.asset-active', this.assetList).forEach(elem => {
            elem.classList.remove('asset-active', 'border-primary');
        });
        assetElement.classList.add('asset-active', 'border-primary');
        this.scrollToActiveAsset();

        this.metadataPanel = new MetadataPanel(asset);
        mount(
            $('#asset-info-modal .modal-body', this.assetViewer),
            this.metadataPanel
        );

        this.getCachedItem(asset.item).then(itemInfo => {
            this.metadataPanel.itemMetadata.update(itemInfo);
        });

        this.getCachedProject(asset.project).then(projectInfo => {
            this.metadataPanel.projectMetadata.update(projectInfo);
        });

        this.getCachedCampaign(asset.campaign).then(campaignInfo => {
            this.metadataPanel.campaignMetadata.update(campaignInfo);
        });

        this.appElement.dataset.openAssetId = asset.id;

        $$('a.asset-external-view', this.assetViewer).forEach(i => {
            i.href = asset.resource_url;
        });

        // Generic text & URL updates until we finish componentizing everything:
        [
            ['asset', asset],
            ['item', asset.item],
            ['project', asset.project],
            ['campaign', asset.campaign]
        ].forEach(([prefix, data]) => {
            $$(`a.${prefix}-url`, this.assetViewer).forEach(link => {
                link.href = data.url;
            });

            $$(`.${prefix}-title`, this.assetViewer).forEach(elem => {
                elem.innerText = data.title;
            });
        });

        // Until we component-ize this, we use a custom display for the asset titles:
        $$('.asset-title', this.assetViewer).forEach(i => {
            i.innerText = 'Image ' + asset.sequence;
        });

        // This should be a component which renders based on the mode and the provided data
        if (asset.latest_transcription) {
            if (this.currentMode == 'review') {
                $(
                    '#review-transcription-text'
                ).innerHTML = asset.latest_transcription.replace(
                    /\n/g,
                    '<br/>'
                );
            } else {
                $('textarea', this.assetViewer).value =
                    asset.latest_transcription;
            }
        } else {
            if (this.currentMode == 'review') {
                // FIXME: this really should be a property in the data rather
                // than an inferred value from latest_transcription and we
                // probably want this to be styled differently, too

                $('#review-transcription-text').innerHTML =
                    'Nothing to transcribe';
            } else {
                $('textarea', this.assetViewer).value = '';
            }
        }

        if (this.seadragonViewer.isOpen()) {
            this.seadragonViewer.close();
        }

        let tileSources = [
            {
                type: 'image',
                url: asset.thumbnail
            }
        ];
        let initialPage = 0;

        if (asset.previous_thumbnail) {
            initialPage = 1;
            tileSources.unshift({
                type: 'image',
                url: asset.previous_thumbnail
            });
        }

        if (asset.next_thumbnail) {
            tileSources.push({
                type: 'image',
                url: asset.next_thumbnail
            });
        }

        this.seadragonViewer.open(tileSources, initialPage);

        this.checkViewerAvailability(assetElement.id);
    }

    closeViewer() {
        delete this.appElement.dataset.openAssetId;

        if (this.seadragonViewer.isOpen()) {
            this.seadragonViewer.close();
        }

        if (this.metadataPanel && this.metadataPanel.el.parentNode) {
            unmount(this.metadataPanel.el.parentNode, this.metadataPanel);
        }

        this.scrollToActiveAsset();
    }

    checkViewerAvailability() {
        if (!this.appElement.dataset.openAssetId) {
            return;
        }

        let editor = document.getElementById('editor-column');

        let openAsset = document.getElementById(
            this.appElement.dataset.openAssetId
        );

        if (openAsset.classList.contains('unavailable')) {
            $$('input,button', editor).forEach(i =>
                i.setAttribute('disabled', 'disabled')
            );
            $$('textarea', editor).forEach(i =>
                i.setAttribute('readonly', 'readonly')
            );
        } else {
            $$('button,input,textarea', editor).forEach(i => {
                i.removeAttribute('disabled');
                i.removeAttribute('readonly');
            });
        }
    }
}
