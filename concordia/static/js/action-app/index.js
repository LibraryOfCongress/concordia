/* global OpenSeadragon */
/* eslint-disable no-console */

import {
    mount,
    unmount
} from 'https://cdnjs.cloudflare.com/ajax/libs/redom/3.18.0/redom.es.min.js';

import {$, $$, emptyNode, sortChildren} from './utils/dom.js';
import {fetchJSON, getCachedData} from './utils/api.js';
import {AssetTooltip} from './components.js';

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

        this.setupModeSelector();
        this.setupAssetList();
        this.setupAssetViewer();

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

        const handleTooltipRevealEvent = evt => {
            let target = evt.target;
            if (target && target.classList.contains('asset')) {
                const asset = this.assets.get(target.dataset.id);
                tooltip.update(asset);
                mount(target, tooltip);
            }
        };
        this.assetList.addEventListener('mouseover', handleTooltipRevealEvent);
        // Unlike focus, focusin bubbles:
        this.assetList.addEventListener('focusin', handleTooltipRevealEvent);

        // We'll remove the tooltip any time the asset list itself loses focus:
        this.assetList.addEventListener('blur', () => {
            unmount(tooltip.el.parentNode, tooltip);
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
            case 'item-id':
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
            toolbar: 'viewer-controls',
            zoomInButton: 'viewer-zoom-in',
            zoomOutButton: 'viewer-zoom-out',
            homeButton: 'viewer-home',
            fullPageButton: 'viewer-full-page',
            rotateLeftButton: 'viewer-rotate-left',
            rotateRightButton: 'viewer-rotate-right'
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
            data.objects.forEach(i => this.createAsset(i));

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
        return getCachedData(this.campaigns, refObj, 'campaign');
    }

    createAsset(assetData) {
        // n.b. although we are
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

        this.getCachedItem(asset.item).then(itemInfo => {
            $('#asset-more-info').innerHTML =
                '<pre>' + JSON.stringify(itemInfo, null, 3) + '</pre>';
        });

        this.appElement.dataset.openAssetId = asset.id;

        $$('.asset-title', this.assetViewer).forEach(i => {
            i.innerText = asset.title;
            i.href = asset.url;
        });
        $$('.item-title', this.assetViewer).forEach(i => {
            i.innerText = asset.item.title;
            i.href = asset.item.url;
        });
        $$('.project-title', this.assetViewer).forEach(i => {
            i.innerText = asset.project.title;
            i.href = asset.project.url;
        });
        $$('.campaign-title', this.assetViewer).forEach(i => {
            i.innerText = asset.campaign.title;
            i.href = asset.campaign.url;
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

        this.seadragonViewer.open({type: 'image', url: asset.thumbnail});
    }

    closeViewer() {
        delete this.appElement.dataset.openAssetId;

        if (this.seadragonViewer.isOpen()) {
            this.seadragonViewer.close();
        }

        this.scrollToActiveAsset();
    }
}
