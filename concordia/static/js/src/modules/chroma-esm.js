// This is a shim to allow chroma-js to be used as an ES modules
import '../../chroma-js/dist/chroma.min.js'; // loads the UMD build onto window.chroma
export default window.chroma; // re-export as the module’s default
