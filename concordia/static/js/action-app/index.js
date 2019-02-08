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

        this.assets = [];

        this.setupModeSelector();
        this.setupAssetList();
        this.setupAssetViewer();

        this.fetchAssetData();
    }

    setupModeSelector() {
        // TODO: actually implement switching modes
        this.modeSelection = $('#activity-mode-selection');
        this.currentMode = this.modeSelection.querySelector('.active').value;
    }

    setupAssetList() {
        this.assetList = $('#asset-list');

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
    }

    setupAssetViewer() {
        this.assetViewer = $('#asset-viewer');
        console.warn('setupAssetViewer is unimplemented');
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
                if (data.pagination.next && this.assets.length < 500) {
                    this.fetchAssetPage(data.pagination.next);
                }
            });
    }

    createAsset(assetData) {
        this.assets.push(assetData);

        let assetElement = document.createElement('div');
        assetElement.id = assetData.id;
        assetElement.classList.add('asset', 'rounded');
        assetElement.dataset.image = assetData.thumbnail;

        assetElement.title = `${assetData.title} (${assetData.project.title})`;

        this.assetListObserver.observe(assetElement);

        this.assetList.appendChild(assetElement);
    }

    filterAssets() {
        $$('.asset', this.assetList).forEach(elem => {
            console.log('FIXME: implement visibility checks for', elem.id);
        });
    }
}
