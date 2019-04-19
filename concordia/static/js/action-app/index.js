/* global OpenSeadragon Split jQuery URITemplate */
/* eslint-disable no-console */

import {
    mount,
    unmount
} from 'https://cdnjs.cloudflare.com/ajax/libs/redom/3.18.0/redom.es.min.js';

import {$, $$} from './utils/dom.js';
import {fetchJSON, getCachedData} from './utils/api.js';
import {MetadataPanel, AssetList, AssetViewer} from './components.js';

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

        this.setupModeSelector();
        this.setupAssetList();
        this.setupAssetViewer();

        this.connectAssetEventStream();

        this.refreshData();
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
                $$('button', this.modeSelection).forEach(inactiveElement => {
                    inactiveElement.classList.remove('active');
                });
                event.target.classList.add('active');
                this.updateAvailableCampaignFilters();
                this.closeViewer();
                this.refreshData();
            });
        });
    }

    getCurrentMode() {
        this.currentMode = this.modeSelection.querySelector('.active').value;
        this.appElement.dataset.mode = this.currentMode;
        $$('.current-mode').forEach(i => (i.textContent = this.currentMode));
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
                    if (
                        !this.config.currentUser ||
                        (this.config.currentUser &&
                            this.config.currentUser != message.user_pk)
                    ) {
                        alert('// FIXME: handle asset reservation updates');
                        this.markAssetAsUnavailable(
                            assetId,
                            'Someone else is working on this'
                        );
                    }
                    break;
                case 'asset_reservation_released':
                    // FIXME: we need to test whether the user who reserved it is different than the user we're running as!
                    alert('// FIXME: handle asset reservation updates');
                    this.markAssetAsAvailable(assetId);
                    break;
                default:
                    console.warn(
                        `Unknown message type ${message.type}: ${message}`
                    );
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
        this.getCurrentMode();
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
        this.sortMode = this.sortModeSelector.value;
        this.sortModeSelector.addEventListener('change', () => {
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
                this.updateAvailableCampaignFilters();
            });
        this.campaignSelect.addEventListener('change', () =>
            this.updateAssetList()
        );
    }

    updateAvailableCampaignFilters() {
        /*
            Ensure that the list of campaign filter values only contains
            campaigns which you can actually work on
        */

        // TODO: componentize the asset list controls
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
            showFlipControl: true,
            sequenceMode: true,
            toolbar: 'viewer-controls',
            zoomInButton: 'viewer-zoom-in',
            zoomOutButton: 'viewer-zoom-out',
            homeButton: 'viewer-home',
            fullPageButton: 'viewer-full-page',
            rotateLeftButton: 'viewer-rotate-left',
            rotateRightButton: 'viewer-rotate-right',
            nextButton: 'viewer-next-page',
            previousButton: 'viewer-previous-page',
            flipButton: 'viewer-flip'
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

        this.fetchAssetPage(url);
    }

    fetchAssetPage(url) {
        fetchJSON(url)
            .then(data => {
                data.objects.forEach(i => {
                    i.sent = data.sent;
                    this.createAsset(i);
                });

                $('#asset-count').textContent = this.assets.size;

                if (data.pagination.next) {
                    this.queuedAssetPageURLs.push(data.pagination.next);
                }

                if (this.assets.size < 300) {
                    // We like to have a fair number of items to start with
                    window.requestIdleCallback(
                        this.fetchNextAssetPage.bind(this)
                    );
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
            mergedData[k] = freshestCopy[k];
        }

        console.debug(
            `Changing asset ${assetId} from ${JSON.stringify(
                oldData
            )} to ${JSON.stringify(mergedData)}`
        );

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

        // FIXME: the mergeAssetUpdate() process should trigger a call to this & update the asset list & viewer
        // FIXME: decide what call signature will support specifying the displayed reason

        if (!asset) {
            throw `No information for an asset with ID ${assetID}`;
        }

        let canEdit = true;
        let reason = '';

        if (asset.status == 'completed') {
            reason = 'this asset has been completed';
            canEdit = false;
        } else if (this.currentMode == 'review') {
            if (asset.status != 'submitted') {
                reason = 'asset has not been submitted for review';
                canEdit = false;
            } else if (!this.config.currentUser) {
                reason = 'anonymous users cannot review';
                canEdit = false;
            } else if (!asset.latest_transcription) {
                reason = 'no transcription';
                canEdit = false;
            } else if (
                asset.latest_transcription.submitted_by ==
                this.config.currentUser
            ) {
                reason =
                    'transcriptions must be reviewed by a different person';
                canEdit = false;
            }
        } else if (this.currentMode == 'transcribe') {
            if (asset.status == 'submitted') {
                canEdit = false;
                reason = 'this asset has been submitted for review';
            } else if (
                asset.status != 'not_started' &&
                asset.status != 'in_progress'
            ) {
                canEdit = false;
                reason = 'this asset is not available for transcription';
            }
        } else {
            throw `Unexpected mode ${this.currentMode}`;
        }

        console.info(
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

                $('#visible-asset-count').textContent = visibleAssets.length;

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

        let currentCampaignId = this.campaignSelect.value;
        if (currentCampaignId) {
            // The values specified in API responses are integers, not DOM strings:
            currentCampaignId = parseInt(currentCampaignId, 10);
        }

        // TODO: We should have a cleaner way to filter the assets which are in scope due to the current status & having been fully loaded
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
        let asset = this.assets.get(assetElement.dataset.id);

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
        });

        this.getCachedProject(asset.project).then(projectInfo => {
            this.metadataPanel.projectMetadata.update(projectInfo);
        });

        this.getCachedCampaign(asset.campaign).then(campaignInfo => {
            this.metadataPanel.campaignMetadata.update(campaignInfo);
        });

        if (this.seadragonViewer.isOpen()) {
            this.seadragonViewer.close();
        }

        let tileSources = [
            {
                type: 'image',
                url: asset.imageUrl
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

        if (!this.assetReserved) {
            canEdit = false;
            reason = 'Asset reservation in progress';
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

        if (this.reservationTimer) {
            window.clearInterval(this.reservationTimer);
        }

        if (this.seadragonViewer.isOpen()) {
            this.seadragonViewer.close();
        }

        if (this.metadataPanel && this.metadataPanel.el.parentNode) {
            unmount(this.metadataPanel.el.parentNode, this.metadataPanel);
        }

        this.assetList.scrollToActiveAsset();
    }

    reserveAsset() {
        if (!this.assetReservationURL) {
            console.warn('reserveAsset called without asset reservation URL!');
            return;
        }

        let reservationURL = this.assetReservationURL;

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

                this.assetReserved = true;
                this.updateViewer();
            })
            .fail((jqXHR, textStatus, errorThrown) => {
                console.error(
                    'Unable to reserve asset: %s %s',
                    textStatus,
                    errorThrown
                );
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
