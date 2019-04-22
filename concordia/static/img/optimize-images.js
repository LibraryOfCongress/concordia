#!/usr/bin/env node

const imagemin = require('imagemin');
const advpng = require('imagemin-advpng');
const jpegoptim = require('imagemin-jpegoptim');
const jpegtran = require('imagemin-jpegtran');
const optipng = require('imagemin-optipng');
const svgo = require('imagemin-svgo');
const pngout = require('imagemin-pngout');

(async () => {
    const files = await imagemin(['*.{jpg,png,svg}'], '.', {
        plugins: [
            optipng(),
            pngout(),
            advpng(),
            jpegoptim(),
            jpegtran(),
            svgo()
        ]
    });

    process.stdout.write(`Optimized ${files.length} files:\n`);

    files.forEach(file => {
        process.stdout.write(`\t${file.path}\n`);
    });
})();
