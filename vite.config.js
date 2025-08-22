import {defineConfig} from 'vite';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
    // root: '.',
    base: '/static/',
    build: {
        outDir: 'static',
        emptyOutDir: false,
        rollupOptions: {
            // input: path.resolve(__dirname, 'concordia/static/js/src/main.js'),
            output: {
                entryFileNames: 'bundle.js',
                // chunkFileNames: '[name].js';
                assetFileNames: ({name}) =>
                    name && name.endsWith('.css')
                        ? 'css/bundle.css'
                        : '[name][extname]',
            },
        },
    },
    resolve: {
        alias: {
            // '@js': path.resolve(__dirname, 'concordia/static/js/src'),
            '@scss': path.resolve(__dirname, 'concordia/static/scss'),
        },
    },
});
