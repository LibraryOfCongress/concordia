/* global OpenSeadragon screenfull debounce */
/* exported seadragonView stepUp stepDown resetImageFilterForms */

const viewerData = document.currentScript.dataset;

var seadragonViewer = OpenSeadragon({
    id: 'asset-image',
    prefixUrl: viewerData.prefixUrl,
    tileSources: {
        type: 'image',
        url: viewerData.tileSourceUrl,
    },
    gestureSettingsTouch: {
        pinchRotate: true,
    },
    showNavigator: true,
    showRotationControl: true,
    showFlipControl: true,
    toolbar: 'viewer-controls',
    zoomInButton: 'viewer-zoom-in',
    zoomOutButton: 'viewer-zoom-out',
    homeButton: 'viewer-home',
    rotateLeftButton: 'viewer-rotate-left',
    rotateRightButton: 'viewer-rotate-right',
    flipButton: 'viewer-flip',
    crossOriginPolicy: 'Anonymous',
});

// We need to define our own fullscreen function rather than using OpenSeadragon's
// because the built-in fullscreen function overwrites the DOM with the viewer,
// breaking our extra controls, such as the image filters.
if (screenfull.isEnabled) {
    let fullscreenButton = document.querySelector('#viewer-fullscreen');
    fullscreenButton.addEventListener('click', function (event) {
        event.preventDefault();
        let targetElement = document.querySelector(
            fullscreenButton.dataset.target,
        );
        if (screenfull.isFullscreen) {
            screenfull.exit();
        } else {
            screenfull.request(targetElement);
        }
    });
}

// The buttons configured as controls for the viewer don't properly get focus
// when clicked. This mostly isn't a problem, but causes odd-looking behavior
// when one of the extra buttons in the control bar is clicked (and therefore
// focused) first--clicking the control button leaves the focus on the extra
// button.
// TODO: Attempting to add focus to the clicked button here doesn't consistently
// work for unknown reasons, so it just removes focus from the extra buttons
// for now
let viewerControlButtons = document.querySelectorAll('.viewer-control-button');
for (const node of viewerControlButtons) {
    node.addEventListener('click', function () {
        let focusedButton = document.querySelector(
            '.extra-control-button:focus',
        );
        if (focusedButton) {
            focusedButton.blur();
        }
    });
}

/*
 * Image filter handling
 */

let availableFilters = [
    {
        formId: 'gamma-form',
        inputId: 'gamma',
        getFilter: function () {
            let value = document.getElementById(this.inputId).value;
            if (
                !Number.isNaN(value) &&
                value != 1 &&
                value >= 0 &&
                value <= 5
            ) {
                return OpenSeadragon.Filters.GAMMA(value);
            }
        },
    },
    {
        formId: 'invert-form',
        inputId: 'invert',
        getFilter: function () {
            let value = document.getElementById(this.inputId).checked;
            if (value) {
                return OpenSeadragon.Filters.INVERT();
            }
        },
    },
    {
        formId: 'threshold-form',
        inputId: 'threshold',
        getFilter: function () {
            let value = document.getElementById(this.inputId).value;
            if (!Number.isNaN(value) && value > 0 && value <= 255) {
                return OpenSeadragon.Filters.THRESHOLDING(value);
            }
        },
    },
];

function updateFilters() {
    let filters = [];
    for (const filterData of availableFilters) {
        let filter = filterData.getFilter();
        if (filter) {
            filters.push(filter);
        }
    }

    seadragonViewer.setFilterOptions({
        filters: {
            processors: filters,
        },
    });
}

for (const filterData of availableFilters) {
    let form = document.getElementById(filterData.formId);
    if (form) {
        form.addEventListener('change', updateFilters);
        form.addEventListener('reset', function () {
            // We use setTimeout to push the updateFilters
            // call to the next event cycle in order to
            // call it after the form is reset, instead
            // of before, which is when this listener
            // triggers
            setTimeout(updateFilters);
        });
    }

    let input = document.getElementById(filterData.inputId);
    if (input) {
        // We use debounce here so that updateFilters is only called once,
        // after the user stops typing or scrolling with their mousewheel
        input.addEventListener(
            'keyup',
            debounce(() => updateFilters()),
        );
        input.addEventListener(
            'wheel',
            debounce(() => updateFilters()),
        );
    }
}

/*
 * Image filter form handling
 */
function stepUp(id) {
    let input = document.getElementById(id);
    input.stepUp();
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
    return false;
}

function stepDown(id) {
    let input = document.getElementById(id);
    input.stepDown();
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
    return false;
}

function resetImageFilterForms() {
    for (const filterData of availableFilters) {
        let form = document.getElementById(filterData.formId);
        form.reset();
    }
}

let gammaNumber = document.getElementById('gamma');
let gammaRange = document.getElementById('gamma-range');

gammaNumber.addEventListener('input', function () {
    gammaRange.value = gammaNumber.value;
});

gammaRange.addEventListener('input', function () {
    gammaNumber.value = gammaRange.value;
});

let thresholdNumber = document.getElementById('threshold');
let thresholdRange = document.getElementById('threshold-range');

thresholdNumber.addEventListener('input', function () {
    thresholdRange.value = thresholdNumber.value;
});

thresholdRange.addEventListener('input', function () {
    thresholdNumber.value = thresholdRange.value;
});
