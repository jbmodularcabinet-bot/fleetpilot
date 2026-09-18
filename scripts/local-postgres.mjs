import EmbeddedPostgres from "embedded-postgres";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";

// Local development only. Secrets stay in gitignored .runtime and .env files.
mkdirSync(".runtime", { recursive: true });
const secretPath = ".runtime/database.json";
const secrets = existsSync(secretPath)
  ? JSON.parse(readFileSync(secretPath, "utf8"))
  : {
      admin: randomBytes(24).toString("hex"),
      app: randomBytes(24).toString("hex"),
      demo: randomBytes(16).toString("hex"),
    };
if (!existsSync(secretPath))
  writeFileSync(secretPath, JSON.stringify(secrets), { mode: 0o600 });
const pg = new EmbeddedPostgres({
  databaseDir: ".runtime/postgres",
  user: "postgres",
  password: secrets.admin,
  port: 54329,
  persistent: true,
  authMethod: "scram-sha-256",
  postgresFlags: ["-h", "127.0.0.1"],
  onLog: () => {},
  onError: (message) => {
    if (String(message).includes("FATAL")) console.error(String(message));
  },
});
if (!existsSync(".runtime/postgres/PG_VERSION")) await pg.initialise();
await pg.start();
const admin = pg.getPgClient("postgres", "127.0.0.1");
await admin.connect();
if (
  !(await admin.query("SELECT 1 FROM pg_roles WHERE rolname='fleetpilot_app'"))
    .rowCount
) {
  // Password is generated hex, never interpolated user input.
  await admin.query(
    `CREATE ROLE fleetpilot_app LOGIN PASSWORD '${secrets.app}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`,
  );
}
for (const database of ["fleetpilot", "fleetpilot_test"]) {
  if (
    !(
      await admin.query("SELECT 1 FROM pg_database WHERE datname=$1", [
        database,
      ])
    ).rowCount
  )
    await pg.createDatabase(database);
  const connection = pg.getPgClient(database, "127.0.0.1");
  await connection.connect();
  await connection.query("REVOKE CREATE ON SCHEMA public FROM PUBLIC");
  await connection.query("GRANT USAGE ON SCHEMA public TO fleetpilot_app");
  await connection.query(
    "ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fleetpilot_app",
  );
  await connection.end();
}
await admin.end();
const appUrl = `postgresql+asyncpg://fleetpilot_app:${secrets.app}@127.0.0.1:54329/fleetpilot`;
const adminUrl = `postgresql+asyncpg://postgres:${secrets.admin}@127.0.0.1:54329/fleetpilot`;
if (!existsSync(".env"))
  writeFileSync(
    ".env",
    `ENVIRONMENT=development\nWEB_ORIGIN=http://localhost:3000\nAPI_INTERNAL_URL=http://127.0.0.1:8000\nDATABASE_URL=${appUrl}\nMIGRATION_DATABASE_URL=${adminUrl}\nDEMO_PASSWORD=${secrets.demo}\n`,
    { mode: 0o600 },
  );
writeFileSync(
  ".runtime/test.env",
  `ENVIRONMENT=test\nWEB_ORIGIN=http://localhost:3000\nDATABASE_URL=${appUrl}_test\nMIGRATION_DATABASE_URL=${adminUrl}_test\nDEMO_PASSWORD=${secrets.demo}\nLOGIN_LIMIT=100\n`,
  { mode: 0o600 },
);
console.log(
  "Local PostgreSQL ready on 127.0.0.1:54329. Development and isolated test databases ready. Secrets saved locally, not printed.",
);
async function stop() {
  await pg.stop();
  process.exit(0);
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
setInterval(() => {}, 60000);
