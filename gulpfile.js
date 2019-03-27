/* eslint-env node */

let gulp = require('gulp');
let sass = require('gulp-sass');
let rename = require('gulp-rename');

let paths = {
    styles: [
        'node_modules/bootstrap/scss/bootstrap.scss',
        '*/static/scss/**/*.scss'
    ],

    scripts: ['*/static/js/**/*.js']
};

function styles() {
    return gulp
        .src(paths.styles)
        .pipe(sass())
        .pipe(
            rename({
                dirname: ''
            })
        )
        .pipe(gulp.dest('static/css/'));
}

function scripts() {
    return gulp
        .src(paths.scripts)
        .pipe(
            rename({
                dirname: ''
            })
        )
        .pipe(gulp.dest('static/js/'));
}

function watch() {
    gulp.watch(paths.scripts, scripts);
    gulp.watch(paths.styles, styles);
}

var build = gulp.parallel(styles, scripts);

exports.styles = styles;
exports.scripts = scripts;
exports.build = build;
exports.watch = watch;
exports.default = watch;
