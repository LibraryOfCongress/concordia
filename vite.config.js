import {defineConfig} from 'vite';

export default defineConfig({
    base: '/static/',
    build: {
        manifest: true,
        outDir: 'concordia/static', // where the compiled files go
        emptyOutDir: false,
        rollupOptions: {
            input: {
                main: './src/main.js',
                about: './src/about.js',
            },
            output: {
                entryFileNames: 'js/[name].js',
                chunkFileNames: 'js/[name].js',
                assetFileNames: 'assets/[name][extname]',
            },
        },
    },
});
