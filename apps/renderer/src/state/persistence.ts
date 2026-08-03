import { createLogger } from "../core/logging/logger";

const logger = createLogger("SettingsPersistence");

const BACKEND_PORT = Number(import.meta.env.VITE_JARVIS_BACKEND_PORT ?? 8137);
const SETTINGS_BASE_URL = `http://127.0.0.1:${BACKEND_PORT}/settings`;

/**
 * Backend-API-backed settings persistence (ADR-0012's `SettingsRepository`,
 * `GET`/`PUT`/`DELETE /settings/{key}`). Deliberately not `localStorage` —
 * this project's persistence architecture is "the backend owns durable
 * state" (the same SQLite database that backs task history, memory, and
 * audit logs), consistent with every other durable-state decision made
 * since Phase 4 began, and avoids the renderer having its own separate,
 * un-backed-up storage mechanism.
 *
 * Every call is best-effort: a failed load falls back to the caller's
 * default (the app must still function even if a preference fails to
 * load); a failed save is logged, not thrown, since a preference failing
 * to persist should never interrupt what the user was doing when they
 * changed it.
 */

export async function loadPersistedSetting<T>(key: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${SETTINGS_BASE_URL}/${encodeURIComponent(key)}`);
    if (!response.ok) return fallback;
    const body = (await response.json()) as { value: T | null };
    return body.value ?? fallback;
  } catch (error) {
    logger.warn("Failed to load persisted setting — using fallback", {
      key,
      error: String(error),
    });
    return fallback;
  }
}

export async function savePersistedSetting<T>(key: string, value: T): Promise<void> {
  try {
    const response = await fetch(`${SETTINGS_BASE_URL}/${encodeURIComponent(key)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    });
    if (!response.ok) {
      logger.warn("Backend rejected settings save", { key, status: response.status });
    }
  } catch (error) {
    logger.warn("Failed to save persisted setting", { key, error: String(error) });
  }
}
