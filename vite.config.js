import {defineConfig} from 'vite';
import {compression} from 'vite-plugin-compression2';

export default defineConfig({
    base: '/static/',
    build: {
        // collectstatic ignores hidden files - so 'true' not enough
        manifest: 'manifest.json',
        // Using 'dist' prevents Vite from writing into your source folders
        outDir: 'concordia/static/dist', // where the compiled files go
        emptyOutDir: true,
        rollupOptions: {
            input: {
                main: './src/main.js',
                about: './src/about.js',
                profile: './src/profile.js',
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
