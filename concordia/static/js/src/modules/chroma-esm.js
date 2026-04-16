// This is a shim to allow chroma-js to be used as an ES modules
// TODO Consider removing the shim and vite config alias and input
//      concordia-visualizations directly
import 'chroma-js'; // Vite resolves this to node_modules/chroma-js - loads the UMD build onto window.chroma
export default window.chroma; // re-export as the module’s default
