import {defineConfig} from 'vite';
// import path from 'path';

export default defineConfig({
    // root: '.',
    base: '/static/',
    build: {
        outDir: 'static',
        emptyOutDir: true,
        rollupOptions: {
            input: './main.js',
            output: {
                entryFileNames: 'bundle.js',
            },
        },
    },
});
