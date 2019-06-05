/* global Split jQuery URITemplate sortBy Sentry */
/* eslint-disable no-console */

import {mount} from 'https://cdnjs.cloudflare.com/ajax/libs/redom/3.18.0/redom.es.min.js';
import {
    Alert,
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

        this.alerts = {};

        /*
            These will store *all* metadata retrieved from the API so it can be
            easily queried and updated.
        */
        this.assets = new Map();
        this.items = new Map();
        this.projects = new Map();
        this.campaigns = new Map();

        this.touchedAssetIDs = new Set();

        this.setupGlobalKeyboardEvents();

        this.setupSidebar();

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

    reportError(category, header, body) {
        let alert;

        if (!this.alerts.hasOwnProperty(category)) {
            alert = new Alert();
            this.alerts[category] = alert;
            mount(document.body, alert);
            jQuery(alert.el)
                .alert()
                .on('closed.bs.alert', () => {
                    delete this.alerts[category];
                });
        } else {
            alert = this.alerts[category];
        }

        alert.update(header, body);
    }

    clearError(category) {
        if (this.alerts.hasOwnProperty(category)) {
            jQuery(this.alerts[category].el).alert('close');
        }
    }

    clearAllErrors() {
        Object.keys(this.alerts).forEach(category => this.clearError(category));
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
        if (key == 'campaign') {
            this.persistentState.delete('topic');
        } else if (key == 'topic') {
            this.persistentState.delete('campaign');
        }
        this.serializeStateToURL();
    }

    deleteFromState(key) {
        this.persistentState.delete(key);
        this.serializeStateToURL();
    }

    getAssetData(assetId) {
        // Convenience accessor which type-checks
        if (typeof assetId != 'number') {
            assetId = Number(assetId);
        }

        return this.assets.get(assetId);
    }

    restoreOpenAsset() {
        let assetId = this.persistentState.get('asset');
        if (!assetId) {
            return;
        }

        let assetDataURL = new URL(
            this.urlTemplates.assetData.expand({
                // This is a special-case for retrieving all assets regardless of status
                action: 'assets'
            }),
            document.location.href
        );

        assetDataURL.searchParams.set('pk', assetId);

        this.fetchAssetPage(assetDataURL).then(() => {
            this.assetList.updateCallbacks.push(() => {
                let element = document.getElementById(assetId);
                if (!element) {
                    console.warn('Expected to load asset with ID %s', assetId);
                } else {
                    this.openViewer(assetId);
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
                        // text field so we'll open the help sidebar:
                        document.getElementById('help-toggle').click();
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
        if (mode != 'transcribe' && mode != 'review') {
            if (window.Sentry) {
                Sentry.captureMessage(
                    `Setup requested for unknown ${mode} mode`
                );
            }
            mode = 'review';
        }
        this.switchMode(mode);
    }

    switchMode(newMode) {
        // We'll distinguish between the initial mode setup and transitions:
        let modeChanged = this.currentMode && this.currentMode != newMode;

        console.info(
            `switching to mode ${newMode} (previously ${this.currentMode})`
        );

        this.currentMode = newMode;
        this.appElement.dataset.mode = this.currentMode;
        this.addToState('mode', this.currentMode);

        $$('button', this.modeSelection).forEach(button => {
            button.classList.toggle('active', button.value == newMode);
        });

        $$('.current-mode').forEach(i => (i.textContent = this.currentMode));

        this.updateAvailableCampaignFilters();

        if (modeChanged) {
            this.queuedAssetPageURLs.length = 0;
            this.closeViewer();
            this.refreshData();
        }
    }

    setupSidebar() {
        let sidebar = $('#action-app-sidebar');
        let buttons = $$('.btn', sidebar);

        let hideTarget = (button, force) => {
            let target = document.getElementById(button.dataset.target);
            let hidden = target.toggleAttribute('hidden', force);
            button.classList.toggle('active', !hidden);
            if (button.classList.contains('active')) {
                button.setAttribute('aria-selected', 'true');
            } else {
                button.setAttribute('aria-selected', 'false');
            }
            return hidden;
        };

        let toggleButton = clickedButton => {
            let hidden = hideTarget(clickedButton);

            if (!hidden) {
                // If we just made something visible we'll hide any other button's targets
                // as long as they aren't pinned to apply only when an asset is open:
                buttons
                    .filter(button => button != clickedButton)
                    .filter(
                        button =>
                            this.openAssetId ||
                            !('toggleableOnlyWhenOpen' in button.dataset)
                    )
                    .forEach(button => {
                        hideTarget(button, true);
                    });
            }
        };

        buttons.forEach(button => {
            button.addEventListener('click', event => {
                toggleButton(event.currentTarget);
            });
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
            let assetId = message.asset_pk;

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

                    if (this.openAssetId && this.openAssetId == assetId) {
                        this.reserveAsset();
                    }

                    break;
                default:
                    console.warn(
                        `Unknown message type ${message.type}: ${message}`
                    );
            }

            if (this.openAssetId && assetId == this.openAssetId) {
                // Someone may be looking at an asset even if they have not
                // locked it and this provides real-time updates:
                this.updateViewer();
            }

            let assetListItem = this.assetList.lookup[assetId];
            if (assetListItem) {
                // If this is visible, we want to update the displayed asset
                // list icon using the current value:
                assetListItem.update(this.getAssetData(assetId));
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

        this.assetList = new AssetList({
            getAssetData: assetId => this.getAssetData(assetId),
            open: targetElement => this.openViewer(targetElement.id)
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
                let campaignOptGroup = document.createElement('optgroup');
                campaignOptGroup.label = 'Campaigns';
                this.campaignSelect.appendChild(campaignOptGroup);
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

                    campaignOptGroup.appendChild(o);
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
            let campaignOrTopic = this.getSelectedOptionType();
            this.addToState(campaignOrTopic, this.campaignSelect.value);
            this.updateAssetList();
        });

        fetchJSON(this.config.urls.topicList)
            .then(data => {
                let topicOptGroup = document.createElement('optgroup');
                topicOptGroup.label = 'Topics';
                topicOptGroup.classList.add('topic-optgroup');
                this.campaignSelect.appendChild(topicOptGroup);

                data.objects.forEach(topic => {
                    let o = document.createElement('option');
                    o.value = topic.id;
                    o.textContent = topic.title;

                    // TODO: this does not handle the case where the last assets of a topic change state while the app is open
                    Object.entries(topic.asset_stats).forEach(
                        ([key, value]) => {
                            o.dataset[key] = value;
                        }
                    );

                    topicOptGroup.appendChild(o);
                });
            })
            .then(() => {
                this.updateAvailableCampaignFilters();
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

        $('#viewer-help').addEventListener('click', () => {
            document.getElementById('help-toggle').click();
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

        let oldData = this.getAssetData(assetId) || {};
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
        let assetId = assetData.id;
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
            asset = this.getAssetData(assetObjectOrID);
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
            reason = 'This page has been completed';
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

    updateAssetList() {
        window.requestIdleCallback(() => {
            console.time('Filtering assets');
            let visibleAssets = this.getVisibleAssets();
            console.timeEnd('Filtering assets');

            console.time('Sorting assets');
            visibleAssets = this.sortAssets(visibleAssets);
            console.timeEnd('Sorting assets');

            window.requestAnimationFrame(() => {
                console.time('Updating asset list');
                this.assetList.update(visibleAssets);
                console.timeEnd('Updating asset list');

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
                keyFromAsset = asset => [-asset.sent, asset.id];
                break;
            case 'year':
                keyFromAsset = asset => asset.year;
                break;
            default:
                console.warn(`Unknown sort mode ${sortMode}; using asset ID…`);
                keyFromAsset = asset => asset.id;
        }

        return sortBy(assetList, keyFromAsset);
    }

    getSelectedOptionType() {
        let campaignOrTopic = 'campaign';

        if (
            this.campaignSelect.options[
                this.campaignSelect.selectedIndex
            ].parentElement.classList.contains('topic-optgroup')
        ) {
            campaignOrTopic = 'topic';
        }

        return campaignOrTopic;
    }

    assetHasTopic(asset, topicId) {
        for (let topic in asset.topics) {
            if (topic.id === topicId) {
                return true;
            }
        }
        return false;
    }

    getVisibleAssets() {
        // We allow passing a list of asset IDs which should always be included
        // to avoid jarring UI transitions (the display code is responsible for
        // badging these as unavailable):

        let alwaysIncludedAssetIDs = new Set(this.touchedAssetIDs);

        if (this.openAssetId) {
            alwaysIncludedAssetIDs.add(this.openAssetId);
        }

        if (this.persistentState.has('asset')) {
            alwaysIncludedAssetIDs.add(this.persistentState.get('asset'));
        }

        let currentCampaignSelectValue = this.campaignSelect.value;
        let currentCampaignId;
        let currentTopicId;
        if (currentCampaignSelectValue) {
            let campaignOrTopic = this.getSelectedOptionType();
            currentCampaignSelectValue = parseInt(
                currentCampaignSelectValue,
                10
            );

            // The values specified in API responses are integers, not DOM strings:
            if (campaignOrTopic == 'campaign') {
                currentCampaignId = currentCampaignSelectValue;
            } else {
                currentTopicId = currentCampaignSelectValue;
            }
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
            if (!alwaysIncludedAssetIDs.has(asset.id)) {
                if (!asset.thumbnailUrl) {
                    continue;
                }

                if (
                    currentCampaignId &&
                    asset.campaign.id != currentCampaignId
                ) {
                    continue;
                }

                if (
                    currentTopicId &&
                    !this.assetHasTopic(asset, currentTopicId)
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

    openViewer(assetId) {
        if (this.openAssetId) {
            this.closeViewer();
        }

        let asset = this.getAssetData(assetId);

        this.openAssetId = asset.id;

        this.addToState('asset', asset.id);

        this.updateSharing(asset.url, asset.title);

        this.assetReservationURL = this.urlTemplates.assetReservation.expand({
            assetId: encodeURIComponent(asset.id)
        });

        this.reserveAsset();
        this.reservationTimer = window.setInterval(
            this.reserveAsset.bind(this),
            30000
        );

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
            this.appElement.dataset.openAssetId = this.openAssetId;

            this.assetList.setActiveAsset(
                document.getElementById(this.openAssetId)
            );

            this.updateViewer();
        });
    }

    updateViewer() {
        if (!this.openAssetId) {
            console.warn('updateViewer() called without an open asset');
            return;
        }

        let asset = this.getAssetData(this.openAssetId);

        let {canEdit, reason} = this.canEditAsset(asset);

        if (canEdit && !this.assetReserved) {
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
        delete this.openAssetId;

        this.deleteFromState('asset');

        if (this.reservationTimer) {
            window.clearInterval(this.reservationTimer);
        }

        if (this.metadataPanel) {
            conditionalUnmount(this.metadataPanel);
        }

        this.clearAllErrors();

        this.assetList.scrollToActiveAsset();
    }

    reserveAsset() {
        if (!this.openAssetId) {
            console.warn('reserveAsset called without an open asset?');
            return;
        }

        let asset = this.getAssetData(this.openAssetId);
        let {canEdit, reason} = this.canEditAsset(asset);

        if (!canEdit) {
            console.info(`Asset ${asset.id} cannot be edited: ${reason}`);
            return;
        }

        if (!this.assetReservationURL) {
            console.warn('reserveAsset called without asset reservation URL!');
            return;
        }

        let reservationURL = this.assetReservationURL;

        // TODO: record the last asset renewal time and don't renew early unless the ID has changed

        jQuery
            .ajax({
                url: reservationURL,
                type: 'POST',
                dataType: 'json'
            })
            .done(() => {
                if (
                    !this.openAssetId ||
                    reservationURL != this.assetReservationURL
                ) {
                    console.warn(
                        `User navigated before reservation for asset #${
                            asset.id
                        } was obtained: open asset ID = ${this.openAssetId}`
                    );

                    this.releaseReservationURL(reservationURL);
                }

                this.clearError('reservation');

                this.assetReserved = true;
                this.updateViewer();
            })
            .fail((jqXHR, textStatus, errorThrown) => {
                if (jqXHR.status != 409) {
                    console.error(
                        'Unable to reserve asset: %s %s',
                        textStatus,
                        errorThrown
                    );

                    this.reportError(
                        'reservation',
                        `Unable to reserve asset`,
                        errorThrown
                            ? `${textStatus}: ${errorThrown}`
                            : textStatus
                    );
                }

                this.assetReserved = false;
                this.updateViewer();
            });
    }

    releaseAsset() {
        if (!this.assetReservationURL) {
            return;
        }

        this.releaseReservationURL(this.assetReservationURL);

        delete this.assetReservationURL;
        delete this.assetReserved;

        this.updateViewer();
    }

    releaseReservationURL(assetReservationURL) {
        // Handle the low-level details of releasing an asset reservation

        let payload = {
            release: true,
            csrfmiddlewaretoken: $('input[name="csrfmiddlewaretoken"]').value
        };

        navigator.sendBeacon(
            assetReservationURL,
            new Blob([jQuery.param(payload)], {
                type: 'application/x-www-form-urlencoded'
            })
        );
    }

    handleAction(action, data) {
        if (!this.openAssetId) {
            console.error(
                `Unexpected action with no open asset: ${action} with data ${data}`
            );
            return;
        } else {
            console.debug(`User action ${action} with data ${data}`);
        }

        let asset = this.getAssetData(this.openAssetId);
        let currentTranscriptionId = asset.latest_transcription
            ? asset.latest_transcription.id
            : null;

        let updateViews = () => {
            this.updateViewer();
            this.updateAssetList();
        };

        this.touchedAssetIDs.add(asset.id);

        switch (action) {
            case 'save':
                this.postAction(
                    this.urlTemplates.saveTranscription.expand({
                        assetId: this.openAssetId
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
                        sent: responseData.sent,
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
                        sent: responseData.sent,
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
                        sent: responseData.sent,
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
                        sent: responseData.sent,
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
            .done(() => {
                this.clearError('user-action');
            })
            .fail((jqXHR, textStatus) => {
                if (jqXHR.status == 401) {
                    alert(
                        '// FIXME: the CAPTCHA system is not implemented yet. Please hit the main site before returning to this page'
                    );
                }

                let details = jqXHR.responseJSON
                    ? jqXHR.responseJSON.error
                    : jqXHR.responseText;

                if (!details) {
                    details = textStatus;
                }

                console.error(
                    'POSTed action to %s failed: %s %s',
                    url,
                    textStatus,
                    details
                );

                this.reportError(
                    'user-action',
                    'Unable to save your work',
                    details
                );
            });
    }
}
