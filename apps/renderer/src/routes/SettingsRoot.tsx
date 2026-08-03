import { useEffect } from "react";
import { useJarvisStore } from "../state/store";

/**
 * Settings window content. Phase 1 shipped this read-only, explicitly
 * documented as pending a persistence layer to save changes to — Phase 4
 * built that layer (`SettingsRepository`/`GET`,`PUT /settings/{key}`,
 * ADR-0012) and `PreferencesSlice` (`state/slices/preferencesSlice.ts`),
 * so the editable controls below are genuinely persisted, not local-only
 * state that resets on restart.
 *
 * System/graphics info remains live/read-only (it reflects actual
 * detected state, not a preference — there is nothing to "save" about
 * what GPU tier was detected).
 */
export function SettingsRoot() {
  const gpu = useJarvisStore((state) => state.gpuCapabilities);
  const quality = useJarvisStore((state) => state.qualitySettings);
  const backendStatus = useJarvisStore((state) => state.backendStatus);
  const eventBusState = useJarvisStore((state) => state.eventBusConnectionState);

  const preferencesLoaded = useJarvisStore((state) => state.preferencesLoaded);
  const performanceOverlayVisibleDefault = useJarvisStore(
    (state) => state.performanceOverlayVisibleDefault,
  );
  const overlayClickThroughDefault = useJarvisStore((state) => state.overlayClickThroughDefault);
  const setPerformanceOverlayVisibleDefault = useJarvisStore(
    (state) => state.setPerformanceOverlayVisibleDefault,
  );
  const setOverlayClickThroughDefault = useJarvisStore(
    (state) => state.setOverlayClickThroughDefault,
  );
  const hydratePreferences = useJarvisStore((state) => state.hydratePreferences);

  useEffect(() => {
    if (!preferencesLoaded) void hydratePreferences();
  }, [preferencesLoaded, hydratePreferences]);

  return (
    <div className="jarvis-settings">
      <section className="jarvis-glass-panel jarvis-settings__section">
        <h2 className="jarvis-settings__heading">Preferences</h2>
        <label className="jarvis-settings__checkbox-row">
          <input
            type="checkbox"
            checked={performanceOverlayVisibleDefault}
            onChange={(event) => void setPerformanceOverlayVisibleDefault(event.target.checked)}
          />
          Show performance overlay by default
        </label>
        <label className="jarvis-settings__checkbox-row">
          <input
            type="checkbox"
            checked={overlayClickThroughDefault}
            onChange={(event) => void setOverlayClickThroughDefault(event.target.checked)}
          />
          Overlay click-through by default
        </label>
      </section>

      <section className="jarvis-glass-panel jarvis-settings__section">
        <h2 className="jarvis-settings__heading">System</h2>
        <dl className="jarvis-kv-list">
          <div className="jarvis-kv-list__row">
            <dt>Backend</dt>
            <dd>{backendStatus}</dd>
          </div>
          <div className="jarvis-kv-list__row">
            <dt>Event bus</dt>
            <dd>{eventBusState}</dd>
          </div>
        </dl>
      </section>

      <section className="jarvis-glass-panel jarvis-settings__section">
        <h2 className="jarvis-settings__heading">Graphics</h2>
        <dl className="jarvis-kv-list">
          <div className="jarvis-kv-list__row">
            <dt>WebGL2</dt>
            <dd>{gpu?.webgl2 ? "supported" : "unsupported"}</dd>
          </div>
          <div className="jarvis-kv-list__row">
            <dt>Renderer</dt>
            <dd>{gpu?.rendererString ?? "detecting…"}</dd>
          </div>
          <div className="jarvis-kv-list__row">
            <dt>GPU tier</dt>
            <dd>{gpu?.tier ?? "detecting…"}</dd>
          </div>
          <div className="jarvis-kv-list__row">
            <dt>Active quality tier</dt>
            <dd>{quality.tier} (auto)</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
