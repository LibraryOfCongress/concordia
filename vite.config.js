import {defineConfig} from 'vite';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig({
    base: '/static/',
    build: {
        manifest: true,
        outDir: 'concordia/static', // where the compiled files go
        emptyOutDir: false,
        rollupOptions: {
            output: {
                entryFileNames: 'bundle.js',
                assetFileNames: 'bundle.[ext]',
            },
        },
    },
    resolve: {
        alias: {
            '@scss': path.resolve(__dirname, 'concordia/static/scss'),
        },
    },
});
