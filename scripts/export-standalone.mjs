import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const backendRoot = path.resolve(__dirname, "..");
const defaultTarget = path.resolve(backendRoot, "..", "..", "exports", "dtoc-protected-backend");
const targetRoot = path.resolve(process.argv[2] || defaultTarget);

const includePaths = [
  ".env.example",
  ".dockerignore",
  "Dockerfile",
  "README.md",
  "package.json",
  "bundled-framework",
  "scripts",
  "src"
];

function removeTarget(targetPath) {
  if (fs.existsSync(targetPath)) {
    fs.rmSync(targetPath, { recursive: true, force: true });
  }
}

function copyRecursive(sourcePath, targetPath) {
  const stat = fs.statSync(sourcePath);

  if (stat.isDirectory()) {
    fs.mkdirSync(targetPath, { recursive: true });
    for (const entry of fs.readdirSync(sourcePath)) {
      copyRecursive(path.join(sourcePath, entry), path.join(targetPath, entry));
    }
    return;
  }

  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.copyFileSync(sourcePath, targetPath);
}

removeTarget(targetRoot);
fs.mkdirSync(targetRoot, { recursive: true });

for (const relativePath of includePaths) {
  copyRecursive(path.join(backendRoot, relativePath), path.join(targetRoot, relativePath));
}

console.log(`Standalone backend repo exported to ${targetRoot}`);
