// Runtime-confined Pi evaluation extension for model-optimizer.
//
// The Python evaluator launches Pi with all ambient extensions and built-in tools disabled,
// then loads only this extension and points it at a bounded JSON policy file.  The policy
// contains the prepared workspace root, allowed built-in tool names, confined path rules,
// and exact manifest commands.  This file intentionally contains no host-specific paths or
// credentials.

import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

type AllowedCommand = { command_id: string; argv: string[]; sandbox_argv: string[] };
type Policy = {
  workspace_root: string;
  token: string;
  tools: string[];
  allowed_read_paths: string[];
  allowed_write_paths: string[];
  allowed_commands: AllowedCommand[];
};

const MAX_POLICY_BYTES = 64 * 1024;
const SHELL_OPERATOR_RE = /[|&;<>()`$\\\n]/;

function loadPolicy(): Policy {
  const policyPath = process.env.PI_EVAL_POLICY;
  if (!policyPath) throw new Error("eval_policy_missing");
  const stat = fs.statSync(policyPath);
  if (stat.size > MAX_POLICY_BYTES) throw new Error("eval_policy_too_large");
  const parsed = JSON.parse(fs.readFileSync(policyPath, "utf8"));
  return parsed as Policy;
}

function realInside(root: string, candidate: string): string {
  const base = fs.realpathSync(root);
  const resolved = path.isAbsolute(candidate)
    ? path.resolve(candidate)
    : path.resolve(base, candidate);
  const parent = path.dirname(resolved);
  const realParent = fs.existsSync(parent) ? fs.realpathSync(parent) : path.resolve(parent);
  const finalPath = path.join(realParent, path.basename(resolved));
  const relative = path.relative(base, finalPath);
  if (relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))) return finalPath;
  throw new Error("eval_path_outside_workspace");
}

function scrubbedEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  if (process.env.PATH) env.PATH = process.env.PATH;
  return env;
}

function assertExactCommand(policy: Policy, argv: string[]): AllowedCommand {
  if (argv.some((item) => SHELL_OPERATOR_RE.test(item))) throw new Error("eval_shell_operator_forbidden");
  const serialized = JSON.stringify(argv);
  const command = policy.allowed_commands.find((item) => JSON.stringify(item.argv) === serialized);
  if (!command) throw new Error("eval_command_not_allowed");
  return command;
}

export async function activate(api: any) {
  const policy = loadPolicy();
  const root = fs.realpathSync(policy.workspace_root);
  const allowed = new Set(policy.tools);

  if (allowed.has("read")) {
    api.registerTool("read", async ({ file }: { file: string }) => {
      return fs.readFileSync(realInside(root, file), "utf8");
    });
  }

  if (allowed.has("write") || allowed.has("edit")) {
    const writeFile = async ({ file, content }: { file: string; content: string }) => {
      const target = realInside(root, file);
      fs.writeFileSync(target, content, "utf8");
      return { path: path.relative(root, target) };
    };
    if (allowed.has("write")) api.registerTool("write", writeFile);
    if (allowed.has("edit")) api.registerTool("edit", writeFile);
  }

  if (allowed.has("bash")) {
    api.registerTool("bash", async ({ argv, cwd }: { argv: string[]; cwd?: string }) => {
      if (!Array.isArray(argv) || !argv.every((item) => typeof item === "string")) {
        throw new Error("eval_invalid_argv");
      }
      if (cwd && fs.realpathSync(path.resolve(root, cwd)) !== root) throw new Error("eval_alternate_cwd_forbidden");
      const command = assertExactCommand(policy, argv);
      if (!Array.isArray(command.sandbox_argv) || command.sandbox_argv.length === 0) {
        throw new Error("eval_sandbox_unavailable");
      }
      return await new Promise((resolve) => {
        const child = spawn(command.sandbox_argv[0], command.sandbox_argv.slice(1), {
          cwd: root,
          env: scrubbedEnv(),
          shell: false,
          stdio: ["ignore", "pipe", "pipe"],
        });
        const started = Date.now();
        child.on("close", (code) => resolve({
          command_id: command.command_id,
          exit_code: code,
          elapsed_ms: Date.now() - started,
          sandbox_backend: "policy-runner",
        }));
      });
    });
  }
}
