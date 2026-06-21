import { PrintPayload } from "./types.js";

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

export function validatePrintPayload(payload: PrintPayload): string[] {
  const errors: string[] = [];

  if (!payload || typeof payload !== "object") {
    return ["Payload must be an object"];
  }

  if (!payload.printer_id || typeof payload.printer_id !== "string") {
    errors.push("printer_id is required and must be a string");
  }

  if (!isPlainObject(payload.printer)) {
    errors.push("printer is required and must be an object");
  } else {
    const ip = payload.printer.ip;
    const port = payload.printer.port;
    if (!ip || typeof ip !== "string") {
      errors.push("printer.ip is required and must be a string");
    }
    if (typeof port !== "number" || Number.isNaN(port)) {
      errors.push("printer.port is required and must be a number");
    }
  }

  if (!isPlainObject(payload.command)) {
    errors.push("command is required and must be an object");
  } else {
    const asDirect = payload.command as Record<string, unknown>;
    const maybeNested = asDirect.command;
    if (typeof maybeNested === "string") {
      if (!maybeNested.trim()) {
        errors.push("command.command must be a non-empty string");
      }
    } else if (isPlainObject(maybeNested)) {
      const nestedName = maybeNested.command;
      if (typeof nestedName !== "string" || !nestedName.trim()) {
        errors.push("nested command.command must be a non-empty string");
      }
    } else {
      errors.push("command.command must be a string or nested command object");
    }
  }

  if (
    payload.priority !== undefined &&
    payload.priority !== "high" &&
    payload.priority !== "normal"
  ) {
    errors.push("priority must be 'high' or 'normal'");
  }

  return errors;
}
