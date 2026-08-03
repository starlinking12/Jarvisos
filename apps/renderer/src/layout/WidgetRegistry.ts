import type { ComponentType } from "react";

export type DockZone = "left" | "right" | "bottom" | "floating";

export interface WidgetDefinition {
  id: string;
  title: string;
  /** Widgets receive no required props — they read everything from the
   * global store or their own local state, so any widget can be docked
   * anywhere without prop-plumbing from the layout. */
  component: ComponentType;
  defaultDock: DockZone;
  /** Default size hint in pixels; docking containers may override. */
  defaultSize: { width: number; height: number };
  /** Third-party plugins set this to their plugin id (Phase 5+); core
   * widgets omit it. */
  pluginId?: string;
}

/**
 * Process-wide widget registry. Core widgets self-register at import time
 * (see `widgets/registerCoreWidgets.ts`); the Phase 5+ plugin loader will
 * call `registerWidget` for third-party widgets after validating their
 * manifest. Nothing about `DockingLayout` or `Widget` needs to change to
 * support that — they only ever consume `getWidget(id)`.
 */
class WidgetRegistryImpl {
  private readonly widgets = new Map<string, WidgetDefinition>();

  public register(definition: WidgetDefinition): void {
    if (this.widgets.has(definition.id)) {
      throw new Error(`Widget "${definition.id}" is already registered`);
    }
    this.widgets.set(definition.id, definition);
  }

  public get(id: string): WidgetDefinition | undefined {
    return this.widgets.get(id);
  }

  public getAll(): WidgetDefinition[] {
    return Array.from(this.widgets.values());
  }
}

export const WidgetRegistry = new WidgetRegistryImpl();
