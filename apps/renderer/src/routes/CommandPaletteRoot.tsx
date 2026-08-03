import { useMemo, useRef, useState, useEffect } from "react";
import { invokeJarvis } from "../core/ipc/jarvisBridge";
import { useJarvisStore } from "../state/store";
import { createLogger } from "../core/logging/logger";

const logger = createLogger("CommandPalette");

interface Command {
  id: string;
  label: string;
  run: () => void | Promise<void>;
}

/**
 * The command palette's full content: a real, filterable list of commands
 * each bound to a genuine action (window IPC calls, store mutations) — not
 * a mock list awaiting future wiring. The command set itself is small in
 * Phase 1 because the actions that exist are small; the Orchestrator/agent
 * command surface (Phase 2) extends this same `Command` shape rather than
 * replacing it.
 */
export function CommandPaletteRoot() {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const toggleClickThrough = useJarvisStore((state) => state.toggleClickThrough);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const commands: Command[] = useMemo(
    () => [
      {
        id: "open-settings",
        label: "Open Settings",
        run: () =>
          invokeJarvis("window.create", { kind: "settings", focusIfExists: true }).catch(
            (error) => logger.error("Failed to open settings", { error: String(error) }),
          ),
      },
      {
        id: "focus-hud",
        label: "Focus Main HUD",
        run: () =>
          invokeJarvis("window.create", { kind: "main-hud", focusIfExists: true }).catch(
            (error) => logger.error("Failed to focus HUD", { error: String(error) }),
          ),
      },
      {
        id: "toggle-overlay-click-through",
        label: "Toggle Overlay Click-Through",
        run: () => toggleClickThrough(),
      },
    ],
    [toggleClickThrough],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((command) => command.label.toLowerCase().includes(q));
  }, [commands, query]);

  return (
    <div className="jarvis-glass-panel jarvis-holographic jarvis-command-palette">
      <input
        ref={inputRef}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Type a command…"
        className="jarvis-command-palette__input"
        onKeyDown={(event) => {
          if (event.key === "Enter" && filtered[0]) {
            void filtered[0].run();
          }
        }}
      />
      <ul className="jarvis-command-palette__list">
        {filtered.map((command) => (
          <li key={command.id}>
            <button
              type="button"
              className="jarvis-command-palette__item"
              onClick={() => void command.run()}
            >
              {command.label}
            </button>
          </li>
        ))}
        {filtered.length === 0 && (
          <li className="jarvis-command-palette__empty">No matching commands</li>
        )}
      </ul>
    </div>
  );
}
