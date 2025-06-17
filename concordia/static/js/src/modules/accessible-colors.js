import chroma from 'chroma-js';

/**
 * Adjust a color’s lightness so it meets at least `minContrast` vs. `background`.
 * @param {string} colorString - Input color (any CSS‐parsable string, e.g. '#f66' or 'rgb(255,0,0)')
 * @param {string} [background='#fff'] - Background color to contrast against
 * @param {number} [minContrast=4.5] - Minimum WCAG contrast ratio
 * @returns {string} A colorString string of the adjusted color
 */
export function adjustColorForContrast(
    colorString,
    background = '#fff',
    minContrast = 4.5,
) {
    let color = chroma(colorString);
    const backgroundLum = chroma(background).luminance();
    // if background is light, we darken; if background is dark, we brighten
    let step = 0.05;
    if (backgroundLum > 0.5) {
        step *= -1;
    }

    // We adjust the color's lightness by `step` until it reaches a constract of minConstrast
    // We limit it to 20 iterations to avoid an infinite loop. 20 because at 20
    // iterations, we've definitely traversed the entire possible range
    // (from 0 to 1 or from 1 to 0)
    for (
        let index = 0;
        index < 20 && chroma.contrast(color, background) < minContrast;
        index++
    ) {
        color = color.set('hsl.l', color.get('hsl.l') + step);
    }
    return color.hex();
}

/**
 * Generate a `count`-color palette that all meet `minContrast` vs. `background`.
 * Uses an LCh‐spaced base palette from chroma.js, then adjusts each hue.
 * @param {number} count - Number of colors to generate
 * @param {string} [background='#fff'] - Background color to contrast against
 * @param {number} [minContrast=4.5] - Minimum WCAG contrast ratio
 * @param {string} [scaleName='Spectral']
 *   - Any valid chroma.js scale name (e.g. 'Spectral', 'Rainbow', etc.)
 * @returns {string[]} Array of colorString color strings
 */
export function generateAccessibleColors(
    count,
    background = '#fff',
    minContrast = 4.5,
    scaleName = 'Spectral',
) {
    // build a base LCh (Lightness-Color-hue) palette
    const raw = chroma.scale(scaleName).mode('lch').colors(count);

    // adjust each color for contrast
    return raw.map((colorString) =>
        adjustColorForContrast(colorString, background, minContrast),
    );
}
