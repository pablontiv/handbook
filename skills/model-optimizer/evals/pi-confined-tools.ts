// Runtime-confined Pi evaluation extension for model-optimizer.
// Loaded explicitly with --no-extensions --no-builtin-tools --extension <this-file>.

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import fs from "node:fs";
import fsp from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";

const MAX_POLICY_BYTES = 64 * 1024;
const SHELL_OPERATOR_RE = /[|&;<>()`$\\\n]/;
const SUPPORTED_TOOLS = new Set(["read", "write", "edit", "bash", "grep", "find", "ls"]);

type AllowedCommand = { command_id: string; argv: string[]; sandbox_argv: string[] };
type Policy = {
  workspace_root: string;
  token: string;
  tools: string[];
  allowed_read_paths: string[];
  allowed_write_paths: string[];
  allowed_commands: AllowedCommand[];
};

function text(content: string, details: Record<string, unknown> | undefined = {}) {
  return { content: [{ type: "text" as const, text: content }], details };
}

function loadPolicy(): Policy {
  const policyPath = process.env.PI_EVAL_POLICY;
  if (!policyPath) throw new Error("eval_policy_missing");
  const stat = fs.statSync(policyPath);
  if (stat.size > MAX_POLICY_BYTES) throw new Error("eval_policy_too_large");
  const parsed = JSON.parse(fs.readFileSync(policyPath, "utf8"));
  if (!parsed || typeof parsed !== "object") throw new Error("eval_policy_invalid");
  return parsed as Policy;
}

function realRoot(policy: Policy): string {
  return fs.realpathSync(policy.workspace_root);
}

function contains(root: string, candidate: string): boolean {
  const rel = path.relative(root, candidate);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

function policyPaths(root: string, values: string[]): string[] {
  return values.map((value) => {
    const candidate = path.isAbsolute(value) ? path.resolve(value) : path.resolve(root, value);
    const real = fs.existsSync(candidate) ? fs.realpathSync(candidate) : path.resolve(candidate);
    if (!contains(root, real)) throw new Error("eval_policy_path_escape");
    return real;
  });
}

function resolveExisting(root: string, raw: string): string {
  const clean = raw.startsWith("@") ? raw.slice(1) : raw;
  const resolved = path.isAbsolute(clean) ? path.resolve(clean) : path.resolve(root, clean);
  const real = fs.realpathSync(resolved);
  if (!contains(root, real)) throw new Error("eval_path_outside_workspace");
  return real;
}

function resolveProspective(root: string, raw: string): string {
  const clean = raw.startsWith("@") ? raw.slice(1) : raw;
  const resolved = path.isAbsolute(clean) ? path.resolve(clean) : path.resolve(root, clean);
  const parent = path.dirname(resolved);
  const realParent = fs.existsSync(parent) ? fs.realpathSync(parent) : path.resolve(parent);
  if (!contains(root, realParent)) throw new Error("eval_path_outside_workspace");
  const finalPath = path.join(realParent, path.basename(resolved));
  if (fs.existsSync(finalPath)) {
    const realFinal = fs.realpathSync(finalPath);
    if (!contains(root, realFinal)) throw new Error("eval_path_outside_workspace");
    return realFinal;
  }
  if (!contains(root, finalPath)) throw new Error("eval_path_outside_workspace");
  return finalPath;
}

function requireAllowed(target: string, allowed: string[], reason: string): void {
  if (!allowed.some((base) => contains(base, target))) throw new Error(reason);
}

function scrubbedEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  if (process.env.PATH) env.PATH = process.env.PATH;
  return env;
}

function shellWords(command: string): string[] {
  if (SHELL_OPERATOR_RE.test(command)) throw new Error("eval_shell_operator_forbidden");
  return command.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g)?.map((part) => part.replace(/^(['"])(.*)\1$/, "$2")) ?? [];
}

function assertExactCommand(policy: Policy, command: string): AllowedCommand {
  const argv = shellWords(command);
  const serialized = JSON.stringify(argv);
  const found = policy.allowed_commands.find((item) => JSON.stringify(item.argv) === serialized);
  if (!found) throw new Error("eval_command_not_allowed");
  if (!Array.isArray(found.sandbox_argv) || found.sandbox_argv.length === 0) throw new Error("eval_sandbox_unavailable");
  return found;
}

async function runSandboxed(root: string, command: AllowedCommand, timeoutMs?: number) {
  return await new Promise<{ command_id: string; exit_code: number | null; elapsed_ms: number; sandbox_backend: string }>((resolve, reject) => {
    const started = Date.now();
    const child = spawn(command.sandbox_argv[0], command.sandbox_argv.slice(1), {
      cwd: root,
      env: scrubbedEnv(),
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
      detached: process.platform !== "win32",
    });
    let settled = false;
    const timer = timeoutMs && timeoutMs > 0 ? setTimeout(() => {
      if (settled) return;
      try {
        if (child.pid && process.platform !== "win32") process.kill(-child.pid, "SIGKILL");
        else child.kill("SIGKILL");
      } catch {}
    }, timeoutMs) : undefined;
    child.on("error", reject);
    child.on("close", (code) => {
      settled = true;
      if (timer) clearTimeout(timer);
      resolve({ command_id: command.command_id, exit_code: code, elapsed_ms: Date.now() - started, sandbox_backend: "policy-runner" });
    });
  });
}

export default function modelOptimizerConfinedTools(pi: ExtensionAPI) {
  const policy = loadPolicy();
  const root = realRoot(policy);
  const allowedRead = policyPaths(root, policy.allowed_read_paths ?? []);
  const allowedWrite = policyPaths(root, policy.allowed_write_paths ?? []);
  const requested = new Set(policy.tools ?? []);
  for (const tool of requested) {
    if (!SUPPORTED_TOOLS.has(tool)) throw new Error(`eval_unsupported_tool:${tool}`);
  }

  if (requested.has("read")) {
    pi.registerTool({
      name: "read",
      label: "read (confined)",
      description: "Read UTF-8 text files allowed by the evaluation fixture policy.",
      parameters: Type.Object({ path: Type.String(), offset: Type.Optional(Type.Number()), limit: Type.Optional(Type.Number()) }),
      async execute(_id, params) {
        const target = resolveExisting(root, params.path);
        requireAllowed(target, allowedRead, "eval_read_not_allowed");
        const lines = (await fsp.readFile(target, "utf8")).split("\n");
        const start = params.offset ? Math.max(0, params.offset - 1) : 0;
        const end = params.limit ? start + params.limit : lines.length;
        return text(lines.slice(start, end).join("\n"), {});
      },
    });
  }

  if (requested.has("write")) {
    pi.registerTool({
      name: "write",
      label: "write (confined)",
      description: "Create or overwrite files allowed by the evaluation fixture policy.",
      parameters: Type.Object({ path: Type.String(), content: Type.String() }),
      async execute(_id, params) {
        const target = resolveProspective(root, params.path);
        requireAllowed(target, allowedWrite, "eval_write_not_allowed");
        await fsp.mkdir(path.dirname(target), { recursive: true });
        await fsp.writeFile(target, params.content, "utf8");
        return { content: [{ type: "text" as const, text: `Wrote ${path.relative(root, target)}` }], details: undefined };
      },
    });
  }

  if (requested.has("edit")) {
    pi.registerTool({
      name: "edit",
      label: "edit (confined)",
      description: "Apply exact text replacements to files allowed by the evaluation fixture policy.",
      parameters: Type.Object({ path: Type.String(), edits: Type.Array(Type.Object({ oldText: Type.String(), newText: Type.String() })) }),
      async execute(_id, params) {
        const target = resolveExisting(root, params.path);
        requireAllowed(target, allowedWrite, "eval_write_not_allowed");
        let content = await fsp.readFile(target, "utf8");
        for (const edit of params.edits) {
          if (!content.includes(edit.oldText)) throw new Error("eval_edit_old_text_missing");
          content = content.replace(edit.oldText, edit.newText);
        }
        await fsp.writeFile(target, content, "utf8");
        return text(`Edited ${path.relative(root, target)}`, { diff: "", patch: "" });
      },
    });
  }

  if (requested.has("bash")) {
    pi.registerTool({
      name: "bash",
      label: "bash (manifest sandbox)",
      description: "Run only exact manifest commands through the evaluator-selected sandbox profile.",
      parameters: Type.Object({ command: Type.String(), timeout: Type.Optional(Type.Number()) }),
      async execute(_id, params) {
        const command = assertExactCommand(policy, params.command);
        const details = await runSandboxed(root, command, params.timeout);
        return text(`Command exited with code ${details.exit_code}.`, details);
      },
    });
  }

  if (requested.has("ls")) {
    pi.registerTool({
      name: "ls",
      label: "ls (confined)",
      description: "List allowed workspace directories.",
      parameters: Type.Object({ path: Type.Optional(Type.String()), limit: Type.Optional(Type.Number()) }),
      async execute(_id, params) {
        const target = resolveExisting(root, params.path ?? ".");
        requireAllowed(target, allowedRead, "eval_read_not_allowed");
        const entries = (await fsp.readdir(target)).slice(0, params.limit ?? 1000);
        return text(entries.join("\n"), {});
      },
    });
  }

  for (const name of ["grep", "find"] as const) {
    if (!requested.has(name)) continue;
    pi.registerTool({
      name,
      label: `${name} (disabled confined)`,
      description: `${name} is registered only when requested, but this evaluator fixture does not expose search execution.`,
      parameters: Type.Object({ pattern: Type.String(), path: Type.Optional(Type.String()), limit: Type.Optional(Type.Number()) }),
      async execute() {
        throw new Error(`eval_${name}_not_available`);
      },
    });
  }

  pi.setActiveTools([...requested]);
}
