/* global OpenSeadragon */
/* eslint-disable no-console */

import {html, render} from 'https://unpkg.com/lit-html?module';

let $ = (selector, scope = document) => scope.querySelector(selector);

let $$ = (selector, scope = document) => {
    return Array.from(scope.querySelectorAll(selector));
};

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
        this.assets.length = 0;
        this.resetAssetList();
        this.fetchAssetData();
    }

    resetAssetList() {
        this.assetList.childNodes.forEach(i => i.remove());
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

                // TODO: stop using Bootstrap classes directly and toggle semantic classes
                $$('.asset', this.assetList).forEach(elem => {
                    elem.classList.remove('border-primary');
                });
                target.classList.add('border-primary');
                return false;
            }
        });

        /* Tooltips */

        this.assetList.addEventListener('mouseover', evt => {
            let target = evt.target;

            if (target && target.classList.contains('asset')) {
                const asset = this.assets[target.dataset.idx - 1];

                // FIXME: we can hoist this out if we add a visibility toggle for the mouseout state
                const tooltip = asset => html`
                    <div class="asset-tooltip text-white p-2">
                        <div class="item-title">
                            ${asset.item.title}
                        </div>
                        <div class="asset-title">
                            ${asset.title}
                        </div>
                        <div class="difficulty-score">
                            Difficulty Score: ${asset.difficulty}
                        </div>
                    </div>
                `;

                render(tooltip(asset), target);
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
        console.time(`Fetch ${url}`);

        fetch(url)
            .then(response => response.json())
            .then(data => {
                console.timeEnd(`Fetch ${url}`);
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

        $$('.asset-title', this.assetViewer).forEach(
            i => (i.innerText = asset.title)
        );

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
    }
}
