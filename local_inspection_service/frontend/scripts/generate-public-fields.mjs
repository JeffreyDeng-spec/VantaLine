// Closed response vocabulary from public consumers. Debug/provider envelopes are
// additionally denied by the server, even if administrator interfaces mention them.
import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';
import {fileURLToPath} from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Retained business links on the legacy training-status API are independent of current UI usage.
const fields = new Set(['active_training_task_id', 'last_preview_id', 'approved_preview_id', 'preview_urls', 'previews', 'is_real_photo', 'elements', 'checks', 'issues', 'preview', 'original', 'image', 'box', 'polygon', 'source', 'sequence', 'finalized', 'inputs', 'summary', 'items', 'artifacts', 'reviews', 'progress', 'settled', 'total', 'deadline_at']);
function scan(dir) {
  for (const entry of fs.readdirSync(dir, {withFileTypes:true})) {
    const file = path.join(dir,entry.name);
    if(entry.isDirectory()) { if(!['billing'].includes(entry.name))scan(file); continue; }
    if(!/\.tsx?$/.test(file)||entry.name.startsWith('Admin')||file.endsWith('.test.ts'))continue;
    const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true);
    function visit(node) {
      if(ts.isPropertyAccessExpression(node))fields.add(node.name.text);
      if((ts.isPropertySignature(node)||ts.isPropertyAssignment(node)||ts.isShorthandPropertyAssignment(node))&&node.name&&(ts.isIdentifier(node.name)||ts.isStringLiteral(node.name)))fields.add(node.name.text);
      ts.forEachChild(node,visit);
    }
    visit(source);
  }
}
scan(path.join(root,'src'));
const target=path.join(root,'../privacy/public_fields.json');
const output=JSON.stringify([...fields].sort(),null,2)+'\n';
if(process.argv.includes('--check')) {
  if(fs.readFileSync(target,'utf8')!==output)throw new Error('Stale public response vocabulary');
} else fs.writeFileSync(target,output);
console.log(`${fields.size} public response field names`);
