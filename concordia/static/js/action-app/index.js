/* global Split jQuery URITemplate */
/* eslint-disable no-console */

import {mount} from 'https://cdnjs.cloudflare.com/ajax/libs/redom/3.18.0/redom.es.min.js';
import {
    AssetList,
    AssetViewer,
    conditionalUnmount,
    MetadataPanel
} from './components.js';
import {fetchJSON, getCachedData} from './utils/api.js';
import {$, $$, setSelectValue} from './utils/dom.js';

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

        this.urlTemplates = {};
        Object.entries(config.urlTemplates).forEach(([key, value]) => {
            this.urlTemplates[key] = new URITemplate(value);
        });

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

        this.setupSharing();
        this.setupPersistentStateManagement();

        this.setupModeSelector();
        this.setupAssetList();
        this.setupAssetViewer();

        this.connectAssetEventStream();

        // We call this before refreshData to ensure that its request gets in first:
        this.restoreOpenAsset();

        this.refreshData();
    }

    setupPersistentStateManagement() {
        this.persistentState = new URLSearchParams(
            window.location.hash.replace(/^#/, '')
        );
    }

    serializeStateToURL() {
        let loc = new URL(window.location);
        loc.hash = this.persistentState.toString();
        window.history.replaceState(null, null, loc);
    }

    addToState(key, value) {
        this.persistentState.set(key, value);
        this.serializeStateToURL();
    }

    deleteFromState(key) {
        this.persistentState.delete(key);
        this.serializeStateToURL();
    }

    restoreOpenAsset() {
        let assetId = this.persistentState.get('asset');
        if (!assetId) return;

        let allAssetsURL = this.urlTemplates.assetData.expand({
            // This is a special-case for retrieving all assets regardless of status
            action: 'assets'
        });

        this.fetchAssetPage(allAssetsURL + '?pk=' + assetId).then(() => {
            this.assetList.updateCallbacks.push(() => {
                let element = document.getElementById(assetId);
                if (!element) {
                    console.warn('Expected to load asset with ID %s', assetId);
                } else {
                    this.openViewer(element);
                }
            });
        });
    }

    setupGlobalKeyboardEvents() {
        // Register things which we need to handle in any context, such as
        // opening help or handling focus-shift events

        document.body.addEventListener('keydown', event => {
            switch (event.key) {
                case '?':
                case 'F1':
                    if (!event.target.tagName.match(/(INPUT|TEXTAREA)/i)) {
                        // Either the F1 or ? keys were pressed outside of a
                        // text field so we'll open the global help modal:
                        window.jQuery('#help-modal').modal('show');
                        return false;
                    }
                    break;

                case 'Escape':
                    this.closeViewer();
                    return false;
            }
        });
    }

    setupModeSelector() {
        this.modeSelection = $('#activity-mode-selection');

        $$('button', this.modeSelection).forEach(element => {
            element.addEventListener('click', event => {
                let target = event.target;
                this.switchMode(target.value);
            });
        });

        let mode = this.persistentState.get('mode') || 'review';
        if (mode == 'transcribe' || mode == 'review') {
            this.currentMode = mode;
            $$('button', this.modeSelection).forEach(button => {
                button.classList.toggle('active', button.value == mode);
            });
        }
    }

    switchMode(newMode) {
        console.info(`Switch mode from ${this.currentMode} to ${newMode}`);
        this.currentMode = newMode;
        this.appElement.dataset.mode = this.currentMode;
        this.addToState('mode', this.currentMode);
        this.queuedAssetPageURLs.length = 0;

        $$('button', this.modeSelection).forEach(button => {
            button.classList.toggle('active', button.value == newMode);
        });

        $$('.current-mode').forEach(i => (i.textContent = this.currentMode));

        this.updateAvailableCampaignFilters();
        this.closeViewer();
        this.refreshData();
    }

    // FIXME: replace with a generic function since we need to both show these side panels and hide the inactive ones
    setupToolbars() {
        let helpToggle = $('#help-toggle');
        let helpPanel = $('#help-panel');

        helpToggle.addEventListener('click', () => {
            helpPanel.toggleAttribute('hidden');
            helpToggle.classList.toggle('hidden');
            return false;
        });

        let assetListToggle = $('#asset-list-toggle');
        let assetList = $('#asset-list-container');

        assetListToggle.addEventListener('click', () => {
            assetList.toggleAttribute('hidden');
            assetListToggle.classList.toggle('hidden');
            return false;
        });
    }

    setupSharing() {
        /*
            We share the share button toolbar with the traditional HTML UI but
            we need to update it from .openViewer(). This is done by saving the
            initial button <a> tags with their placeholder href values and then
            updating them each time they change.
        */
        this.sharingButtons = $(
            '.concordia-share-button-group',
            this.appElement
        );

        $$('a[href]', this.sharingButtons).forEach(anchor => {
            // We use getAttribute to get the bare value without the normal
            // browser relative URL resolution so we can recognize an unescaped
            // URL value:
            anchor.dataset.urlTemplate = anchor.getAttribute('href');
        });
    }

    updateSharing(url, title) {
        $$('a[href]', this.sharingButtons).forEach(anchor => {
            let template = anchor.dataset.urlTemplate;
            if (template.indexOf('SHARE_URL') === 0) {
                // The bare URL doesn't require URL encoding
                anchor.href = url;
            } else {
                anchor.href = template
                    .replace('SHARE_URL', encodeURIComponent(url))
                    .replace('SHARE_TITLE', encodeURIComponent(title));
            }
        });
    }

    connectAssetEventStream() {
        let assetSocketURL = this.config.urls.assetUpdateSocket;
        console.info(`Connecting to ${assetSocketURL}`);
        let assetSocket = (this.assetSocket = new WebSocket(assetSocketURL));

        assetSocket.addEventListener('message', rawMessage => {
            console.debug('Asset socket message:', rawMessage);

            let data = JSON.parse(rawMessage.data);
            let message = data.message;
            let assetId = message.asset_pk.toString();

            switch (message.type) {
                case 'asset_update': {
                    let assetUpdate = {
                        sent: data.sent,
                        difficulty: message.difficulty,
                        latest_transcription: message.latest_transcription,
                        status: message.status
                    };

                    this.mergeAssetUpdate(assetId, assetUpdate);

                    break;
                }
                case 'asset_reservation_obtained':
                    /*
                    If the user is anonymous, or if the user is logged in and
                    is not the same as the user who obtained the reservation,
                    then mark it unavailable
                    */

                    this.mergeAssetUpdate(assetId, {
                        reservationToken: message.reservation_token
                    });

                    break;
                case 'asset_reservation_released':
                    this.mergeAssetUpdate(assetId, {
                        reservationToken: null
                    });

                    break;
                default:
                    console.warn(
                        `Unknown message type ${message.type}: ${message}`
                    );
            }

            let assetListItem = this.assetList.lookup[assetId];
            if (assetListItem) {
                // If this is visible, we want to update the displayed asset
                // list icon using the current value:
                assetListItem.update(this.assets.get(assetId));
            }
        });

        assetSocket.addEventListener('error', event => {
            console.error('Asset socket error occurred:', event);
        });

        assetSocket.onclose = event => {
            console.warn('Asset socket closed:', event);
            window.setTimeout(this.connectAssetEventStream.bind(this), 1000);
        };
    }

    refreshData() {
        console.time('Refreshing asset editability');

        this.assets.forEach(asset => {
            asset.editable = this.canEditAsset(asset);
        });

        console.timeEnd('Refreshing asset editability');

        this.updateAssetList();
        this.fetchAssetData(); // This starts the fetch process going by calculating the appropriate base URL
    }

    setupAssetList() {
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

        this.assetList = new AssetList(this.assets, {
            open: targetElement => this.openViewer(targetElement)
        });
        mount($('#asset-list-container'), this.assetList, loadMoreButton);

        /* List sorting */
        this.sortModeSelector = $('#sort-mode');
        setSelectValue(this.sortModeSelector, this.persistentState.get('sort'));
        this.sortMode = this.sortModeSelector.value;
        this.sortModeSelector.addEventListener('change', () => {
            this.addToState('sort', this.sortModeSelector.value);
            this.updateAssetList();
        });

        /* List filtering */
        this.campaignSelect = $('#selected-campaign');
        fetchJSON(this.config.urls.campaignList)
            .then(data => {
                data.objects.forEach(campaign => {
                    let o = document.createElement('option');
                    o.value = campaign.id;
                    o.textContent = campaign.title;

                    // TODO: this does not handle the case where the last assets of a campaign change state while the app is open
                    Object.entries(campaign.asset_stats).forEach(
                        ([key, value]) => {
                            o.dataset[key] = value;
                        }
                    );

                    this.campaignSelect.appendChild(o);
                });
            })
            .then(() => {
                setSelectValue(
                    this.campaignSelect,
                    this.persistentState.get('campaign')
                );
                this.updateAvailableCampaignFilters();
            });

        this.campaignSelect.addEventListener('change', () => {
            this.addToState('campaign', this.campaignSelect.value);
            this.updateAssetList();
        });

        $('#asset-list-thumbnail-size').addEventListener('input', event => {
            this.assetList.el.style.setProperty(
                '--asset-thumbnail-size',
                event.target.value + 'px'
            );
            this.attemptAssetLazyLoad();
        });
    }

    updateAvailableCampaignFilters() {
        /*
            Ensure that the list of campaign filter values only contains
            campaigns which you can actually work on
        */

        $$('option', this.campaignSelect).forEach(optionElement => {
            let disabled;
            if (this.campaignSelect == 'review') {
                disabled = optionElement.dataset.submitted_count == '0';
            } else {
                disabled =
                    optionElement.dataset.not_started_count == '0' &&
                    optionElement.dataset.in_progress_count == '0';
            }
            optionElement.toggleAttribute('disabled', disabled);
        });
    }

    setupAssetViewer() {
        this.assetViewer = new AssetViewer(this.handleAction.bind(this));

        mount($('#editor-main'), this.assetViewer);

        $('#close-viewer-button').addEventListener('click', () => {
            this.closeViewer();
        });

        this.assetViewSplitter = Split(['#viewer-column', '#editor-column'], {
            sizes: [50, 50],
            minSize: 300,
            gutterSize: 8,
            elementStyle: function(dimension, size, gutterSize) {
                return {
                    'flex-basis': 'calc(' + size + '% - ' + gutterSize + 'px)'
                };
            },
            gutterStyle: function(dimension, gutterSize) {
                return {
                    'flex-basis': gutterSize + 'px'
                };
            }
        });
    }

    fetchAssetData() {
        let url = this.urlTemplates.assetData.expand({
            action: this.currentMode
        });

        return this.fetchAssetPage(url);
    }

    fetchAssetPage(url) {
        let startingMode = this.currentMode;

        return fetchJSON(url)
            .then(data => {
                data.objects.forEach(i => {
                    i.sent = data.sent;
                    this.createAsset(i);
                });

                if (this.currentMode != startingMode) {
                    console.warn(
                        `Mode changed from ${startingMode} to ${
                            this.currentMode
                        } while request for ${url} was being processed; halting chained fetches`
                    );
                } else {
                    if (data.pagination.next) {
                        this.queuedAssetPageURLs.push(data.pagination.next);
                    }

                    if (this.assets.size < 300) {
                        // We like to have a fair number of items to start with
                        window.requestIdleCallback(
                            this.fetchNextAssetPage.bind(this)
                        );
                    }
                }
            })
            .then(() => {
                window.requestAnimationFrame(() => {
                    this.updateAssetList();
                });
            });
    }

    fetchNextAssetPage() {
        if (this.queuedAssetPageURLs.length > 0) {
            this.fetchAssetPage(this.queuedAssetPageURLs.pop());
        }
    }

    getCachedItem(objectReference) {
        return getCachedData(this.items, objectReference, 'item');
    }

    getCachedProject(objectReference) {
        return getCachedData(this.projects, objectReference, 'project');
    }

    getCachedCampaign(objectReference) {
        return getCachedData(this.campaigns, objectReference, 'object');
    }

    mergeAssetUpdate(assetId, newData) {
        /*
            We have two sources of data: JSON API requests and WebSocket
            updates. The WebSocket updates may be more recent depending on how
            long it takes an XHR request to return but the API responses have
            the full object representation.

            We will generate the merged record by taking creating a copy of the
            old data and new data and then selectively picking the most recent
            of the fields which frequently change.
        */

        let oldData = this.assets.get(assetId) || {};
        let mergedData = Object.assign({}, oldData);
        mergedData = Object.assign(mergedData, newData);

        let freshestCopy;
        if (oldData.sent && oldData.sent > newData.sent) {
            console.warn(
                'Updated data is older than our existing record:',
                newData,
                oldData
            );
            freshestCopy = oldData;
        } else {
            freshestCopy = newData;
        }

        for (let k of ['status', 'difficulty', 'latest_transcription']) {
            if (k in freshestCopy) {
                mergedData[k] = freshestCopy[k];
            }
        }

        mergedData.editable = this.canEditAsset(mergedData);

        this.assets.set(assetId, mergedData);
    }

    createAsset(assetData) {
        // n.b. although we are currently using numeric keys, we're coding under
        // the assumption that they will become opaque strings in the future:
        let assetId = assetData.id.toString();

        this.mergeAssetUpdate(assetId, assetData);
    }

    canEditAsset(assetObjectOrID) {
        /*
             Check whether an asset can possibly be edited by the current user

             Note that this does not account for transient reasons why editing
             might be disabled, such as waiting for an AJAX operation to
             complete or obtaining a reservation. The results of this check are
             intended to be current until the next time the asset's metadata
             changes, which means that it should be queried again after
             mergeAssetUpdate completes.
        */

        let asset, assetID;

        if (typeof assetObjectOrID == 'string') {
            assetID = assetObjectOrID;
            asset = this.assets.get(assetObjectOrID);
        } else {
            asset = assetObjectOrID;
            assetID = asset.id;
        }

        if (!asset) {
            throw `No information for an asset with ID ${assetID}`;
        }

        let canEdit = true;
        let reason = '';

        if (asset.status == 'completed') {
            reason = 'This page has already been completed';
            canEdit = false;
        } else if (this.currentMode == 'review') {
            if (asset.status != 'submitted') {
                reason = 'This page has not been submitted for review';
                canEdit = false;
            } else if (!this.config.currentUser) {
                reason = 'Anonymous users cannot review';
                canEdit = false;
            } else if (!asset.latest_transcription) {
                reason = 'no transcription';
                canEdit = false;
            } else if (
                asset.latest_transcription.submitted_by ==
                this.config.currentUser
            ) {
                reason =
                    'Transcriptions must be reviewed by a different person';
                canEdit = false;
            }
        } else if (this.currentMode == 'transcribe') {
            if (asset.status == 'submitted') {
                canEdit = false;
                reason = 'This page has been submitted for review';
            } else if (
                asset.status != 'not_started' &&
                asset.status != 'in_progress'
            ) {
                canEdit = false;
                reason = `Page with status ${
                    asset.status
                } are not available for transcription`;
            }
        } else {
            throw `Unexpected mode ${this.currentMode}`;
        }

        if (
            asset.reservationToken &&
            asset.reservationToken != this.config.reservationToken
        ) {
            canEdit = false;
            reason = 'Somebody else is working on this page';
        }

        console.debug(
            'Asset ID %s: editable=%s, reason="%s"',
            assetID,
            canEdit,
            reason
        );

        return {canEdit, reason};
    }

    updateAssetList(alwaysIncludedAssets) {
        if (!alwaysIncludedAssets) {
            alwaysIncludedAssets = [];
        }

        if (this.appElement.dataset.openAssetId) {
            alwaysIncludedAssets.push(
                Number(this.appElement.dataset.openAssetId)
            );
        }

        window.requestIdleCallback(() => {
            console.time('Filtering assets');
            let visibleAssets = this.getVisibleAssets(alwaysIncludedAssets);
            console.timeEnd('Filtering assets');

            console.time('Sorting assets');
            visibleAssets = this.sortAssets(visibleAssets);
            console.timeEnd('Sorting assets');

            window.requestAnimationFrame(() => {
                console.time('Updating asset list');
                this.assetList.update(visibleAssets);
                console.timeEnd('Updating asset list');

                this.assetList.scrollToActiveAsset();

                this.attemptAssetLazyLoad();
            });
        });
    }

    attemptAssetLazyLoad() {
        /*
            If the list is small enough to display without scrolling we'll
            attempt to load more assets in the background.
        */

        let el = this.assetList.el.parentNode;

        if (el.scrollHeight <= el.clientHeight) {
            window.requestIdleCallback(this.fetchNextAssetPage.bind(this));
        }
    }

    sortAssets(assetList) {
        let sortMode = (this.sortMode = this.sortModeSelector.value);

        let keyFromAsset;
        switch (sortMode) {
            case 'hardest':
                keyFromAsset = asset => -1 * asset.difficulty;
                break;
            case 'easiest':
                keyFromAsset = asset => asset.difficulty;
                break;
            case 'campaign':
                // Sort by Campaign using sub-values for stable ordering
                keyFromAsset = asset => [
                    asset.campaign.title,
                    asset.project.title,
                    asset.item.title,
                    asset.id
                ];
                break;
            case 'item-id':
                keyFromAsset = asset => asset.item.item_id;
                break;
            case 'recent':
                keyFromAsset = asset => [asset.sent, asset.id];
                break;
            case 'year':
                keyFromAsset = asset => asset.year;
                break;
            default:
                console.warn(`Unknown sort mode ${sortMode}; using asset ID…`);
                keyFromAsset = asset => asset.id;
        }

        return assetList.sort((a, b) => {
            let aKey = keyFromAsset(a),
                bKey = keyFromAsset(b);
            if (aKey < bKey) {
                return -1;
            } else if (aKey > bKey) {
                return 1;
            } else {
                return 0;
            }
        });
    }

    getVisibleAssets(alwaysIncludedAssetIDs) {
        // We allow passing a list of asset IDs which should always be included
        // to avoid jarring UI transitions (the display code is responsible for
        // badging these as unavailable):
        if (!alwaysIncludedAssetIDs) {
            alwaysIncludedAssetIDs = [];
        }

        if (this.persistentState.has('asset')) {
            alwaysIncludedAssetIDs.push(this.persistentState.get('asset'));
        }

        let currentCampaignId = this.campaignSelect.value;
        if (currentCampaignId) {
            // The values specified in API responses are integers, not DOM strings:
            currentCampaignId = parseInt(currentCampaignId, 10);
        }

        let currentStatuses;
        let currentMode = this.currentMode;
        if (currentMode == 'review') {
            currentStatuses = ['submitted'];
        } else if (currentMode == 'transcribe') {
            currentStatuses = ['not_started', 'in_progress'];
        } else {
            throw `Don't know how to filter assets for unrecognized ${currentMode} mode`;
        }

        // Selection criteria: asset metadata has been fully loaded (we're using thumbnailUrl as a proxy for that) and the status is in-scope
        let visibleAssets = [];

        for (let asset of this.assets.values()) {
            if (!alwaysIncludedAssetIDs.includes(asset.id)) {
                if (!asset.thumbnailUrl) {
                    continue;
                }

                if (
                    currentCampaignId &&
                    asset.campaign.id != currentCampaignId
                ) {
                    continue;
                }

                if (!currentStatuses.includes(asset.status)) {
                    continue;
                }
            }

            visibleAssets.push(asset);
        }

        return visibleAssets;
    }

    openViewer(assetElement) {
        if (this.openAssetElement) {
            this.closeViewer();
        }

        let asset = this.assets.get(assetElement.dataset.id);

        this.addToState('asset', asset.id);

        this.updateSharing(asset.url, asset.title);

        // FIXME: refactor openAssetElement into a single open asset ID property & pass it to the respective list & viewer components
        this.openAssetElement = assetElement;

        let {canEdit} = this.canEditAsset(asset);

        if (canEdit) {
            this.assetReservationURL = this.urlTemplates.assetReservation.expand(
                {
                    assetId: encodeURIComponent(asset.id)
                }
            );

            this.reserveAsset();
            this.reservationTimer = window.setInterval(
                this.reserveAsset.bind(this),
                30000
            );
        }

        this.metadataPanel = new MetadataPanel(asset);
        mount(
            $('#asset-info-modal .modal-body', this.appElement),
            this.metadataPanel
        );

        this.getCachedItem(asset.item).then(itemInfo => {
            this.metadataPanel.itemMetadata.update(itemInfo);
            this.updateSharing(asset.url, itemInfo.title);
        });

        this.getCachedProject(asset.project).then(projectInfo => {
            this.metadataPanel.projectMetadata.update(projectInfo);
        });

        this.getCachedCampaign(asset.campaign).then(campaignInfo => {
            this.metadataPanel.campaignMetadata.update(campaignInfo);
        });

        window.requestAnimationFrame(() => {
            // This will trigger the CSS which displays the viewer:
            this.appElement.dataset.openAssetId = asset.id;

            this.assetList.setActiveAsset(assetElement);

            this.updateViewer();
        });
    }

    updateViewer() {
        if (!this.appElement.dataset.openAssetId || !this.openAssetElement) {
            console.warn('updateViewer() called without an open asset');
            return;
        }

        let openAssetId = this.appElement.dataset.openAssetId;
        let asset = this.assets.get(openAssetId);

        let {canEdit, reason} = this.canEditAsset(asset);

        if (this.assetReservationInProgress) {
            canEdit = false;
            reason = 'Page reservation in progress';
        } else {
            if (!this.assetReserved) {
                canEdit = false;
                reason = 'Somebody else is working on this page.';
            }
        }

        if (this.actionSubmissionInProgress) {
            canEdit = false;
            reason = 'Your action is being processed';
        }

        this.assetViewer.update({
            editable: {canEdit, reason},
            mode: this.currentMode,
            asset
        });
    }

    closeViewer() {
        this.releaseAsset();

        delete this.appElement.dataset.openAssetId;
        delete this.openAssetElement;

        this.deleteFromState('asset');

        if (this.reservationTimer) {
            window.clearInterval(this.reservationTimer);
        }

        if (this.metadataPanel) {
            conditionalUnmount(this.metadataPanel);
        }

        this.assetList.scrollToActiveAsset();
    }

    reserveAsset() {
        if (!this.assetReservationURL) {
            console.warn('reserveAsset called without asset reservation URL!');
            return;
        }

        let reservationURL = this.assetReservationURL;
        this.assetReservationInProgress = true;
        jQuery
            .ajax({
                url: reservationURL,
                type: 'POST',
                dataType: 'json'
            })
            .done(() => {
                if (!this.openAssetElement) {
                    throw 'Open asset was closed with a reservation request pending';
                }

                if (reservationURL != this.assetReservationURL) {
                    throw `Asset changed while reserving ${reservationURL} != ${
                        this.assetReservationURL
                    }`;
                }
                this.assetReservationInProgress = false;
                this.assetReserved = true;
                this.updateViewer();
            })
            .fail((jqXHR, textStatus, errorThrown) => {
                console.error(
                    'Unable to reserve asset: %s %s',
                    textStatus,
                    errorThrown
                );
                this.assetReservationInProgress = false;
                this.assetReserved = false;
                this.updateViewer();
            });
    }

    releaseAsset() {
        if (!this.assetReservationURL) {
            console.warn('releaseAsset called without asset reservation URL!');
            return;
        }

        let payload = {
            release: true,
            csrfmiddlewaretoken: $('input[name="csrfmiddlewaretoken"]').value
        };

        navigator.sendBeacon(
            this.assetReservationURL,
            new Blob([jQuery.param(payload)], {
                type: 'application/x-www-form-urlencoded'
            })
        );

        delete this.assetReservationURL;
        delete this.assetReserved;
        delete this.assetReservationInProgress;

        this.updateViewer();
    }

    handleAction(action, data) {
        if (!this.appElement.dataset.openAssetId) {
            console.error(
                `Unexpected action with no open asset: ${action} with data ${data}`
            );
            return;
        } else {
            console.debug(`User action ${action} with data ${data}`);
        }

        let openAssetId = this.appElement.dataset.openAssetId;
        let asset = this.assets.get(openAssetId);
        let currentTranscriptionId = asset.latest_transcription
            ? asset.latest_transcription.id
            : null;

        let updateViews = () => {
            this.updateViewer();
            this.updateAssetList();
        };

        switch (action) {
            case 'save':
                this.postAction(
                    this.urlTemplates.saveTranscription.expand({
                        assetId: openAssetId
                    }),
                    {
                        text: data.text,
                        supersedes: currentTranscriptionId
                    }
                ).done(responseData => {
                    if (!asset.latest_transcription) {
                        asset.latest_transcription = {};
                    }
                    asset.latest_transcription.id = responseData.id;
                    asset.latest_transcription.text = responseData.text;
                    this.mergeAssetUpdate(responseData.asset.id, {
                        status: responseData.asset.status
                    });
                    updateViews();
                });
                break;
            case 'submit':
                if (!currentTranscriptionId) {
                    throw 'Asked to submit an undefined transcription!';
                }
                this.postAction(
                    this.urlTemplates.submitTranscription.expand({
                        transcriptionId: currentTranscriptionId
                    })
                ).done(responseData => {
                    this.mergeAssetUpdate(responseData.asset.id, {
                        status: responseData.asset.status
                    });
                    updateViews();
                });
                break;
            case 'accept':
                this.postAction(
                    this.urlTemplates.reviewTranscription.expand({
                        transcriptionId: currentTranscriptionId
                    }),
                    {action: 'accept'}
                ).done(responseData => {
                    this.mergeAssetUpdate(responseData.asset.id, {
                        status: responseData.asset.status
                    });
                    this.releaseAsset();
                    updateViews();
                });
                break;
            case 'reject':
                this.postAction(
                    this.urlTemplates.reviewTranscription.expand({
                        transcriptionId: currentTranscriptionId
                    }),
                    {action: 'reject'}
                ).done(responseData => {
                    this.mergeAssetUpdate(responseData.asset.id, {
                        status: responseData.asset.status
                    });
                });
                break;
            default:
                console.error(`Unknown action ${action} with data ${data}`);
        }
    }

    postAction(url, payload) {
        this.actionSubmissionInProgress = true;
        this.updateViewer();

        // FIXME: switch to Fetch API once we add CSRF compatibility
        return jQuery
            .ajax({
                url: url,
                method: 'POST',
                dataType: 'json',
                data: payload
            })
            .always(() => {
                this.actionSubmissionInProgress = false;
                this.updateViewer();
            })
            .fail(function(jqXHR, textStatus) {
                if (jqXHR.status == 401) {
                    alert(
                        '// FIXME: the CAPTCHA system is not implemented yet. Please hit the main site before returning to this page'
                    );
                }

                console.error(
                    'POSTed action to %s failed: %s %s',
                    url,
                    textStatus,
                    jqXHR.responseJSON
                        ? jqXHR.responseJSON.error
                        : jqXHR.responseText
                );
            });
    }
}
