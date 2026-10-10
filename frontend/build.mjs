import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname);
const source = resolve(root, "public");
const output = resolve(root, "dist");
const apiBaseUrl = process.env.API_BASE_URL || "http://localhost:8000";

await rm(output, { recursive: true, force: true });
await mkdir(output, { recursive: true });
await cp(source, output, { recursive: true });
await writeFile(
  resolve(output, "config.js"),
  `window.ECONSCOPE_CONFIG = ${JSON.stringify({ API_BASE_URL: apiBaseUrl }, null, 2)};\n`,
  "utf8",
);

console.log(`EconScope frontend built for ${apiBaseUrl}`);

