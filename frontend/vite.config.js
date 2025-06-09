import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    base: '/static/frontend/',
    plugins: [react()],
    build: {
        outDir: '../static/frontend',
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
