import {defineConfig} from 'vite';
// import path from 'path';

export default defineConfig({
    // root: '.',
    base: '/static/',
    build: {
        outDir: 'static',
        emptyOutDir: false,
        rollupOptions: {
            input: './concordia/static/js/src/main.js',
            output: {
                entryFileNames: 'bundle.js',
                assetFileNames: ({name}) =>
                    name && name.endsWith('.css')
                        ? 'css/bundle.css'
                        : '[name][extname]',
            },
        },
    },
});
