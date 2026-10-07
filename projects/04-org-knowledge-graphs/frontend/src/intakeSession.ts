import type { IntakeMode } from "./intakeTypes";

export const INTAKE_SESSION_KEY = "atlas.intake.v1";
export type IntakeSession = { requestKey: string; id?: string; mode: IntakeMode; people?: number };

/** Only an opaque recovery handle is stored; never source records or file contents. */
export function parseIntakeSession(value: string | null): IntakeSession | null {
  try {
    const record = JSON.parse(value || "null");
    if (!record || !/^[A-Za-z0-9_-]{8,128}$/.test(record.requestKey || "") ||
      !["import", "synthetic"].includes(record.mode) ||
      (record.id !== undefined && !/^intake_[a-f0-9]+$/.test(record.id))) return null;
    return { requestKey: record.requestKey, mode: record.mode, id: record.id,
      people: Number.isInteger(record.people) && record.people >= 72 && record.people <= 100000 ? record.people : undefined };
  } catch { return null; }
}

export function readIntakeSession(): IntakeSession | null {
  try { return parseIntakeSession(sessionStorage.getItem(INTAKE_SESSION_KEY)); }
  catch { return null; }
}

export function writeIntakeSession(session: IntakeSession | null) {
  try {
    if (session) sessionStorage.setItem(INTAKE_SESSION_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(INTAKE_SESSION_KEY);
  } catch { /* The flow still works when browser storage is unavailable. */ }
}

export function retryDelay(attempt: number) {
  return Math.min(6000, 700 * 2 ** Math.min(Math.max(attempt, 0), 4));
}
