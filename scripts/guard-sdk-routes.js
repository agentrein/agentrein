#!/usr/bin/env node
/**
 * SDK Contract Guard (Item D3)
 *
 * Statically parses sdk-ts and sdk-python for HTTP route calls,
 * and asserts that every authenticated route called by the SDKs matches an allowed route
 * defined in the backend AGENT_ALLOWED_ROUTES specification.
 */

const fs = require('fs');
const path = require('path');

// Canonical AGENT_ALLOWED_ROUTES patterns from backend/src/dashboard/agent-routes.ts
const AGENT_ALLOWED_ROUTES = [
  { method: 'POST', pattern: /^\/sessions$/, label: 'POST /sessions' },
  { method: 'GET', pattern: /^\/sessions\/(?!dirty$)[^/]+$/, label: 'GET /sessions/:id' },
  { method: 'PATCH', pattern: /^\/sessions\/[^/]+$/, label: 'PATCH /sessions/:id' },
  { method: 'POST', pattern: /^\/sessions\/[^/]+\/rollback$/, label: 'POST /sessions/:id/rollback' },
  { method: 'POST', pattern: /^\/sessions\/[^/]+\/actions\/precapture$/, label: 'POST /sessions/:id/actions/precapture' },
  { method: 'POST', pattern: /^\/sessions\/[^/]+\/actions$/, label: 'POST /sessions/:id/actions' },
  { method: 'PATCH', pattern: /^\/sessions\/[^/]+\/actions\/[^/]+$/, label: 'PATCH /sessions/:id/actions/:actionId' },
  { method: 'GET', pattern: /^\/approvals\/[^/]+$/, label: 'GET /approvals/:id' },
  { method: 'GET', pattern: /^\/registry$/, label: 'GET /registry' },
  { method: 'GET', pattern: /^\/settings\/credentials\/validate$/, label: 'GET /settings/credentials/validate' },
];

function isAgentRouteAllowed(method, fullPath) {
  const upperMethod = method.toUpperCase();
  let cleanPath = fullPath.split('?')[0];
  if (cleanPath.endsWith('/') && cleanPath.length > 1) {
    cleanPath = cleanPath.slice(0, -1);
  }
  return AGENT_ALLOWED_ROUTES.some(
    (route) => route.method === upperMethod && route.pattern.test(cleanPath)
  );
}

function normalizeTemplateToSamplePath(template) {
  return template
    .replace(/\$\{[^}]+\}/g, 'sample_id')
    .replace(/\{[^}]+\}/g, 'sample_id')
    .replace(/^\/?/, '/');
}

function extractSdkTsRoutes(tsSource) {
  const routes = [];
  const axiosRegex = /axios\.(post|get|patch)(?:<[^>]+>)?\(\s*(?:`\$\{this\.serverUrl\}([^`]+)`|['"]([^'"]+)['"])/g;
  let match;
  while ((match = axiosRegex.exec(tsSource)) !== null) {
    const method = match[1].toUpperCase();
    const rawPath = match[2] || match[3];
    routes.push({
      sdk: 'sdk-ts',
      method,
      rawTemplate: rawPath,
      normalizedPath: normalizeTemplateToSamplePath(rawPath),
    });
  }
  return routes;
}

function extractSdkPythonRoutes(pySource) {
  const routes = [];
  const httpRegex = /self\._(?:client\._)?http\.(post|get|patch)\(\s*(?:f?["']([^"']+)["'])/g;
  let match;
  while ((match = httpRegex.exec(pySource)) !== null) {
    const method = match[1].toUpperCase();
    const rawPath = match[2];
    routes.push({
      sdk: 'sdk-python',
      method,
      rawTemplate: rawPath,
      normalizedPath: normalizeTemplateToSamplePath(rawPath),
    });
  }
  return routes;
}

function main() {
  const tsPath = path.resolve(__dirname, '../sdk-ts/src/agentreinClient.ts');
  const pyPath = path.resolve(__dirname, '../sdk-python/agentrein/client.py');

  if (!fs.existsSync(tsPath)) {
    console.error(`Error: sdk-ts source not found at ${tsPath}`);
    process.exit(1);
  }
  if (!fs.existsSync(pyPath)) {
    console.error(`Error: sdk-python source not found at ${pyPath}`);
    process.exit(1);
  }

  const tsSource = fs.readFileSync(tsPath, 'utf8');
  const pySource = fs.readFileSync(pyPath, 'utf8');

  const tsRoutes = extractSdkTsRoutes(tsSource);
  const pyRoutes = extractSdkPythonRoutes(pySource);
  const allRoutes = [...tsRoutes, ...pyRoutes];

  const errors = [];
  let verifiedCount = 0;

  for (const route of allRoutes) {
    if (route.normalizedPath === '/auth/token') {
      continue; // Unauthenticated public exchange endpoint
    }

    if (!isAgentRouteAllowed(route.method, route.normalizedPath)) {
      errors.push(
        `[Contract Violation] ${route.sdk} calls ${route.method} "${route.rawTemplate}" (normalized: "${route.normalizedPath}"), not in AGENT_ALLOWED_ROUTES!`
      );
    } else {
      verifiedCount++;
    }
  }

  if (errors.length > 0) {
    console.error(`\nFAILED: Found ${errors.length} route contract violation(s):`);
    errors.forEach((e) => console.error(`  - ${e}`));
    process.exit(1);
  }

  console.log(`[SDK Contract Guard] SUCCESS: Verified ${verifiedCount} SDK route calls across sdk-ts and sdk-python. All match AGENT_ALLOWED_ROUTES.`);
}

main();
