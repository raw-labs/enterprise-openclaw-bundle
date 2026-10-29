// Authoring measurement against real PostgreSQL, not full application qualification.
import { createRequire } from "node:module";
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";

const root = process.cwd();
const dependency = createRequire(resolve("packages/occ/package.json"));
const { Client } = dependency("pg");
const { drizzle } = dependency("drizzle-orm/node-postgres");
const { migrate } = dependency("drizzle-orm/node-postgres/migrator");
const { migrationCatalog, catalogDigest } = await import(
  pathToFileURL(resolve("scripts/migration-catalog.mjs"))
);
const inputs = JSON.parse(await readFile(".maintain-catalog-inputs.json", "utf8"));
const container = process.env.CATALOG_CONTAINER;
if (!container || !/^[a-zA-Z0-9_-]+$/.test(container)) throw new Error("Missing owned test container");
const binding = execFileSync("docker", ["port", container, "5432/tcp"], { encoding: "utf8" }).trim();
if (!/^127\.0\.0\.1:[0-9]+$/.test(binding)) throw new Error("Test PostgreSQL is not loopback-only");
const port = Number(binding.split(":")[1]);
const connect = async (user, password, database) => {
  const client = new Client({ host: "127.0.0.1", port, user, password, database });
  await client.connect();
  return client;
};
const admin = await connect("postgres", "openclaw-local-admin", "openclaw_enterprise");
const databases = ["maintain_catalog", "maintain_catalog_restore", "maintain_catalog_prefix"];
const prefixRestore = "maintain_catalog_prefix_restore";
const temporary = await mkdtemp(resolve(tmpdir(), "maintain-catalog-"));
try {
  const server = await admin.query("SHOW server_version");
  if (!server.rows[0].server_version.startsWith("18.6")) throw new Error("Unexpected PostgreSQL version");
  const roles = await admin.query(`SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb
    FROM pg_roles WHERE rolname IN ('occ_migrator','occ_app') ORDER BY rolname`);
  if (roles.rows.length !== 2 || roles.rows.some(row => row.rolsuper || row.rolbypassrls || row.rolcreaterole || row.rolcreatedb)) {
    throw new Error("Application/migrator roles are not limited");
  }
  for (const name of databases) {
    await admin.query(`CREATE DATABASE ${name}`);
    await admin.query(`GRANT CREATE ON DATABASE ${name} TO occ_migrator`);
    const setup = await connect("postgres", "openclaw-local-admin", name);
    try {
      await setup.query("REVOKE CREATE ON SCHEMA public FROM PUBLIC");
      if (name !== databases[1]) await setup.query("CREATE SCHEMA occ AUTHORIZATION occ_migrator; CREATE SCHEMA drizzle AUTHORIZATION occ_migrator");
    }
    finally { await setup.end(); }
  }
  const measure = async name => {
    const client = await connect("occ_migrator", "occ-migrator-local", name);
    try {
      return {
        completed: catalogDigest(await migrationCatalog(client)),
        ledger: catalogDigest(await migrationCatalog(client, "drizzle")),
      };
    } finally { await client.end(); }
  };
  const client = await connect("occ_migrator", "occ-migrator-local", databases[0]);
  try {
    // Drizzle installs the exact reviewed SQL before its authoring catalog is known.
    // The production guarded migrator and upgrade cases run later in canonical CI.
    await migrate(drizzle(client), { migrationsFolder: resolve(root, "migrations") });
  } finally { await client.end(); }
  const native = await measure(databases[0]);
  const dump = execFileSync("docker", ["exec", container, "pg_dump", "-U", "postgres", "-Fc", databases[0]], { maxBuffer: 64 * 1024 * 1024 });
  execFileSync("docker", ["exec", "-i", container, "pg_restore", "-U", "postgres", "--single-transaction", "--exit-on-error", "-d", databases[1]], { input: dump, maxBuffer: 1024 * 1024 });
  const restored = await measure(databases[1]);
  if (restored.ledger !== native.ledger) throw new Error("Logical restore changed ledger catalog");
  // Qualify accepted upgrade-prefix fingerprints from actual SQL as well. Never
  // derive them from final DDL text or reuse upstream hashes after composition.
  const journal = JSON.parse(await readFile("migrations/meta/_journal.json", "utf8"));
  if (!journal.entries.length || journal.entries.length > 512) throw new Error("Unexpected migration inventory");
  await mkdir(resolve(temporary, "meta"));
  for (const entry of journal.entries) {
    if (!/^[0-9]+_[a-zA-Z0-9_]+$/.test(entry.tag)) throw new Error("Invalid migration identity");
    await copyFile(resolve("migrations", entry.tag + ".sql"), resolve(temporary, entry.tag + ".sql"));
  }
  const prefixes = {};
  const incremental = await connect("occ_migrator", "occ-migrator-local", databases[2]);
  try {
    for (let count = 1; count <= journal.entries.length; count += 1) {
      await writeFile(resolve(temporary, "meta/_journal.json"), JSON.stringify({ ...journal, entries: journal.entries.slice(0, count) }));
      await migrate(drizzle(incremental), { migrationsFolder: temporary });
      const prefix = await measure(databases[2]);
      await admin.query(`CREATE DATABASE ${prefixRestore}`);
      await admin.query(`GRANT CREATE ON DATABASE ${prefixRestore} TO occ_migrator`);
      const restoreSetup = await connect("postgres", "openclaw-local-admin", prefixRestore);
      try { await restoreSetup.query("REVOKE CREATE ON SCHEMA public FROM PUBLIC"); }
      finally { await restoreSetup.end(); }
      const prefixDump = execFileSync("docker", ["exec", container, "pg_dump", "-U", "postgres", "-Fc", databases[2]], { maxBuffer: 64 * 1024 * 1024 });
      execFileSync("docker", ["exec", "-i", container, "pg_restore", "-U", "postgres", "--single-transaction", "--exit-on-error", "-d", prefixRestore], { input: prefixDump, maxBuffer: 1024 * 1024 });
      const restoredPrefix = await measure(prefixRestore);
      if (restoredPrefix.ledger !== prefix.ledger) throw new Error("Restored prefix changed ledger catalog");
      // pg_dump may rewrite existing function definitions while later migrations
      // create native definitions. Measure that mixed final catalog explicitly.
      const upgrade = await connect("occ_migrator", "occ-migrator-local", prefixRestore);
      try { await migrate(drizzle(upgrade), { migrationsFolder: resolve(root, "migrations") }); }
      finally { await upgrade.end(); }
      const upgraded = await measure(prefixRestore);
      if (upgraded.ledger !== native.ledger) throw new Error("Restored upgrade changed ledger catalog");
      prefixes[count] = { tag: journal.entries[count - 1].tag, catalog: prefix.completed, ledger: prefix.ledger, restored_catalog: restoredPrefix.completed, upgraded_catalog: upgraded.completed };
      await admin.query(`DROP DATABASE ${prefixRestore} WITH (FORCE)`);
    }
  } finally { await incremental.end(); }
  const finalPrefix = prefixes[journal.entries.length];
  if (finalPrefix.catalog !== native.completed || finalPrefix.ledger !== native.ledger || finalPrefix.restored_catalog !== restored.completed || finalPrefix.upgraded_catalog !== restored.completed) {
    throw new Error("Incremental and fresh migration catalogs differ");
  }
  const receipt = {
    ...inputs,
    probe_sha: process.env.GITHUB_SHA,
    run_id: process.env.GITHUB_RUN_ID,
    postgresql: server.rows[0].server_version,
    drizzle: JSON.parse(await readFile(resolve(dirname(dependency.resolve("drizzle-orm")), "package.json"), "utf8")).version,
    migration_count: journal.entries.length,
    prefixes,
    completed_catalog: native.completed,
    ledger_catalog: native.ledger,
    restored_catalog: restored.completed,
    scope: "Real fresh/incremental SQL installation, logical restore and restored-prefix upgrade measurements for every prefix; this does not admit unsupported prefixes or replace guarded upgrade/application CI.",
  };
  await writeFile("catalog-measurement.json", JSON.stringify(receipt, null, 2) + "\n");
  console.log(JSON.stringify(receipt));
} finally {
  await rm(temporary, { recursive: true, force: true });
  for (const name of [prefixRestore, ...databases.toReversed()]) await admin.query(`DROP DATABASE IF EXISTS ${name} WITH (FORCE)`);
  await admin.end();
}
