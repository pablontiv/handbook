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
    let real = path.resolve(candidate);
    try {
      fs.lstatSync(candidate);
      real = fs.realpathSync(candidate);
    } catch (err: any) {
      if (err && err.code !== "ENOENT") throw err;
    }
    if (!contains(root, real)) throw new Error("eval_policy_path_escape");
    return real;
  });
}

function resolveExisting(root: string, raw: string): string {
  const clean = raw.startsWith("@") ? raw.slice(1) : raw;
  const resolved = path.isAbsolute(clean) ? path.resolve(clean) : path.resolve(root, clean);
  try {
    fs.lstatSync(resolved);
  } catch (err: any) {
    if (err && err.code === "ENOENT") throw new Error("eval_path_missing_or_dangling_symlink");
    throw err;
  }
  const real = fs.realpathSync(resolved);
  if (!contains(root, real)) throw new Error("eval_path_outside_workspace");
  return real;
}

function resolveProspective(root: string, raw: string): string {
  const clean = raw.startsWith("@") ? raw.slice(1) : raw;
  const resolved = path.isAbsolute(clean) ? path.resolve(clean) : path.resolve(root, clean);
  const relative = path.relative(root, resolved);
  if (relative === "" || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("eval_path_outside_workspace");
  const parts = relative.split(path.sep).filter(Boolean);
  let current = root;
  for (let index = 0; index < parts.length; index += 1) {
    const next = path.join(current, parts[index]);
    const isFinal = index === parts.length - 1;
    try {
      const stat = fs.lstatSync(next);
      if (stat.isSymbolicLink()) {
        let real: string;
        try {
          real = fs.realpathSync(next);
        } catch {
          throw new Error("eval_path_missing_or_dangling_symlink");
        }
        if (!contains(root, real)) throw new Error("eval_path_outside_workspace");
        if (!isFinal) current = real;
        else return real;
      } else {
        current = next;
      }
    } catch (err: any) {
      if (err && err.code !== "ENOENT") throw err;
      current = next;
    }
    if (!contains(root, path.resolve(current))) throw new Error("eval_path_outside_workspace");
  }
  return path.resolve(current);
}

function requireAllowed(target: string, allowed: string[], reason: string): void {
  if (!allowed.some((base) => contains(base, target))) throw new Error(reason);
}

function scrubbedEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  if (process.env.PATH) env.PATH = process.env.PATH;
  return env;
}

function smokeEvidence(root: string, requested: Set<string>, allowedRead: string[], pi: ExtensionAPI, phase: string): void {
  const smokePath = process.env.PI_EVAL_SMOKE_FILE;
  if (!smokePath) return;
  const target = resolveProspective(root, smokePath);
  let helperProbe = "SKIP";
  if (requested.has("read") && allowedRead.length > 0) {
    const entries = fs.readdirSync(allowedRead[0]);
    helperProbe = Array.isArray(entries) ? "PASS" : "FAIL";
  }
  const activeTools = pi.getActiveTools().slice().sort();
  const allTools = pi.getAllTools().map((tool) => tool.name).filter((name) => requested.has(name)).sort();
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, JSON.stringify({ phase, active_tools: activeTools, extension_tools: allTools, helper_probe: helperProbe }), "utf8");
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

  pi.registerCommand("model_optimizer_eval_smoke", {
    description: "Record model-optimizer eval extension runtime smoke evidence",
    async handler() {
      smokeEvidence(root, requested, allowedRead, pi, "command");
    },
  });
  pi.on("session_start", () => {
    smokeEvidence(root, requested, allowedRead, pi, "session_start");
  });

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
        const timeoutMs = typeof params.timeout === "number" ? Math.max(0, params.timeout * 1000) : undefined;
        const details = await runSandboxed(root, command, timeoutMs);
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

  if (requested.has("grep")) {
    pi.registerTool({
      name: "grep",
      label: "grep (confined)",
      description: "Search allowed UTF-8 files below an allowed workspace path.",
      parameters: Type.Object({ pattern: Type.String(), path: Type.Optional(Type.String()), ignoreCase: Type.Optional(Type.Boolean()), limit: Type.Optional(Type.Number()) }),
      async execute(_id, params) {
        const target = resolveExisting(root, params.path ?? ".");
        requireAllowed(target, allowedRead, "eval_read_not_allowed");
        const needle = params.ignoreCase ? params.pattern.toLowerCase() : params.pattern;
        const output: string[] = [];
        const max = Math.max(1, Math.min(params.limit ?? 100, 1000));
        async function visit(item: string) {
          if (output.length >= max) return;
          const stat = await fsp.lstat(item);
          if (stat.isSymbolicLink()) return;
          const real = await fsp.realpath(item);
          if (!contains(root, real)) throw new Error("eval_path_outside_workspace");
          requireAllowed(real, allowedRead, "eval_read_not_allowed");
          if (stat.isDirectory()) {
            for (const entry of await fsp.readdir(real)) await visit(path.join(real, entry));
            return;
          }
          const body = await fsp.readFile(real, "utf8").catch(() => "");
          body.split("\n").forEach((line, index) => {
            const haystack = params.ignoreCase ? line.toLowerCase() : line;
            if (output.length < max && haystack.includes(needle)) output.push(`${path.relative(root, real)}:${index + 1}:${line}`);
          });
        }
        await visit(target);
        return text(output.join("\n"), { matches: output.length });
      },
    });
  }

  if (requested.has("find")) {
    pi.registerTool({
      name: "find",
      label: "find (confined)",
      description: "List files below an allowed workspace path.",
      parameters: Type.Object({ path: Type.Optional(Type.String()), pattern: Type.Optional(Type.String()), limit: Type.Optional(Type.Number()) }),
      async execute(_id, params) {
        const target = resolveExisting(root, params.path ?? ".");
        requireAllowed(target, allowedRead, "eval_read_not_allowed");
        const output: string[] = [];
        const max = Math.max(1, Math.min(params.limit ?? 100, 1000));
        async function visit(item: string) {
          if (output.length >= max) return;
          const stat = await fsp.lstat(item);
          if (stat.isSymbolicLink()) return;
          const real = await fsp.realpath(item);
          if (!contains(root, real)) throw new Error("eval_path_outside_workspace");
          requireAllowed(real, allowedRead, "eval_read_not_allowed");
          if (stat.isDirectory()) {
            for (const entry of await fsp.readdir(real)) await visit(path.join(real, entry));
            return;
          }
          const rel = path.relative(root, real);
          if (!params.pattern || rel.includes(params.pattern)) output.push(rel);
        }
        await visit(target);
        return text(output.join("\n"), { matches: output.length });
      },
    });
  }
}
