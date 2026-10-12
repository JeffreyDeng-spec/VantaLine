// Real React workbench with isolated synthetic APIs/media. No physical PLC or production requests.
import {createServer} from 'vite';
import react from '@vitejs/plugin-react';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url));
const exports=[...readFileSync(root+'src/api/queries.ts','utf8').matchAll(/export (?:async )?function (\w+)\(/g)].map(m=>m[1]);
const task={id:'demo',name:'JHC20261010',model_id:'ai_detection__task_demo',accessory_count:3,accessory_names:['投影笔','鼠标','记号笔'],selected_accessory_ids:['pen','mouse','marker'],required_accessory_counts:{pen:1,mouse:1,marker:1},status:'ready',updated_at:1};
const stub=`const task=${JSON.stringify(task)};const model={id:task.model_id,label:'AI 检测',exists:true,is_ai_detection:true,variant:'ai_detection',task_id:'demo'};
const config={schema_version:5,transport_mode:'web_serial',profile_id:'mitsubishi_fx3ga_40mr',protocol:'fx_programming_port_ascii',checksum_mode:'include_etx',enabled:true,baudrate:9600,data_bits:7,parity:'E',stop_bits:1,result_register:'D206',output_control_point:'',capture_trigger_enabled:true,capture_input_register:'D0',capture_trigger_value:1,capture_poll_interval_ms:200,ack_timeout_ms:500,retries:0};
export const queryKeys=new Proxy({},{get:(_,k)=>{const f=(...args)=>[k,...args];return ['plcWorkstation','plcWorkstations'].includes(k)?[k]:f}});
async function response(name,args){if(name==='getServiceStatus')return {model_exists:true,active_model_id:model.id,available_models:[model],ai_detection:{status:'ready'},ai_detection_tasks:[task],classes:[],rule:{required_classes:[],min_counts:{}}};
if(name==='getTrainingResources')return {ai_detection_tasks:[task],tasks:[]};if(name==='getPipeline')return {items:[]};if(name==='getAiTasks')return {tasks:[task]};if(name==='getPlcWorkstation')return {paired:true,station:{id:'line',name:'包装配件漏件检测'},config,config_generation:1,protocol_version:'plc-web-serial-v4',lease:null};if(name==='analyzeCamera'||name==='analyzeImage')return {passed:false,request_id:'fixture-result',model:'AI',detections:[{accessory_id:'pen',label:'投影笔',present:false,required:1,confidence:.98},{accessory_id:'mouse',label:'鼠标',present:true,required:1,confidence:.98},{accessory_id:'marker',label:'记号笔',present:true,required:1,confidence:.98}],rule:null,ai:{status:'ready',latency_ms:1280},plc_sync:{status:'disabled'},preview_url:'/__fixture.svg'};return {items:[],tasks:[]};}
${exports.map(name=>`export const ${name}=(...args)=>response('${name}',args);`).join('\n')}`;
const auth=`import React,{createContext,useContext,useState} from 'react';const initial={user:{id:'fixture',username:'operator',role:new URLSearchParams(location.search).get('role')==='admin'?'admin':'user',permissions:['inspection','ai_detection']},dataUserId:'',loading:false};export const AuthContext=createContext(initial);export function FixtureAuthProvider({children}){const [dataUserId,setDataUserId]=useState('');return React.createElement(AuthContext.Provider,{value:{...initial,dataUserId,setDataUserId}},children)}export const useAuth=()=>useContext(AuthContext);export const hasPermission=()=>true;`;
const server=await createServer({root,configFile:false,define:{__VANTALINE_RELEASE_IDENTITY__:JSON.stringify("VANTALINE_RELEASE:development:unknown")},server:{host:'127.0.0.1',port:8801},plugins:[react(),{
 name:'normal-inspection-fixture',enforce:'pre',
 resolveId(id){if(id==='/__entry.tsx')return id;if(id.endsWith('/api/queries'))return '\0queries';if(id.endsWith('/api/client'))return '\0client';if(id.endsWith('/auth/auth-context'))return '\0auth';if(id.endsWith('/agent/useAgentActions'))return '\0agent';},
 load(id){if(id==='\0queries')return stub;if(id==='\0auth')return auth;if(id==='\0agent')return 'export function useAgentActions() {}';if(id==='\0client')return `export class ApiError extends Error {} export const withAuthScope=p=>p;export const apiClient={get:async p=>p.includes('real-photo')?{}:{items:[],next_offset:null},post:async()=>({})};`;
 if(id==='/__entry.tsx')return `import React,{useState} from 'react';import {createPortal} from 'react-dom';import {InspectionScopeTarget} from '/src/components/InspectionScopeTarget.ts';import {FixtureAuthProvider,useAuth} from '/src/features/auth/auth-context';import {createRoot} from 'react-dom/client';import {BrowserRouter,Routes,Route,Link} from 'react-router-dom';import {QueryClient,QueryClientProvider} from '@tanstack/react-query';import {AppToastProvider} from '/src/components/ToastProvider.tsx';import {DetectionWorkbenchPage} from '/src/features/detection/DetectionWorkbenchPage.tsx';import '/src/styles/global.css';
Object.defineProperty(navigator,'serial',{configurable:true,value:undefined});
const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;const ctx=canvas.getContext('2d');ctx.fillStyle='#23354a';ctx.fillRect(0,0,1280,720);ctx.fillStyle='#c6d4e8';ctx.font='30px sans-serif';ctx.fillText('Synthetic camera fixture',48,70);
Object.defineProperty(navigator,'mediaDevices',{configurable:true,value:{enumerateDevices:async()=>[{deviceId:'fixture',kind:'videoinput',label:'FHD Camera'}],getUserMedia:async()=>{const stream=canvas.captureStream(0);const track=stream.getVideoTracks()[0];const timer=setInterval(()=>{ctx.fillStyle='#23354a';ctx.fillRect(0,0,1280,720);ctx.fillStyle='#c6d4e8';ctx.fillText('Synthetic camera fixture',48,70);track.requestFrame?.();if(track.readyState==='ended')clearInterval(timer)},100);return stream},addEventListener(){},removeEventListener(){}}});
function FixtureShell(){const auth=useAuth();const [inspectionScopeTarget,setInspectionScopeTarget]=useState(null);const userManagementActive=false;const usersQuery={data:{users:[{id:'fixture',username:'operator',display_name:'测试操作员'}]}};const dataScopeControl=(
            <label>
              数据范围
              <select value={auth.dataUserId} onChange={(event) => auth.setDataUserId(event.currentTarget.value)}>
                <option value="">全部用户与历史数据</option>
                <option value="legacy_admin">历史数据</option>
                {(usersQuery.data?.users || []).map((user) => (
                  <option value={user.id} key={user.id}>
                    {user.display_name || user.username}
                  </option>
                ))}
              </select>
            </label>
);return <InspectionScopeTarget.Provider value={setInspectionScopeTarget}><div className="app-shell"><aside className="sidebar"><div className="brand-block"><div className="brand-mark">VL</div><div className="brand-copy">VantaLine</div></div><nav className="side-nav"><Link className="nav-item" to="/workspace/about" title="其他页面">检测<span>其他页面</span></Link></nav></aside><main className="workspace">        {auth.user.role === "admin" && !userManagementActive ? (
          inspectionScopeTarget
            ? createPortal(<div className="normal-data-scope">{dataScopeControl}</div>, inspectionScopeTarget)
            : <div className="top-scope-bar">{dataScopeControl}</div>
        ) : null}<Routes><Route path="/workspace/about" element={<Link to="/workspace/tasks/ai%3Ademo/inspect">返回检测</Link>}/><Route path="/workspace/tasks/:taskId/inspect" element={<DetectionWorkbenchPage mode="inspect"/>}/></Routes></main></div></InspectionScopeTarget.Provider>};createRoot(document.getElementById('root')).render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><FixtureAuthProvider><AppToastProvider><BrowserRouter><FixtureShell/></BrowserRouter></AppToastProvider></FixtureAuthProvider></QueryClientProvider>);`;},
 configureServer(s){s.middlewares.use(async(req,res,next)=>{if(req.url.startsWith('/__fixture.svg')){res.setHeader('Content-Type','image/png');res.end(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64'));return;}if(req.url.startsWith('/api/')){res.setHeader('Content-Type','application/json');res.end('{}');return;}if(!req.url.startsWith('/workspace/'))return next();res.setHeader('Content-Type','text/html');res.end(await s.transformIndexHtml(req.url,'<html><body><div id="root"></div><script type="module" src="/__entry.tsx"></script></body></html>'));});}
}]});
await server.listen();console.log('Isolated normal inspection fixture: http://127.0.0.1:8801/workspace/tasks/ai%3Ademo/inspect');
