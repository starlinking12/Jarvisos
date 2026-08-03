/**
 * Structured logging for the renderer. Mirrors the `scope()` pattern used by
 * `electron-log` in the main process (see apps/shell) so log shape is
 * consistent across the whole app, without pulling Node/Electron APIs into
 * the browser bundle.
 *
 * In development, output goes to the DevTools console with scope-colored
 * prefixes. Production builds drop `debug` level by default. A future phase
 * can add a transport that forwards `warn`/`error` entries to the backend
 * via the event bus for centralized diagnostics.
 */

type LogLevel = "debug" | "info" | "warn" | "error";

const LEVEL_ORDER: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const MIN_LEVEL: LogLevel = import.meta.env.DEV ? "debug" : "info";

const LEVEL_STYLE: Record<LogLevel, string> = {
  debug: "color:#7dd3fc",
  info: "color:#38bdf8",
  warn: "color:#fbbf24",
  error: "color:#f87171",
};

export interface Logger {
  debug: (message: string, context?: Record<string, unknown>) => void;
  info: (message: string, context?: Record<string, unknown>) => void;
  warn: (message: string, context?: Record<string, unknown>) => void;
  error: (message: string, context?: Record<string, unknown>) => void;
}

function shouldLog(level: LogLevel): boolean {
  return LEVEL_ORDER[level] >= LEVEL_ORDER[MIN_LEVEL];
}

function write(
  scope: string,
  level: LogLevel,
  message: string,
  context?: Record<string, unknown>,
): void {
  if (!shouldLog(level)) return;
  const prefix = `%c[${scope}]`;
  const consoleFn =
    level === "error" ? console.error : level === "warn" ? console.warn : console.log;

  if (context) {
    consoleFn(prefix, LEVEL_STYLE[level], message, context);
  } else {
    consoleFn(prefix, LEVEL_STYLE[level], message);
  }
}

/** Creates a scoped logger, e.g. `const logger = createLogger("EventBus")`. */
export function createLogger(scope: string): Logger {
  return {
    debug: (message, context) => write(scope, "debug", message, context),
    info: (message, context) => write(scope, "info", message, context),
    warn: (message, context) => write(scope, "warn", message, context),
    error: (message, context) => write(scope, "error", message, context),
  };
}
