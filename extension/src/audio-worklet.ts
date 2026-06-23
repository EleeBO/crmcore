// AudioWorklet Processor — compiled as IIFE (see vite.worklet.config.ts).
// AudioWorklet scope does NOT support ES module `import` statements.
// This file runs inside AudioWorkletGlobalScope, not the browser window.

class PCMProcessor extends AudioWorkletProcessor {
  // Throttle level messages: send every ~12 blocks (~96ms at 16kHz, 128 samples/block)
  private frameCounter = 0;
  private static readonly LEVEL_INTERVAL = 12;

  process(
    inputs: Float32Array[][],
    _outputs: Float32Array[][],
    _params: Record<string, Float32Array>
  ): boolean {
    const ch0 = inputs[0]?.[0]; // mic (L)
    const ch1 = inputs[0]?.[1]; // tab (R)
    if (!ch0 || ch0.length === 0) return true;

    // If only one channel available, duplicate it
    const right = ch1 && ch1.length > 0 ? ch1 : ch0;

    // Interleave L,R,L,R,... as Int16 — matches backend deinterleave_stereo()
    const interleaved = new Int16Array(ch0.length * 2);
    for (let i = 0; i < ch0.length; i++) {
      interleaved[i * 2] = Math.max(-32768, Math.min(32767, (ch0[i] ?? 0) * 32768));
      interleaved[i * 2 + 1] = Math.max(-32768, Math.min(32767, (right[i] ?? 0) * 32768));
    }

    // Transfer PCM buffer to main thread (zero-copy)
    this.port.postMessage(
      { type: "pcm", buffer: interleaved.buffer },
      [interleaved.buffer]
    );

    // Compute and send audio levels at throttled rate
    this.frameCounter++;
    if (this.frameCounter >= PCMProcessor.LEVEL_INTERVAL) {
      this.frameCounter = 0;
      const micRms = rms(ch0);
      const tabRms = rms(right);
      this.port.postMessage({ type: "level", mic: micRms, tab: tabRms });
    }

    return true;
  }
}

/** Compute RMS of a Float32 buffer, returns 0..1 range. */
function rms(buf: Float32Array): number {
  let sum = 0;
  for (let i = 0; i < buf.length; i++) {
    const s = buf[i] ?? 0;
    sum += s * s;
  }
  return Math.sqrt(sum / buf.length);
}

registerProcessor("pcm-processor", PCMProcessor);
