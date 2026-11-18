import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(currentDir, "../../src");

const LEGACY_ENTRIES = [
  "features",
  "layout",
  "components",
  "hooks",
  "styles",
  "utils",
  "api",
  "main.tsx",
  "App.tsx",
];

type DomainLayer = "model" | "api" | "application" | "ui";

type FileZone =
  | { kind: "domain-layer"; domain: string; layer: DomainLayer }
  | { kind: "domain-index"; domain: string }
  | { kind: "app" }
  | { kind: "shared" }
  | { kind: "other" };

function normalizePath(p: string): string {
  return p.replace(/\\/g, "/");
}

function collectSourceFiles(dir: string): string[] {
  const results: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectSourceFiles(fullPath));
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      results.push(fullPath);
    }
  }
  return results.sort();
}

function stripComments(source: string, maskStrings = false): string {
  let out = "";
  let i = 0;
  let quote: string | null = null;

  while (i < source.length) {
    const ch = source[i];
    const next = source[i + 1];

    if (quote) {
      if (ch === "\\" && i + 1 < source.length) {
        out += maskStrings ? "  " : ch + source[i + 1];
        i += 2;
        continue;
      }
      if (ch === quote) {
        out += ch;
        quote = null;
      } else {
        out += maskStrings ? (ch === "\n" ? "\n" : " ") : ch;
      }
      i += 1;
      continue;
    }

    if (ch === "'" || ch === '"' || ch === "`") {
      quote = ch;
      out += ch;
      i += 1;
      continue;
    }

    if (ch === "/" && next === "/") {
      while (i < source.length && source[i] !== "\n") {
        out += " ";
        i += 1;
      }
      continue;
    }

    if (ch === "/" && next === "*") {
      out += "  ";
      i += 2;
      while (i < source.length && !(source[i] === "*" && source[i + 1] === "/")) {
        out += source[i] === "\n" ? "\n" : " ";
        i += 1;
      }
      if (i < source.length) {
        out += "  ";
        i += 2;
      }
      continue;
    }

    out += ch;
    i += 1;
  }

  return out;
}

function extractImportSpecifiers(source: string): string[] {
  const cleaned = stripComments(source, false);
  const specifiers: string[] = [];
  const patterns = [
    /^[ \t]*import\s+["']([^"']+)["']/gm,
    /^[ \t]*import\s+(?:type\s+)?(?:[\w$*,\s{}]+?)\s+from\s+["']([^"']+)["']/gm,
    /^[ \t]*export\s+(?:type\s+)?(?:\*(?:\s+as\s+[\w$]+)?|\{[^}]*\})\s+from\s+["']([^"']+)["']/gm,
    /\b(?:import|require)\(\s*["']([^"']+)["']\s*\)/g,
  ];

  for (const pattern of patterns) {
    for (const match of cleaned.matchAll(pattern)) {
      if (match[1]) specifiers.push(match[1]);
    }
  }
  return specifiers;
}

