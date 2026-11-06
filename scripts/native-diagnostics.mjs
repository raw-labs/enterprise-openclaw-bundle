// Fixed labels only: never publish command arguments, error messages or output.
import { basename } from "node:path";

export function reportNativeFailure(error, emit = console.error) {
  const command = typeof error?.command === "string" ? basename(error.command) : "";
  if (["docker", "kubectl", "k3d"].includes(command)) {
    emit(`[bundle-native-command] ${command}`);
  }
  const args = Array.isArray(error?.args) ? error.args : [];
  // kubectl selection flags precede its verb; print only a recognized verb.
  const verb = args.find((arg) => ["exec", "get", "apply", "create", "delete", "cp", "wait"].includes(arg));
  if (verb) emit(`[bundle-native-operation] ${verb}`);
  if (Number.isInteger(error?.exitCode) && error.exitCode >= 0 && error.exitCode <= 255) {
    emit(`[bundle-native-exit] ${error.exitCode}`);
  }
  if (error?.timedOut === true) emit("[bundle-native-failure] timeout");
  if (["ENOENT", "EACCES", "EPERM"].includes(error?.code)) {
    emit(`[bundle-native-failure] ${error.code}`);
  }
  const probe = error?.codexSandboxProbe;
  if (["VERSION", "PREPARE", "SANDBOX", "ASSERTIONS", "CLEANUP", "DONE"].includes(probe?.stage)) {
    emit(`[bundle-native-probe] ${probe.stage}`);
  }
  const diagnostic = [error?.stderr, error?.stdout].filter((value) => typeof value === "string").join("\n");
  for (const [label, signature] of [
    ["permission-denied", /operation not permitted|permission denied/i],
    ["apparmor", /apparmor/i],
    ["version-mismatch", /codex version mismatch/i],
    ["missing-executable", /executable file not found|command not found/i],
    ["connection-refused", /connection refused/i],
  ]) {
    if (signature.test(diagnostic)) emit(`[bundle-native-failure] ${label}`);
  }
}
