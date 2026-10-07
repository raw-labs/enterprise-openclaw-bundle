import { lstat, readdir, realpath, unlink, symlink } from "node:fs/promises";
import { dirname, join, relative } from "node:path";
const root = "/app/node_modules/openclaw";
const target = join(root, ".oce-codex-0.160.1/node_modules/@openai/codex");
async function walk(directory) {
  for (const name of await readdir(directory)) {
    const path = join(directory, name);
    const info = await lstat(path);
    if (info.isSymbolicLink()) {
      if (name === "codex" && dirname(path).endsWith("/@openai")) {
        await unlink(path);
        await symlink(relative(dirname(path), target), path);
      }
    } else if (info.isDirectory()) {
      await walk(path);
    }
  }
}
await walk(root);
const command = "/app/node_modules/.bin/codex";
await unlink(command);
await symlink(relative(dirname(command), join(target, "bin/codex.js")), command);
if (!(await realpath(command)).startsWith(target)) throw new Error("Codex command does not use the selected plugin package");
