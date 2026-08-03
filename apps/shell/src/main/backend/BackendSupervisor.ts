import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { EventEmitter } from "node:events";
import log from "electron-log/main";
import type { BackendStatus } from "@jarvis/contracts";

const logger = log.scope("BackendSupervisor");

export interface BackendSupervisorOptions {
  /** Path to the Python interpreter inside the backend's venv. */
  pythonPath: string;
  /** Working directory of the backend app (apps/backend). */
  cwd: string;
  /** Module to run, e.g. "jarvis_backend.main". */
  module: string;
  /** Port the backend's FastAPI/uvicorn server should bind to. */
  port: number;
  /** Max consecutive crash-restarts before giving up. */
  maxRestarts?: number;
  /** Base delay for exponential backoff between restarts, in ms. */
  baseBackoffMs?: number;
}

interface BackendSupervisorEvents {
  statusChange: [BackendStatus];
  log: [{ stream: "stdout" | "stderr"; line: string }];
}

/**
 * Owns the lifecycle of the Python backend child process: spawn, health
 * tracking, crash detection, and bounded exponential-backoff restarts.
 *
 * This class does NOT parse application-level events from the backend — it
 * only knows about OS process lifecycle. The event-stream client (WebSocket
 * connection carrying `JarvisEvent`s) is a separate collaborator that
 * connects once this supervisor reports `ready`, matching the "replaceable
 * subsystem" architecture principle.
 */
export class BackendSupervisor extends EventEmitter<BackendSupervisorEvents> {
  private readonly options: Required<BackendSupervisorOptions>;
  private child: ChildProcessWithoutNullStreams | null = null;
  private status: BackendStatus = "stopped";
  private restartCount = 0;
  private startedAt: number | null = null;
  private stopping = false;

  constructor(options: BackendSupervisorOptions) {
    super();
    this.options = {
      maxRestarts: 5,
      baseBackoffMs: 1000,
      ...options,
    };
  }

  public getStatus(): {
    status: BackendStatus;
    pid: number | null;
    uptimeMs: number | null;
    restartCount: number;
  } {
    return {
      status: this.status,
      pid: this.child?.pid ?? null,
      uptimeMs: this.startedAt ? Date.now() - this.startedAt : null,
      restartCount: this.restartCount,
    };
  }

  public start(): void {
    if (this.child) {
      logger.warn("start() called but backend already running");
      return;
    }
    this.stopping = false;
    this.spawnProcess();
  }

  public stop(): void {
    this.stopping = true;
    if (this.child) {
      logger.info("Stopping backend process", { pid: this.child.pid });
      this.child.kill();
    }
    this.setStatus("stopped");
  }

  // -- internals -------------------------------------------------------

  private spawnProcess(): void {
    this.setStatus("starting");
    const { pythonPath, cwd, module, port } = this.options;

    logger.info("Spawning backend process", { pythonPath, cwd, module, port });

    const child = spawn(
      pythonPath,
      ["-m", module, "--port", String(port)],
      {
        cwd,
        env: {
          ...process.env,
          JARVIS_BACKEND_PORT: String(port),
          PYTHONUNBUFFERED: "1",
        },
      },
    );

    this.child = child;
    this.startedAt = Date.now();

    child.stdout.on("data", (chunk: Buffer) => {
      const line = chunk.toString("utf8").trimEnd();
      this.emit("log", { stream: "stdout", line });
      if (this.status === "starting" && /uvicorn running/i.test(line)) {
        this.restartCount = 0;
        this.setStatus("ready");
      }
      logger.debug(`[backend] ${line}`);
    });

    child.stderr.on("data", (chunk: Buffer) => {
      const line = chunk.toString("utf8").trimEnd();
      this.emit("log", { stream: "stderr", line });
      logger.warn(`[backend:stderr] ${line}`);
    });

    child.on("exit", (code, signal) => {
      logger.warn("Backend process exited", { code, signal });
      this.child = null;
      this.startedAt = null;

      if (this.stopping) {
        this.setStatus("stopped");
        return;
      }

      this.setStatus("crashed");
      this.maybeRestart();
    });

    child.on("error", (err) => {
      logger.error("Backend process error", { error: err.message });
    });
  }

  private maybeRestart(): void {
    if (this.restartCount >= this.options.maxRestarts) {
      logger.error("Backend exceeded max restarts; giving up", {
        maxRestarts: this.options.maxRestarts,
      });
      return;
    }

    const delay = this.options.baseBackoffMs * 2 ** this.restartCount;
    this.restartCount += 1;
    logger.info("Scheduling backend restart", {
      attempt: this.restartCount,
      delayMs: delay,
    });

    setTimeout(() => {
      if (!this.stopping) this.spawnProcess();
    }, delay);
  }

  private setStatus(status: BackendStatus): void {
    this.status = status;
    this.emit("statusChange", status);
  }
}
