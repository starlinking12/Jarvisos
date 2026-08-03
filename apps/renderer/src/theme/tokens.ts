/**
 * Design tokens — the single source of truth for JARVIS OS's visual
 * language. Nothing in `theme/*.css` or any component should hardcode a
 * color, duration, or easing curve; it should reference a token here (via
 * the CSS custom properties `ThemeProvider` injects, or these constants
 * directly inside three.js code, which can't consume CSS variables).
 *
 * Visual direction: aerospace control systems + scientific visualization
 * + minimalist HUD + modern game-engine UI. Cool cyan/blue primary signal
 * color, deep near-black backgrounds, restrained amber for
 * warnings/attention — not a movie-prop palette, a plausible instrument
 * panel.
 */

export const colorTokens = {
  background: {
    void: "#05070a",
    panel: "rgba(10, 16, 24, 0.62)",
    panelElevated: "rgba(14, 22, 32, 0.74)",
  },
  signal: {
    primary: "#4fd8ff",
    primaryDim: "#1f7c96",
    secondary: "#7c9cff",
    success: "#4fffa0",
    warning: "#ffb84f",
    critical: "#ff5c5c",
  },
  text: {
    primary: "#eaf6ff",
    secondary: "#8fa8bd",
    tertiary: "#516170",
  },
  border: {
    hairline: "rgba(79, 216, 255, 0.16)",
    hairlineStrong: "rgba(79, 216, 255, 0.32)",
  },
} as const;

export const spacingTokens = {
  xs: "4px",
  sm: "8px",
  md: "16px",
  lg: "24px",
  xl: "40px",
} as const;

export const radiusTokens = {
  sm: "6px",
  md: "12px",
  lg: "20px",
  pill: "999px",
} as const;

export const blurTokens = {
  panel: "18px",
  panelElevated: "28px",
} as const;

/**
 * Motion tokens. Durations are in seconds (for three.js/Framer Motion,
 * which both use seconds), easing curves are cubic-bezier tuples usable by
 * both Framer Motion and CSS.
 */
export const motionTokens = {
  duration: {
    instant: 0.08,
    fast: 0.16,
    base: 0.28,
    slow: 0.48,
    ambient: 3.2,
  },
  easing: {
    // A restrained "settle" curve — slight overshoot damping, used for
    // panels entering/leaving. Reads as physically damped, not bouncy.
    settle: [0.16, 1, 0.3, 1] as [number, number, number, number],
    // Standard ease-out for simple fades/opacity.
    standard: [0.4, 0, 0.2, 1] as [number, number, number, number],
    // Linear, used only for continuous ambient motion (particle drift,
    // reactor idle pulse) where mechanical constancy is intentional.
    linear: [0, 0, 1, 1] as [number, number, number, number],
  },
} as const;

export const zIndexTokens = {
  overlayBackground: 0,
  hudPanels: 10,
  dockedWidgets: 20,
  commandPalette: 30,
  modal: 40,
  toast: 50,
} as const;

/** Flattens tokens into CSS custom properties for injection into :root. */
export function tokensToCssVariables(): Record<string, string> {
  return {
    "--jarvis-bg-void": colorTokens.background.void,
    "--jarvis-bg-panel": colorTokens.background.panel,
    "--jarvis-bg-panel-elevated": colorTokens.background.panelElevated,
    "--jarvis-signal-primary": colorTokens.signal.primary,
    "--jarvis-signal-primary-dim": colorTokens.signal.primaryDim,
    "--jarvis-signal-secondary": colorTokens.signal.secondary,
    "--jarvis-signal-success": colorTokens.signal.success,
    "--jarvis-signal-warning": colorTokens.signal.warning,
    "--jarvis-signal-critical": colorTokens.signal.critical,
    "--jarvis-text-primary": colorTokens.text.primary,
    "--jarvis-text-secondary": colorTokens.text.secondary,
    "--jarvis-text-tertiary": colorTokens.text.tertiary,
    "--jarvis-border-hairline": colorTokens.border.hairline,
    "--jarvis-border-hairline-strong": colorTokens.border.hairlineStrong,
    "--jarvis-space-xs": spacingTokens.xs,
    "--jarvis-space-sm": spacingTokens.sm,
    "--jarvis-space-md": spacingTokens.md,
    "--jarvis-space-lg": spacingTokens.lg,
    "--jarvis-space-xl": spacingTokens.xl,
    "--jarvis-radius-sm": radiusTokens.sm,
    "--jarvis-radius-md": radiusTokens.md,
    "--jarvis-radius-lg": radiusTokens.lg,
    "--jarvis-radius-pill": radiusTokens.pill,
    "--jarvis-blur-panel": blurTokens.panel,
    "--jarvis-blur-panel-elevated": blurTokens.panelElevated,
    "--jarvis-duration-fast": `${motionTokens.duration.fast}s`,
    "--jarvis-duration-base": `${motionTokens.duration.base}s`,
    "--jarvis-duration-slow": `${motionTokens.duration.slow}s`,
    "--jarvis-ease-settle": `cubic-bezier(${motionTokens.easing.settle.join(",")})`,
    "--jarvis-ease-standard": `cubic-bezier(${motionTokens.easing.standard.join(",")})`,
  };
}
