import { Component, type ErrorInfo, type ReactNode } from "react";
import { createLogger } from "../logging/logger";

const logger = createLogger("ErrorBoundary");

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Identifies which subsystem this boundary guards, for logging. */
  boundaryName: string;
  /** Custom fallback renderer; defaults to a minimal glass panel message. */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Isolates failures per subsystem. JARVIS OS is built from independently
 * replaceable pieces (per ADR-0001) — a crash in one widget, one HUD panel,
 * or the 3D scene must never take down the entire shell. Wrap every
 * plugin-loaded widget and every top-level route in its own boundary.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    logger.error(`Boundary "${this.props.boundaryName}" caught an error`, {
      message: error.message,
      stack: error.stack,
      componentStack: info.componentStack,
    });
  }

  private reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) {
      return this.props.fallback(error, this.reset);
    }

    return (
      <div className="jarvis-glass-panel jarvis-error-boundary" role="alert">
        <p className="jarvis-error-boundary__title">
          {this.props.boundaryName} failed to render
        </p>
        <p className="jarvis-error-boundary__message">{error.message}</p>
        <button type="button" onClick={this.reset} className="jarvis-error-boundary__retry">
          Retry
        </button>
      </div>
    );
  }
}
