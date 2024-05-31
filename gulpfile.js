/* eslint-env node */
/* eslint-disable unicorn/prefer-module */
/* eslint-disable unicorn/prefer-node-protocol */
/* eslint no-unused-vars: ["error", { "varsIgnorePattern": "debug" }] */

let child_process = require('child_process');
let gulp = require('gulp');
let log = require('fancy-log');
let rename = require('gulp-rename');
let sass = require('gulp-sass')(require('node-sass'));
let sourcemaps = require('gulp-sourcemaps');
let Transform = require('stream').Transform;

let paths = {
    styles: ['*/static/scss/**/*.scss'],
    scripts: ['*/static/js/src/**/*.js'],
};

function debug() {
    var transformStream = new Transform({objectMode: true});
    transformStream._transform = function (file, encoding, callback) {
        console.log('Path is:', file.path);
        callback(undefined, file);
    };

    return transformStream;
}

function styles() {
    return (
        gulp
            .src(paths.styles)
            //.pipe(debug())
            .pipe(sourcemaps.init())
            .pipe(sass({outputStyle: 'expanded'}).on('error', sass.logError))
            .pipe(
                rename(function (path) {
                    path.dirname = path.dirname.replace(
                        /^[^/]+\/static\/scss/,
                        'css',
                    );
                }),
            )
            .pipe(sourcemaps.write('sourcemaps/'))
            .pipe(gulp.dest('static/'))
    );
}

function scripts() {
    return (
        gulp
            .src(paths.scripts)
            //.pipe(debug())
            .pipe(
                rename(function (path) {
                    path.dirname = path.dirname.replace(
                        /^[^/]+\/static\/js\/src/,
                        'js',
                    );
                }),
            )
            .pipe(gulp.dest('static/'))
    );
}

function watch() {
    gulp.watch(paths.scripts, scripts);
    gulp.watch(paths.styles, styles);
}

function clean() {
    return child_process.exec(
        'git clean -fdx static/',
        function (error, stdout, stderr) {
            if (error) {
                log.error(`git clean failed: ${error}`);
            }
            if (stderr) {
                process.stderr.write(stderr);
            }
            if (stdout) {
                process.stdout.write(stdout);
            }
        },
    );
}

var build = gulp.parallel(styles, scripts);

exports.build = build;
exports.clean = clean;
exports.default = gulp.series(build, watch);
exports.scripts = scripts;
exports.styles = styles;
exports.watch = watch;
