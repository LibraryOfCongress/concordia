/* global OpenSeadragon */
/* eslint-disable no-console */

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

        this.setupModeSelector();
        this.setupAssetViewer();

        this.refreshData();
    }

    setupModeSelector() {
        $$('#activity-mode-selection button').forEach(elem => {
            elem.addEventListener('click', evt => {
                $$('#activity-mode-selection button').forEach(inactiveElem => {
                    if (inactiveElem.classList.contains('active')) {
                        inactiveElem.classList.remove('active');
                    }
                });
                evt.target.classList.add('active');
                // refresh the interface to reflect the activity of elem
                window.actionApp.refreshData();
            });
        });
    }

    setMode() {
        this.modeSelection = $('#activity-mode-selection');
        this.currentMode = this.modeSelection.querySelector('.active').value;
    }

    refreshData() {
        this.assets = [];

        this.setMode();
        this.resetAssetList();
        this.setupAssetList();
        this.fetchAssetData();
    }

    resetAssetList() {
        $('#asset-list').innerHTML = '';
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

        this.assetList.addEventListener('click', evt => {
            let target = evt.target;
            if (target && target.classList.contains('asset')) {
                this.openViewer(target);
                $$('#asset-list .asset').forEach(elem => {
                    if (elem.classList.contains('border-primary')) {
                        elem.classList.remove('border-primary');
                    }
                });
                target.classList.add('border-primary');
                return false;
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

        $('#close-viewer-button').addEventListener('click', evt => {
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
        let asset = this.assets[assetElement.dataset.idx];

        $$('.asset-title', this.assetViewer).forEach(
            i => (i.innerText = asset.title)
        );
        $('textarea', this.assetViewer).innerText = 'Loading…';

        this.assetViewer.classList.remove('d-none');

        if (this.seadragonViewer.isOpen()) {
            this.seadragonViewer.close();
        }

        this.seadragonViewer.open({type: 'image', url: asset.thumbnail});
    }

    closeViewer() {
        this.assetViewer.classList.add('d-none');
        if (this.seadragonViewer.isOpen()) {
            this.seadragonViewer.close();
        }
    }
}