function classifyRelativeToSrc(relPath: string): FileZone {
  const normalized = normalizePath(relPath);
  const domainLayerMatch = normalized.match(/^domains\/([^/]+)\/(model|api|application|ui)\//);
  if (domainLayerMatch) {
    return {
      kind: "domain-layer",
      domain: domainLayerMatch[1],
      layer: domainLayerMatch[2] as DomainLayer,
    };
  }
  const domainIndexMatch = normalized.match(/^domains\/([^/]+)\/index\.ts$/);
  if (domainIndexMatch) {
    return { kind: "domain-index", domain: domainIndexMatch[1] };
  }
  if (normalized.startsWith("app/")) {
    return { kind: "app" };
  }
  if (normalized.startsWith("shared/")) {
    return { kind: "shared" };
  }
  return { kind: "other" };
}

function resolveImportTarget(fromAbsFile: string, specifier: string): string | null {
  if (!specifier.startsWith(".")) return null;
  const resolved = path.resolve(path.dirname(fromAbsFile), specifier);
  return normalizePath(path.relative(srcDir, resolved));
}

function isReactPackage(specifier: string): boolean {
  return specifier === "react" || specifier.startsWith("react/") || specifier.startsWith("react-");
}

function collectSourceRecords() {
  return collectSourceFiles(srcDir).map((absPath) => {
    const relPath = normalizePath(path.relative(srcDir, absPath));
    const source = fs.readFileSync(absPath, "utf8");
    const specifiers = extractImportSpecifiers(source);
    return {
      absPath,
      relPath,
      zone: classifyRelativeToSrc(relPath),
      source,
      specifiers,
    };
  });
}

describe("프론트엔드 DDD 아키텍처 경계 및 의존 방향 규칙", () => {
  it("레거시 폴더(features, layout, components, hooks, styles, utils, api)가 src 아래에 존재하지 않는다", () => {
    const existingLegacy = LEGACY_ENTRIES.filter((entry) =>
      fs.existsSync(path.join(srcDir, entry)),
    );
    expect(existingLegacy).toEqual([]);
  });

  it("domains/*/model 계층은 React나 상위 계층(api, application, ui, app)을 import하지 않는다", () => {
    const records = collectSourceRecords().filter(
      (r) => r.zone.kind === "domain-layer" && r.zone.layer === "model",
    );
    expect(records.length).toBeGreaterThan(0);

    const violations: string[] = [];
    for (const file of records) {
      for (const spec of file.specifiers) {
        if (isReactPackage(spec)) {
          violations.push(`${file.relPath} -> ${spec} (React import 금지)`);
          continue;
        }
        const targetRel = resolveImportTarget(file.absPath, spec);
        if (!targetRel) continue;
        const targetZone = classifyRelativeToSrc(targetRel);
        const currentDomain = (file.zone as { domain: string }).domain;
        if (targetZone.kind === "app" || targetZone.kind === "shared") {
          violations.push(`${file.relPath} -> ${spec} (${targetZone.kind} 계층 import 금지)`);
        } else if (targetZone.kind === "domain-index" && targetZone.domain === currentDomain) {
          violations.push(`${file.relPath} -> ${spec} (자기 도메인의 index.ts 순환 import 금지)`);
        } else if (targetZone.kind === "domain-layer") {
          if (targetZone.domain === currentDomain && targetZone.layer !== "model") {
            violations.push(`${file.relPath} -> ${spec} (model은 ${targetZone.layer} 계층 import 금지)`);
          }
          if (targetZone.domain !== currentDomain) {
            violations.push(`${file.relPath} -> ${spec} (타 도메인 내부 경로 직접 import 금지)`);
          }
        }
      }

      const codeOnly = stripComments(file.source, true);
      if (/\bfetch\s*\(/.test(codeOnly) || /\b(?:window|document)\./.test(codeOnly)) {
        violations.push(`${file.relPath} (fetch 또는 DOM 전역 접근 금지)`);
      }
    }

    expect(violations).toEqual([]);
  });

  it("domains/*/ui 계층은 같은 도메인의 api 계층을 직접 import하지 않는다", () => {
    const records = collectSourceRecords().filter(
      (r) => r.zone.kind === "domain-layer" && r.zone.layer === "ui",
    );
    expect(records.length).toBeGreaterThan(0);

    const violations: string[] = [];
    for (const file of records) {
      const currentDomain = (file.zone as { domain: string }).domain;
      for (const spec of file.specifiers) {
        const targetRel = resolveImportTarget(file.absPath, spec);
        if (!targetRel) continue;
        const targetZone = classifyRelativeToSrc(targetRel);
        if (targetZone.kind === "app") {
          violations.push(`${file.relPath} -> ${spec} (ui는 app 계층을 import할 수 없다)`);
        } else if (targetZone.kind === "domain-index" && targetZone.domain === currentDomain) {
          violations.push(`${file.relPath} -> ${spec} (자기 도메인의 index.ts 순환 import 금지)`);
        } else if (targetZone.kind === "domain-layer" && targetZone.layer === "api") {
          violations.push(`${file.relPath} -> ${spec} (ui는 api 계층을 직접 import할 수 없다)`);
        }
      }
    }

    expect(violations).toEqual([]);
  });

  it("domains/*/api와 domains/*/application 계층은 ui나 app 계층을 역방향으로 import하지 않는다", () => {
    const records = collectSourceRecords().filter(
      (r) => r.zone.kind === "domain-layer" && (r.zone.layer === "api" || r.zone.layer === "application"),
    );
    expect(records.length).toBeGreaterThan(0);

    const violations: string[] = [];
    for (const file of records) {
      const fileZone = file.zone as { kind: "domain-layer"; domain: string; layer: DomainLayer };
      for (const spec of file.specifiers) {
        if (fileZone.layer === "api" && isReactPackage(spec)) {
          violations.push(`${file.relPath} -> ${spec} (api는 React를 import할 수 없다)`);
        }
        const targetRel = resolveImportTarget(file.absPath, spec);
        if (!targetRel) continue;
        const targetZone = classifyRelativeToSrc(targetRel);
        if (targetZone.kind === "app") {
          violations.push(`${file.relPath} -> ${spec} (${fileZone.layer}은 app을 import할 수 없다)`);
        } else if (targetZone.kind === "domain-index" && targetZone.domain === fileZone.domain) {
          violations.push(`${file.relPath} -> ${spec} (자기 도메인의 index.ts 순환 import 금지)`);
        } else if (targetZone.kind === "domain-layer") {
          if (targetZone.layer === "ui") {
            violations.push(`${file.relPath} -> ${spec} (${fileZone.layer}은 ui를 import할 수 없다)`);
          }
          if (fileZone.layer === "api" && targetZone.layer === "application") {
            violations.push(`${file.relPath} -> ${spec} (api는 application을 import할 수 없다)`);
          }
        }
      }
    }

    expect(violations).toEqual([]);
  });

  it("한 도메인이 다른 도메인을 참조할 때는 반드시 상대 도메인의 index.ts를 통해서만 import한다", () => {
    const records = collectSourceRecords().filter(
      (r) => r.zone.kind === "domain-layer" || r.zone.kind === "domain-index",
    );

    const violations: string[] = [];
    for (const file of records) {
      const currentDomain = (file.zone as { domain: string }).domain;
      for (const spec of file.specifiers) {
        const targetRel = resolveImportTarget(file.absPath, spec);
        if (!targetRel) continue;
        const targetZone = classifyRelativeToSrc(targetRel);
        if (targetZone.kind === "domain-layer" && targetZone.domain !== currentDomain) {
          violations.push(`${file.relPath} -> ${spec} (타 도메인 ${targetZone.domain}의 index.ts만 import 가능)`);
        }
      }
    }

    expect(violations).toEqual([]);
  });

  it("app 계층은 도메인 내부 경로가 아니라 각 도메인의 index.ts만 import한다", () => {
    const records = collectSourceRecords().filter((r) => r.zone.kind === "app");
    expect(records.length).toBeGreaterThan(0);

    const violations: string[] = [];
    for (const file of records) {
      for (const spec of file.specifiers) {
        const targetRel = resolveImportTarget(file.absPath, spec);
        if (!targetRel) continue;
        const targetZone = classifyRelativeToSrc(targetRel);
        if (targetZone.kind === "domain-layer") {
          violations.push(`${file.relPath} -> ${spec} (app은 domains/${targetZone.domain}/index.ts만 import 가능)`);
        }
      }
    }

    expect(violations).toEqual([]);
  });

  it("shared 계층은 domains나 app 계층을 역방향으로 import하지 않는다", () => {
    const records = collectSourceRecords().filter((r) => r.zone.kind === "shared");
    expect(records.length).toBeGreaterThan(0);

    const violations: string[] = [];
    for (const file of records) {
      for (const spec of file.specifiers) {
        const targetRel = resolveImportTarget(file.absPath, spec);
        if (!targetRel) continue;
        const targetZone = classifyRelativeToSrc(targetRel);
        if (targetZone.kind === "domain-layer" || targetZone.kind === "domain-index" || targetZone.kind === "app") {
          violations.push(`${file.relPath} -> ${spec} (shared는 ${targetZone.kind}를 import할 수 없다)`);
        }
      }
    }

    expect(violations).toEqual([]);
  });
});
