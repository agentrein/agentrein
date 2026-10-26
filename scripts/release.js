#!/usr/bin/env node

/**
 * Release helper script for AgentRein monorepo.
 * Usage:
 *   node scripts/release.js <types|sdk-ts|sdk-python> [patch|minor|major|<version>] [--push]
 *
 * Examples:
 *   npm run release types patch
 *   npm run release sdk-ts 1.0.47
 *   npm run release sdk-python patch --push
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const repoRoot = path.resolve(__dirname, '..');

const PACKAGES = {
  types: {
    name: '@agentrein/types',
    file: 'types/package.json',
    type: 'json',
    tagPrefix: 'types-v',
    testCommand: 'npm run build --workspace types',
  },
  'sdk-ts': {
    name: 'agentrein (TypeScript SDK)',
    file: 'sdk-ts/package.json',
    type: 'json',
    tagPrefix: 'sdk-ts-v',
    testCommand: 'npm test --workspace agentrein',
  },
  'sdk-python': {
    name: 'agentrein (Python SDK)',
    file: 'sdk-python/pyproject.toml',
    type: 'toml',
    tagPrefix: 'sdk-python-v',
    testCommand: 'pytest sdk-python',
  },
};

function run(cmd, options = {}) {
  return execSync(cmd, { cwd: repoRoot, stdio: options.silent ? 'pipe' : 'inherit', encoding: 'utf-8' });
}

function parseSemver(v) {
  const parts = v.split('.').map(n => parseInt(n, 10));
  if (parts.length !== 3 || parts.some(isNaN)) {
    throw new Error(`Cannot parse version: ${v}`);
  }
  return parts;
}

function bumpVersion(current, bump) {
  if (bump === 'major') {
    const [maj] = parseSemver(current);
    return `${maj + 1}.0.0`;
  }
  if (bump === 'minor') {
    const [maj, min] = parseSemver(current);
    return `${maj}.${min + 1}.0`;
  }
  if (bump === 'patch') {
    const [maj, min, pat] = parseSemver(current);
    return `${maj}.${min}.${pat + 1}`;
  }
  if (/^\d+\.\d+\.\d+(?:-[\w.]+)?$/.test(bump)) {
    return bump;
  }
  throw new Error(`Invalid bump type: "${bump}". Allowed values: patch, minor, major, or explicit X.Y.Z`);
}

function getCurrentVersion(pkgConfig) {
  const fullPath = path.join(repoRoot, pkgConfig.file);
  const content = fs.readFileSync(fullPath, 'utf-8');
  if (pkgConfig.type === 'json') {
    const parsed = JSON.parse(content);
    return parsed.version;
  }
  if (pkgConfig.type === 'toml') {
    const match = content.match(/^version\s*=\s*"([^"]+)"/m);
    if (!match) throw new Error(`Could not find version in ${pkgConfig.file}`);
    return match[1];
  }
}

function setCurrentVersion(pkgConfig, newVersion) {
  const fullPath = path.join(repoRoot, pkgConfig.file);
  const content = fs.readFileSync(fullPath, 'utf-8');
  if (pkgConfig.type === 'json') {
    const parsed = JSON.parse(content);
    parsed.version = newVersion;
    fs.writeFileSync(fullPath, JSON.stringify(parsed, null, 2) + '\n', 'utf-8');
  } else if (pkgConfig.type === 'toml') {
    const updated = content.replace(/^version\s*=\s*"[^"]+"/m, `version = "${newVersion}"`);
    fs.writeFileSync(fullPath, updated, 'utf-8');
  }
}

function main() {
  const args = process.argv.slice(2).filter(arg => !arg.startsWith('--'));
  const shouldPush = process.argv.includes('--push');

  const pkgKey = args[0];
  const bumpType = args[1] || 'patch';

  if (!pkgKey || !PACKAGES[pkgKey]) {
    console.error(`\x1b[31mError: Please specify a valid package name.\x1b[0m\n`);
    console.log('Available packages:');
    for (const [key, val] of Object.entries(PACKAGES)) {
      const cur = getCurrentVersion(val);
      console.log(`  - \x1b[36m${key.padEnd(12)}\x1b[0m (${val.name}, current version: \x1b[32mv${cur}\x1b[0m)`);
    }
    console.log(`\nUsage:\n  npm run release <package> [patch|minor|major|<version>] [--push]\n`);
    process.exit(1);
  }

  const pkgConfig = PACKAGES[pkgKey];

  // 1. Verify git cleanliness
  const status = run('git status --porcelain', { silent: true }).trim();
  if (status) {
    console.error(`\x1b[31mError: Working directory has uncommitted changes. Please commit or stash first.\x1b[0m`);
    process.exit(1);
  }

  // 2. Verify branch is main
  const currentBranch = run('git rev-parse --abbrev-ref HEAD', { silent: true }).trim();
  if (currentBranch !== 'main') {
    console.warn(`\x1b[33mWarning: You are currently on branch "${currentBranch}". Releases should typically be cut from "main".\x1b[0m`);
  }

  const currentVersion = getCurrentVersion(pkgConfig);
  const nextVersion = bumpVersion(currentVersion, bumpType);
  const tagName = `${pkgConfig.tagPrefix}${nextVersion}`;

  console.log(`\n========================================`);
  console.log(` Package:        ${pkgConfig.name}`);
  console.log(` Current Version: v${currentVersion}`);
  console.log(` Target Version:  v${nextVersion}`);
  console.log(` Git Tag:         ${tagName}`);
  console.log(`========================================\n`);

  // 3. Run test suite
  console.log(`Running verification tests: "${pkgConfig.testCommand}"...`);
  try {
    run(pkgConfig.testCommand);
    console.log(`\x1b[32m✔ Tests passed cleanly.\x1b[0m\n`);
  } catch (err) {
    console.error(`\x1b[31m✖ Tests failed. Aborting release without changes.\x1b[0m`);
    process.exit(1);
  }

  // 4. Update file
  setCurrentVersion(pkgConfig, nextVersion);
  console.log(`Updated ${pkgConfig.file} to version ${nextVersion}.`);

  // 5. Commit & Tag
  const filesToStage = [pkgConfig.file];
  // If npm workspace update, also stage package-lock.json if updated
  if (pkgConfig.type === 'json') {
    try {
      run(`npm i --package-lock-only`, { silent: true });
      filesToStage.push('package-lock.json');
    } catch (_) {}
  }

  run(`git add ${filesToStage.join(' ')}`);
  run(`git commit -m "chore(release): ${pkgKey} v${nextVersion}"`);
  run(`git tag ${tagName}`);

  console.log(`\n\x1b[32m✔ Successfully committed and tagged ${tagName}!\x1b[0m`);

  if (shouldPush) {
    console.log(`\nPushing commit and tag to origin...`);
    run(`git push origin ${currentBranch}`);
    run(`git push origin ${tagName}`);
    console.log(`\x1b[32m✔ Pushed to GitHub! Deployment workflow will trigger automatically.\x1b[0m\n`);
  } else {
    console.log(`\nTo publish this release to GitHub Actions and package registries, run:`);
    console.log(`  \x1b[36mgit push origin ${currentBranch} && git push origin ${tagName}\x1b[0m\n`);
  }
}

main();
