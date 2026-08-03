import { createLogger } from "../logging/logger";

const logger = createLogger("GpuCapabilities");

export type GpuTier = "low" | "medium" | "high";

export interface GpuCapabilities {
  webgl2: boolean;
  maxTextureSize: number;
  maxSamples: number;
  rendererString: string | null;
  tier: GpuTier;
  devicePixelRatio: number;
}

/**
 * Probes a throwaway canvas for WebGL2 support and hardware limits. Runs
 * once at startup; the result seeds `QualityScaler`'s initial tier, which
 * then adapts further at runtime based on measured frame time
 * (`PerformanceMonitor`). Detection alone is a coarse heuristic — it exists
 * to pick a sane starting point, not to be the final word on quality.
 */
export function detectGpuCapabilities(): GpuCapabilities {
  const canvas = document.createElement("canvas");
  const gl =
    (canvas.getContext("webgl2") as WebGL2RenderingContext | null) ??
    (canvas.getContext("webgl") as WebGLRenderingContext | null);

  if (!gl) {
    logger.warn("No WebGL context available — falling back to lowest tier");
    return {
      webgl2: false,
      maxTextureSize: 0,
      maxSamples: 0,
      rendererString: null,
      tier: "low",
      devicePixelRatio: window.devicePixelRatio || 1,
    };
  }

  const webgl2 = gl instanceof WebGL2RenderingContext;
  const maxTextureSize = gl.getParameter(gl.MAX_TEXTURE_SIZE) as number;
  const maxSamples = webgl2
    ? ((gl as WebGL2RenderingContext).getParameter(
        (gl as WebGL2RenderingContext).MAX_SAMPLES,
      ) as number)
    : 0;

  const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
  const rendererString = debugInfo
    ? (gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) as string)
    : null;

  const tier = estimateTier({ webgl2, maxTextureSize, rendererString });

  const capabilities: GpuCapabilities = {
    webgl2,
    maxTextureSize,
    maxSamples,
    rendererString,
    tier,
    devicePixelRatio: window.devicePixelRatio || 1,
  };

  logger.info("GPU capabilities detected", capabilities);

  // Release the probe context's resources immediately — it's not reused.
  const loseContext = gl.getExtension("WEBGL_lose_context");
  loseContext?.loseContext();

  return capabilities;
}

function estimateTier(params: {
  webgl2: boolean;
  maxTextureSize: number;
  rendererString: string | null;
}): GpuTier {
  const { webgl2, maxTextureSize, rendererString } = params;

  if (!webgl2 || maxTextureSize < 8192) {
    return "low";
  }

  const renderer = (rendererString ?? "").toLowerCase();
  const looksIntegrated =
    renderer.includes("intel") &&
    !renderer.includes("arc") &&
    !renderer.includes("iris xe");
  const looksSoftware = renderer.includes("swiftshader") || renderer.includes("llvmpipe");

  if (looksSoftware) return "low";
  if (looksIntegrated) return "medium";
  if (maxTextureSize >= 16384) return "high";
  return "medium";
}
