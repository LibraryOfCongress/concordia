import {defineConfig} from 'vite';

export default defineConfig({
    base: '/static/',
    build: {
        manifest: true,
        outDir: 'concordia/static', // where the compiled files go
        emptyOutDir: false,
        rollupOptions: {
            output: {
                entryFileNames: 'js/[name].js',
                chunkFileNames: 'js/[name].js',
                assetFileNames: 'assets/[name][extname]',
            },
        },
    },
});
