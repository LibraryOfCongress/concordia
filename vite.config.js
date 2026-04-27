import {defineConfig} from 'vite';
import {compression} from 'vite-plugin-compression2';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

// Define __dirname for ES Modules
const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
    base: '/static/',
    resolve: {
        alias: {
            // Map the custom name to its actual directory
            // Adjust the path below to where your visualization logic actually lives
            'concordia-visualization': path.resolve(
                __dirname,
                './concordia/static/js/src/modules/concordia-visualization.js',
            ),
        },
    },
    optimizeDeps: {
        include: ['openseadragon', 'openseadragon-filters'],
    },
    build: {
        // collectstatic ignores hidden files - so 'true' not enough
        manifest: 'manifest.json',
        // Using 'dist' prevents Vite from writing into your source folders
        outDir: 'concordia/static/dist', // where the compiled files go
        emptyOutDir: true,
        rollupOptions: {
            input: {
                // Existing entry points
                main: './src/main.js',
                about: './src/about.js',
                profile: './src/profile.js',

                // ADD the new standalone JS files
                admin_custom: './concordia/static/admin/custom-inline.js',
                admin_editor: './concordia/static/admin/editor-preview.js',
                js_base: './concordia/static/js/src/base.js',
                accessible_colors:
                    './concordia/static/js/src/modules/accessible-colors.js',
                chroma_esm: './concordia/static/js/src/modules/chroma-esm.js',
                turnstile: './concordia/static/js/src/modules/turnstile.js',
                viz_errors:
                    './concordia/static/js/src/modules/visualization-errors.js',
                password_validation:
                    './concordia/static/js/src/password-validation.js',
                viz_asset_status:
                    './concordia/static/js/src/visualizations/asset-status-by-campaign.js',
                jquery_cookie: './concordia/static/vendor/jquery.cookie.js',

                // The SCSS entry point
                base_styles: './concordia/static/scss/base.scss',
            },
            output: {
                // 1. Enable hashing so Vite handles versioning
                entryFileNames: 'js/[name]-[hash].js',
                chunkFileNames: 'js/[name]-[hash].js',
                assetFileNames: 'assets/[name]-[hash][extname]',
            },
        },
    },
    plugins: [
        // 2. Pre-compress files so WhiteNoise doesn't have to at startup
        compression({algorithm: 'gzip'}),
        compression({algorithm: 'brotliCompress'}),
    ],
});
