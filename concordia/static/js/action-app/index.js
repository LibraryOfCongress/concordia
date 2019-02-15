/* global OpenSeadragon */
/* eslint-disable no-console */

// import {html, render} from 'https://unpkg.com/lit-html?module';
import {
    html,
    text,
    mount
} from 'https://cdnjs.cloudflare.com/ajax/libs/redom/3.18.0/redom.es.min.js';

let $ = (selector, scope = document) => scope.querySelector(selector);

let $$ = (selector, scope = document) => {
    return Array.from(scope.querySelectorAll(selector));
};

let fetchJSON = originalURL => {
    let url = new URL(originalURL, window.location);
    let qs = url.searchParams;
    qs.set('format', 'json');
    let finalURL = `${url.origin}${url.pathname}?${qs}`;

    console.time(`Fetch ${url}`);

    return fetch(finalURL).then(response => {
        console.timeEnd(`Fetch ${url}`);
        return response.json();
    });
};

class AssetTooltip {
    constructor() {
        this.el = html('.asset-tooltip.text-white.p-2', [
            html('.item-title'),
            html('.asset-title'),
            html('.difficulty-score-container', [
                text('Difficulty Score: '),
                html('span.difficulty-score')
            ])
        ]);
    }
    update(asset) {
        $('.item-title', this.el).innerText = asset.item.title;
        $('.asset-title', this.el).innerText = 'Image ' + asset.sequence;
        $('.difficulty-score', this.el).innerText = asset.difficulty;
    }
}

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

        this.setupModeSelector();
        this.setupAssetList();
        this.setupAssetViewer();

        this.refreshData();
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
            });
        });
    }

    getCurrentMode() {
        this.currentMode = this.modeSelection.querySelector('.active').value;
        this.appElement.dataset.mode = this.currentMode;
    }

    refreshData() {
        this.getCurrentMode();
        this.assets.length = 0;
        this.resetAssetList();
        this.fetchAssetData();
    }

    resetAssetList() {
        while (this.assetList.firstChild) {
            this.assetList.removeChild(this.assetList.firstChild);
        }
    }

    setupAssetList() {
        this.assets = [];
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

        this.assetList.addEventListener('click', evt => {
            let target = evt.target;
            if (target && target.classList.contains('asset')) {
                this.openViewer(target);

                // TODO: stop using Bootstrap classes directly and toggle semantic classes only
                $$('.asset', this.assetList).forEach(elem => {
                    elem.classList.remove('asset-active');
                    elem.classList.remove('border-primary');
                });
                target.classList.add('asset-active');
                target.classList.add('border-primary');
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center',
                    inline: 'nearest'
                });
                return false;
            }
        });

        /* Tooltips */
        const tooltip = new AssetTooltip();

        this.assetList.addEventListener('mouseover', evt => {
            let target = evt.target;

            if (target && target.classList.contains('asset')) {
                const asset = this.assets[target.dataset.idx - 1];

                tooltip.update(asset);

                mount(target, tooltip);
            }
        });
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
            window.actionApp.closeViewer();
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
            $('#asset-count').innerText = this.assets.length;

            // FIXME: think about how we want demand loading / “I don't want to work on any of this” to behave
            if (data.pagination.next && this.assets.length < 100) {
                this.fetchAssetPage(data.pagination.next);
            }
        });
    }

    createAsset(assetData) {
        let newIdx = this.assets.push(assetData);

        let assetElement = document.createElement('div');
        assetElement.id = assetData.id;
        assetElement.classList.add('asset', 'rounded', 'border');
        assetElement.dataset.image = assetData.thumbnail;
        assetElement.dataset.idx = newIdx;
        assetElement.dataset.difficulty = assetData.difficulty;
        assetElement.title = `${assetData.title} (${assetData.project.title})`;

        this.assetListObserver.observe(assetElement);

        this.assetList.appendChild(assetElement);
    }

    filterAssets() {
        $$('.asset', this.assetList).forEach(elem => {
            console.log('FIXME: implement visibility checks for', elem.id);
        });
    }

    openViewer(assetElement) {
        let asset = this.assets[assetElement.dataset.idx - 1];

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

        $('#asset-more-info').innerHTML =
            '<pre>' + JSON.stringify(asset.metadata, null, 3) + '</pre>';

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

        $('.asset-active').scrollIntoView({
            behavior: 'smooth',
            block: 'center',
            inline: 'nearest'
        });
    }
}
