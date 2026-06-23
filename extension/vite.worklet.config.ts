import { defineConfig } from "vite";

// Separate build for AudioWorklet processor.
// AudioWorklet scope does NOT support ES module `import` statements,
// so this must be compiled as a self-contained IIFE bundle.
export default defineConfig({
  build: {
    lib: {
      entry: "src/audio-worklet.ts",
      formats: ["iife"],
      name: "PCMProcessor",
    },
    outDir: "dist",
    emptyOutDir: false,
    rollupOptions: {
      output: {
        entryFileNames: "audio-worklet.js",
      },
    },
  },
});
