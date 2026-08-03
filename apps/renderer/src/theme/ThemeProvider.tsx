import { useLayoutEffect, type ReactNode } from "react";
import { tokensToCssVariables } from "./tokens";

/**
 * Injects design tokens as CSS custom properties on `:root` once, on mount.
 * Deliberately NOT a React context provider passing token objects down —
 * components read tokens via `var(--jarvis-*)` in CSS/inline styles, which
 * costs zero re-renders when theme changes (e.g. future light/dark or
 * accessibility contrast variants just swap the injected variable set).
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  useLayoutEffect(() => {
    const variables = tokensToCssVariables();
    const root = document.documentElement;
    for (const [key, value] of Object.entries(variables)) {
      root.style.setProperty(key, value);
    }
  }, []);

  return <>{children}</>;
}
