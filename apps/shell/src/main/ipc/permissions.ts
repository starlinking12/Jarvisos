import log from "electron-log/main";
import { dialog } from "electron";
import type { PermissionDecision, PermissionRequest, PermissionScope } from "@jarvis/contracts";

const logger = log.scope("Permissions");

/**
 * Central gate for every high-impact native action in the system (file
 * writes outside the sandbox, process control, network egress changes,
 * synthetic input, shell execution). No subsystem — not even an internal
 * agent — is permitted to bypass this gate.
 *
 * Decisions are surfaced via a native confirm dialog and an in-memory
 * per-session grant cache. This same dialog now also serves
 * backend-originated requests (`SafetyGate`'s `PROMPT` tier, Python
 * `agents/permission_broker.py`) via `PermissionBridge`
 * (`backend/PermissionBridge.ts`) — see ADR-0012. An auditable decision
 * log for backend-originated requests is persisted on the backend side
 * (`SafetyGate`'s `audit_repository`); this class's own session-grant
 * cache remains renderer/shell-request-scoped and process-local.
 */
export class PermissionGate {
  private readonly sessionGrants = new Set<PermissionScope>();

  public async request(req: PermissionRequest): Promise<PermissionDecision> {
    if (this.sessionGrants.has(req.scope)) {
      logger.info("Permission auto-granted (session cache)", req);
      return { granted: true, scope: req.scope, rememberForSession: true };
    }

    logger.info("Permission requested", req);

    const result = await dialog.showMessageBox({
      type: "question",
      buttons: ["Deny", "Allow Once", "Allow for Session"],
      defaultId: 1,
      cancelId: 0,
      title: "JARVIS OS — Permission Request",
      message: `${req.requestedBy} is requesting: ${req.scope}`,
      detail: req.reason,
    });

    const decision: PermissionDecision = (() => {
      switch (result.response) {
        case 1:
          return { granted: true, scope: req.scope, rememberForSession: false };
        case 2:
          this.sessionGrants.add(req.scope);
          return { granted: true, scope: req.scope, rememberForSession: true };
        default:
          return { granted: false, scope: req.scope, rememberForSession: false };
      }
    })();

    logger.info("Permission decision", decision);
    return decision;
  }

  public clearSessionGrants(): void {
    this.sessionGrants.clear();
  }
}
