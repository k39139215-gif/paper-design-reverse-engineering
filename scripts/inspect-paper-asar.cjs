const fs = require('node:fs');
const archivePath = 'C:/Program Files/Paper/resources/app.asar';
const archive = fs.openSync(archivePath, 'r');
const prefix = Buffer.alloc(16);
fs.readSync(archive, prefix, 0, 16, 0);
const headerSize = prefix.readUInt32LE(4);
const jsonSize = prefix.readUInt32LE(12);
const json = Buffer.alloc(jsonSize);
fs.readSync(archive, json, 0, jsonSize, 16);
const header = JSON.parse(json.toString('utf8'));
const records = [];
function walk(files, base = '') {
  for (const [name, item] of Object.entries(files)) {
    const path = base ? `${base}/${name}` : name;
    if (item.files) walk(item.files, path);
    else records.push({ path, ...item });
  }
}
walk(header.files);
function read(path) {
  const record = records.find(r => r.path === path);
  if (!record || record.unpacked || !record.size) return '';
  const bytes = Buffer.alloc(record.size);
  fs.readSync(archive, bytes, 0, bytes.length, 8 + headerSize + Number(record.offset));
  return bytes.toString('utf8');
}
const packageJson = read('package.json');
const mode = process.argv[2];
if (mode === 'list') {
  console.log(records.filter(r => !r.path.startsWith('node_modules/')).map(r => `${r.path} (${r.size})`).join('\n'));
  fs.closeSync(archive);
  process.exit(0);
}
if (mode === 'read') {
  for (const path of process.argv.slice(3)) {
    if (/\.env|auth\/auth\.|storage\./.test(path)) continue;
    console.log(JSON.stringify({path,source:read(path)},null,2));
  }
  fs.closeSync(archive);
  process.exit(0);
}
console.log(JSON.stringify({
  archivePath, headerSize, jsonSize, fileCount: records.length,
  package: packageJson ? JSON.parse(packageJson) : null,
  ownFiles: records.filter(r => !r.path.startsWith('node_modules/')).map(r => ({ path: r.path, size: r.size })).slice(0, 55),
  relevantPackages: records.filter(r => /(?:electron|todesktop|react|yjs|automerge|liveblocks|replicache|workos|base-ui|shaders|supabase|instantdb|convex|colyseus|trpc|tanstack|sentry|posthog|zustand|jotai|mobx)[^/]*\/package\.json$/.test(r.path)).map(r => ({path:r.path, data:JSON.parse(read(r.path) || '{}')})).map(r=>({path:r.path,name:r.data.name,version:r.data.version})),
}, null, 2));
fs.closeSync(archive);
