// Generate typed adapters from the same functions the UI calls. No runtime eval.
import ts from 'typescript';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const program = ts.createProgram([path.join(root, 'src/api/queries.ts')], { strict: true, target: ts.ScriptTarget.ES2020, moduleResolution: ts.ModuleResolutionKind.Bundler, module: ts.ModuleKind.ESNext, skipLibCheck: true });
const checker = program.getTypeChecker();
const source = program.getSourceFile(path.join(root, 'src/api/queries.ts'));
const groups = {
  core: 'getAuthStatus getTaskNavigationPreferences saveTaskNavigationPreferences getServiceStatus getConfigSummary',
  detection: 'warmupYoloModel getAiTasks getAiTaskAutoOptimize updateAiTaskAutoOptimize uploadAiTaskEnvironmentBackground deleteAiTaskAutoOptimizeSample retryAiTaskAutoOptimizeSample approveAiTaskAutoOptimizeSample updateTaskRules deleteAiTask',
  accessories: 'getAccessories getAccessoryCandidate previewAccessory createAccessory confirmAccessory addAccessoryFiles deleteAccessory setAccessoryRoute',
  text: 'listTextInspectionStandards getTextInspectionStandard classifyTextInspectionStandard deleteTextInspectionStandard importTextInspectionStandard addTextInspectionStandardAsset patchTextInspectionAsset confirmTextInspectionStandard getIncomingTextTask getIncomingTextInspectors uploadIncomingTextReference saveIncomingTextRules cloneIncomingTextReference inspectIncomingText reviewIncomingTextInspection getIncomingTextInspections compareTextInspectionLabel',
  training: 'getTrainingResources getTrainingDatasetDetail updateTrainingDataset deleteTrainingDataset deleteTrainingDatasetSample updateTrainingModel deleteTrainingModel updateTrainingTask',
  pipeline: 'getPipeline createPipelineTask updatePipelineTask deletePipelineTask advancePipelineTask pausePipelineTask sendPipelineAgentFeedback sendPipelineAgentChat addPipelineAccessory removePipelineAccessory getAgentRecommendation',
  analysis: 'getDataAnalysisRecords getDataAnalysisRecord',
  settings: 'updateRules getAgentConfig saveAgentConfig testAgentConfig getAiConfig saveAiConfig deleteActiveAiKey getApiCostLedger getPlcConfig savePlcConfig getPlcWorkstation listPlcWorkstations pairPlcWorkstation savePlcWorkstationConfig verifyPlcWorkstationProfile',
  users: 'getUsers updateUser deleteUser'
};
const exceptions = {
  getAccessoryDetail: 'asset-adapter: accessoryActions supplies opaque asset IDs',
  cropAccessoryTextImage: 'asset-adapter: accessoryActions resolves current owned asset ID',
  setAccessoryAiReference: 'asset-adapter: accessoryActions resolves current owned asset ID',
  deleteAccessoryFile: 'asset-adapter: accessoryActions resolves current owned asset ID',
  createUser: 'secure-input: password must be entered in the account form',
  resetUserPassword: 'secure-input: password must not enter tool arguments/results',
  analyzeImage: 'workspace: use detection_run_image for visible result synchronization',
  analyzeCamera: 'workspace: dedicated capture callback owns camera provenance and dispatch',
  analyzeVideo: 'workspace: use detection_run_video for visible result synchronization',
  analyzeTextCompareBeta: 'retired: current workspace uses text-inspection label/compare',
  getLocateConfig: 'retired: LocateAnything is removed from current navigation',
  saveLocateConfig: 'retired: LocateAnything', getLocateStatus: 'retired: LocateAnything', startLocateRuntime: 'retired: LocateAnything', getLocateAccessories: 'retired: LocateAnything', inspectLocateAnything: 'retired: LocateAnything', locateAnythingPrompt: 'retired: LocateAnything',
  getLabelSheetReferences: 'retired: legacy label sheet flow', addLabelSheetReferences: 'retired: legacy label sheet flow', matchLabelSheet: 'retired: legacy label sheet flow',
  claimPlcWorkstationConnection: 'controller: lease creation belongs to WebSerial controller', activatePlcWorkstationConnection: 'controller: WebSerial controller', heartbeatPlcWorkstationConnection: 'controller: WebSerial controller', rebindPlcWorkstationModel: 'controller: WebSerial controller', disconnectPlcWorkstationConnection: 'controller: WebSerial controller', declarePlcWebSerialAttempt: 'controller: WebSerial controller', sendPlcWebSerialReceipt: 'controller: WebSerial controller', getPlcWebSerialDiagnosticPlan: 'controller: WebSerial controller', finishPlcWebSerialDiagnostic: 'controller: WebSerial controller', confirmPlcWebSerialDiagnostic: 'controller: WebSerial controller'
};
const accessoryFields = ['name','material_type','material_alpha_policy','training_role','pipeline_context','paper_preset','paper_width_mm','paper_height_mm','object_length_mm','object_width_mm','object_height_mm','size_reference','files'];
const formFields = {
  uploadAiTaskEnvironmentBackground: ['file', 'source'], previewAccessory: accessoryFields, createAccessory: [...accessoryFields,'class_id'], addAccessoryFiles: ['files'],
  importTextInspectionStandard: ['file','name','material_code','version_label','standard_type'], addTextInspectionStandardAsset: ['file','expected_revision'], uploadIncomingTextReference: ['file','version_label'], inspectIncomingText: ['file','capture_id'], compareTextInspectionLabel: ['captured_file','standard_asset_id','comparison_id','extraction_id']
};
const object = (properties, required = []) => ({ type: 'object', properties, required, additionalProperties: false });
const secret = /(^|_)(password|api_key|image_api_key|secret|token)(_|$)/i;
function schema(type, depth = 0, ancestors = new Set()) {
  if (depth > 10 || ancestors.has(type)) return object({});
  if (type.flags & ts.TypeFlags.StringLiteral) return {type:'string',enum:[type.value]};
  if (type.flags & ts.TypeFlags.NumberLiteral) return {type:'number',enum:[type.value]};
  if (type.flags & ts.TypeFlags.BooleanLiteral) return {type:'boolean',enum:[type.intrinsicName === 'true']};
  if (type.flags & ts.TypeFlags.String) return {type:'string',maxLength:8192};
  if (type.flags & ts.TypeFlags.Number) return {type:'number'};
  if (type.flags & ts.TypeFlags.Boolean) return {type:'boolean'};
  if (type.flags & ts.TypeFlags.Null) return {type:'null'};
  if (type.isUnion()) return {anyOf:type.types.filter(t=>!(t.flags & ts.TypeFlags.Undefined)).map(t=>schema(t,depth+1,ancestors))};
  if (checker.isArrayType(type)) return {type:'array',items:schema(checker.getTypeArguments(type)[0],depth+1,ancestors),maxItems:500};
  const next = new Set(ancestors); next.add(type);
  const props = {}, required = [];
  for (const prop of type.getProperties()) {
    if (secret.test(prop.name) || ['base_url','image_base_url','endpoint_url','api_key_env','image_api_key_env'].includes(prop.name)) continue;
    const declaration = prop.valueDeclaration || prop.declarations?.[0];
    if (!declaration) continue;
    props[prop.name] = schema(checker.getTypeOfSymbolAtLocation(prop,declaration),depth+1,next);
    if (!(prop.flags & ts.SymbolFlags.Optional)) required.push(prop.name);
  }
  const index = checker.getIndexTypeOfType(type, ts.IndexKind.String);
  return {...object(props,required), ...(index ? {additionalProperties:schema(index,depth+1,next)} : {})};
}
const actions=[], manifest=[];
for (const fn of source.statements.filter(n=>ts.isFunctionDeclaration(n) && n.modifiers?.some(m=>m.kind===ts.SyntaxKind.ExportKeyword))) {
  const name=fn.name.text;
  const domain=Object.entries(groups).find(([,names])=>names.split(' ').includes(name))?.[0];
  if (!domain) { if (!exceptions[name]) throw new Error(`Unmapped public UI function: ${name}`); manifest.push({source:name,status:exceptions[name]}); continue; }
  const properties={}, required=[], args=[];
  for(const param of fn.parameters) {
    const key=param.name.getText(source), type=checker.getTypeAtLocation(param), typeName=checker.typeToString(type);
    if(key==='auth') { args.push('getAuth()'); continue; }
    if(key==='options') { args.push('undefined'); continue; }
    if(typeName==='FormData') {
      const fields=formFields[name]; if(!fields) throw new Error(`Missing multipart fields for ${name}`);
      const fileNames=fields.filter(x=>x==='file'||x==='files'||x==='captured_file');
      properties[key]=object({fields:object(Object.fromEntries(fields.filter(x=>!fileNames.includes(x)).map(x=>[x,{type:'string',maxLength:8192}]))),files:object(Object.fromEntries(fileNames.map(x=>[x,{type:'array',items:{type:'string'},maxItems:x==='files'?50:1}])))});
      args.push(`buildForm(input.${key} as Parameters<typeof buildForm>[0])`);
    } else { properties[key]=schema(type); args.push(`input.${key}`); }
    if(!param.questionToken && !param.initializer) required.push(key);
  }
  const tool=name.replace(/[A-Z]/g,x=>'_'+x.toLowerCase());
  const readOnly=/^(get|list)/.test(name);
  const permissions = domain==='users'?['user_management']: domain==='settings'? name.includes('Agent')?['agent_config']:name.includes('Ai')||name==='getApiCostLedger'||name==='deleteActiveAiKey'?['ai_config']:['system_settings']:domain==='text'?['inspection']:domain==='accessories'?['accessory_library']:domain==='training'?['model_library','training_pipeline']:domain==='pipeline'?['training_pipeline','incoming_material_config']:domain==='analysis'||domain==='detection'?['ai_detection','inspection']:[];
  const invalidates = {core:['user','status','config'],detection:['ai','training'],accessories:['accessories','training'],text:['text-inspection','incomingText'],training:['training'],pipeline:['pipeline','training','accessories','ai'],analysis:['dataAnalysis'],settings:['config','agent','ai','plc','admin'],users:['auth','users']}[domain];
  const definition={name:tool,domain,description:`${name.replace(/([A-Z])/g,' $1').trim()}. ${readOnly?'Read current authorized application data.':'Execute the existing application operation and refresh its visible data.'}`,inputSchema:object(properties,required),readOnly,permissions,...(!readOnly?{invalidates}:{})};
  actions.push(`  { ...${JSON.stringify(definition)}, execute: input => queries.${name}(...[${args.join(', ')}] as Parameters<typeof queries.${name}>) }`);
  manifest.push({name:tool,source:name,domain,inputSchema:definition.inputSchema,status:'api-adapter',ui:'src/api/queries.ts'});
}
const output=`// Generated by scripts/generate-agent-tools.mjs. Do not edit.\nimport * as queries from '../../api/queries';\nimport type { AuthContextValue } from '../auth/auth-context';\nimport type { ActionDefinition } from './contracts';\nimport { buildForm } from './files';\nexport function apiActions(getAuth: () => AuthContextValue): ActionDefinition[] { return [\n${actions.join(',\n')}\n]; }\n`;
const outputs=[['src/features/agent/apiActions.generated.ts',output],['src/features/agent/api-manifest.generated.json',JSON.stringify(manifest,null,2)+'\n']];
for (const [file,content] of outputs) {
  const target=path.join(root,file);
  if(process.argv.includes('--check')) { if(fs.readFileSync(target,'utf8')!==content) throw new Error(`Stale generated action contract: ${file}`); }
  else fs.writeFileSync(target,content);
}
console.log(`${actions.length} API adapters; ${manifest.length} exported functions accounted for (workspace/secure/controller exceptions require separate coverage).`);
