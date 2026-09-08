#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { dirname, isAbsolute, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildPresetShapeCatalog,
  loadPinnedPresetShapeDefinitions,
  stableJson,
} from './source-validator.mjs';
import {
  compilePresetShapeDefinitions,
  evaluatePresetShape,
  summarizePresetGeometryIr,
} from './geometry-ir.mjs';

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const defaultRepositoryRoot = resolve(scriptDirectory, '../..');
const defaultOutput = 'scripts/ooxml-geometry/generated/preset-shape-catalog.json';
const evaluationProfiles = Object.freeze([
  { name: 'square', width: 216, height: 216 },
  { name: 'wide', width: 400, height: 180 },
  { name: 'tall', width: 180, height: 400 },
]);

async function readJson(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

export async function writeOrCheckGeneratedCatalog({ check = false, generated, outputPath }) {
  if (check) {
    let current;
    try {
      current = await readFile(outputPath, 'utf8');
    } catch (error) {
      if (error?.code === 'ENOENT') {
        throw new Error(`Generated OOXML geometry catalog is missing: ${outputPath}`);
      }
      throw error;
    }
    if (current !== generated) {
      throw new Error(
        `Generated OOXML geometry catalog is stale: ${outputPath}. Run pnpm geometry:generate.`,
      );
    }
    return { outputPath, status: 'current' };
  }

  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, generated, 'utf8');
  return { outputPath, status: 'generated' };
}

export function buildGeometryIrContract(ir) {
  const structuralBytes = stableJson({ schemaVersion: ir.schemaVersion, shapes: ir.shapes });
  const profiles = evaluationProfiles.map((profile) => {
    for (const shape of ir.shapes) {
      evaluatePresetShape(shape, profile);
    }
    return { ...profile, evaluatedShapes: ir.shapes.length };
  });
  return {
    schemaVersion: ir.schemaVersion,
    structuralSha256: createHash('sha256').update(structuralBytes).digest('hex'),
    summary: summarizePresetGeometryIr(ir),
    evaluationProfiles: profiles,
  };
}

function parseArguments(arguments_) {
  const options = { check: false, output: defaultOutput, repositoryRoot: defaultRepositoryRoot };
  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];
    if (argument === '--check') {
      options.check = true;
      continue;
    }
    if (argument === '--output') {
      const value = arguments_[index + 1];
      if (!value) throw new Error('--output requires a path');
      options.output = value;
      index += 1;
      continue;
    }
    if (argument === '--root') {
      const value = arguments_[index + 1];
      if (!value) throw new Error('--root requires a path');
      options.repositoryRoot = resolve(value);
      index += 1;
      continue;
    }
    throw new Error(`Unknown argument: ${argument}`);
  }
  return options;
}

export async function generatePresetShapeCatalog({
  check = false,
  output = defaultOutput,
  repositoryRoot = defaultRepositoryRoot,
} = {}) {
  const manifestPath = resolve(repositoryRoot, 'scripts/ooxml-geometry/source-manifest.json');
  const reconciliationPath = resolve(
    repositoryRoot,
    'scripts/ooxml-geometry/source-reconciliation.json',
  );
  const manifest = await readJson(manifestPath);
  const reconciliation = await readJson(reconciliationPath);
  const source = await loadPinnedPresetShapeDefinitions(repositoryRoot, manifest);
  const sourceCatalog = buildPresetShapeCatalog(source.xml, manifest, reconciliation);
  const geometryIr = compilePresetShapeDefinitions(source.xml, manifest, reconciliation);
  const catalog = { ...sourceCatalog, geometryIr: buildGeometryIrContract(geometryIr) };
  const generated = stableJson(catalog);
  const outputPath = isAbsolute(output) ? output : resolve(repositoryRoot, output);
  const persisted = await writeOrCheckGeneratedCatalog({ check, generated, outputPath });
  return { catalog, ...persisted };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  const result = await generatePresetShapeCatalog(options);
  const summary = result.catalog.summary;
  console.log(
    `${result.status}: ${result.outputPath} (${summary.uniqueShapes} shapes, ${summary.guideFormulas} formulas, ${summary.paths} paths)`,
  );
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
