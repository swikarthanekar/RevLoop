import { execSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const webRoot = path.resolve(scriptDir, "..");
const apiRoot = path.resolve(webRoot, "../api");
const generatedDir = path.join(webRoot, "types", "generated");
const tempOpenApiPath = path.join(generatedDir, ".openapi.tmp.json");
const outputPath = path.join(generatedDir, "api.ts");

mkdirSync(generatedDir, { recursive: true });

const pythonCommand =
  "import json; from app.main import app; print(json.dumps(app.openapi(), sort_keys=True))";

const openapiJson = execSync(
  `${path.join(apiRoot, ".venv/bin/python")} -c ${JSON.stringify(pythonCommand)}`,
  {
    cwd: apiRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  },
);

writeFileSync(tempOpenApiPath, openapiJson, "utf8");

execSync(
  `npx openapi-typescript ${JSON.stringify(tempOpenApiPath)} -o ${JSON.stringify(outputPath)}`,
  {
    cwd: webRoot,
    stdio: "inherit",
  },
);

rmSync(tempOpenApiPath, { force: true });

console.log(`Generated ${path.relative(webRoot, outputPath)}`);
