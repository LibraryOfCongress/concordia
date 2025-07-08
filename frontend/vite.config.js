import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {viteStaticCopy} from 'vite-plugin-static-copy';

export default defineConfig({
    base: '/static/frontend/',
    plugins: [
        react(),
        viteStaticCopy({
            targets: [
                {
                    src: 'node_modules/openseadragon/build/openseadragon/images/*',
                    dest: 'openseadragon-images',
                },
            ],
        }),
    ],
    build: {
        outDir: '../static/frontend',
        minify: false,
        emptyOutDir: true,
        rollupOptions: {
            output: {
                entryFileNames: 'js/[name].js',
                chunkFileNames: 'js/[name].js',
                assetFileNames: ({name}) =>
                    name && name.endsWith('.css')
                        ? 'css/[name][extname]'
                        : 'assets/[name][extname]',
            },
        },
    },
});
