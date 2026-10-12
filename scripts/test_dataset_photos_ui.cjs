// Actual React administrator page, synthetic API/media only; no production writes.
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs'),os=require('node:os');
const {spawn}=require('node:child_process');
const frontend=path.resolve(__dirname,'../local_inspection_service/frontend');
const {chromium}=require(path.join(frontend,'node_modules/playwright'));
const output=fs.mkdtempSync(path.join(os.tmpdir(),'dataset-photos-ui-'));
const base='http://127.0.0.1:5194';
const vite=spawn(process.execPath,[path.join(frontend,'node_modules/vite/bin/vite.js'),'--host','127.0.0.1','--port','5194','--strictPort','--base','/'],{cwd:frontend,env:{...process.env,VITE_ROUTER_BASENAME:'/'},stdio:'pipe'});
let browser,page;
(async()=>{
 for(let i=0;i<100;i++){try{if((await fetch(base)).ok)break}catch{}await new Promise(r=>setTimeout(r,100))}
 browser=await chromium.launch({channel:process.env.ADMIN_TEST_BROWSER||(process.platform==='darwin'?'chrome':undefined),headless:true});
 page=await browser.newPage({viewport:{width:1440,height:1000}});
 const errors=[],writes=[],requests=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{const original=window.setInterval;window.setInterval=(fn,delay,...args)=>original(fn,delay===30000?500:delay,...args);window.__fixtureHidden=false;Object.defineProperty(document,'hidden',{get:()=>window.__fixtureHidden})});
 const features={user_management:'用户与权限管理',inspection:'检测工作台'};
 const admin={id:'admin',username:'admin',role:'admin',active:true,permissions:Object.keys(features)};
 const user={id:'a',username:'owner',display_name:'模拟账号',role:'user',active:true,permissions:['inspection']};
 const statuses=['eligible','excluded','uncertain','processing','annotation_failed','disabled','not_collected','unknown'];
 let photos=Array.from({length:105},(_,i)=>({record_id:'r'+String(i).padStart(3,'0'),task_id:i%2?'t1':'t2',task_name:i%2?'一号任务':'二号任务',created_at:i+1,status:statuses[i%8],reason:'模拟筛选理由',image_type:'original',image_url:`/api/auth/users/a/data/detection-photos/r${String(i).padStart(3,'0')}/image`,memberships:i%8===0?[{dataset_id:'d1',name:'冻结版本一',splits:['train','val'],member_count:1}]:[],samples:[{sample_id:'s'+i,mode:'real_photo',status:statuses[i%8],reason:'模拟理由',versions_url:'/api/auth/users/a/data/tasks/t1/samples/s'+i+'/versions'}]}));
 let failed=false,historyReads=0;
 function photoPage(url){const task=url.searchParams.get('task_id'),status=url.searchParams.get('status');const all=photos.filter(p=>!task||p.task_id===task);const matched=all.filter(p=>!status||(status==='included'?p.memberships.length:p.status===status));const cursor=url.searchParams.get('cursor');let anchor=Infinity,start=0;if(cursor){[anchor,start]=cursor.split(':').map(Number)}const anchored=matched.filter(p=>p.created_at<=anchor);const items=anchored.slice(start,start+24);const high=items[0]?.created_at||anchor;const counts=Object.fromEntries(statuses.map(s=>[s,all.filter(p=>p.status===s).length]));counts.included=all.filter(p=>p.memberships.length).length;return {items,total:matched.length,record_total:all.length,counts,next_cursor:start+24<anchored.length?`${anchor===Infinity?high:anchor}:${start+24}`:null,refresh_cursor:anchored.length?`${anchor===Infinity?high:anchor}:0`:null,latest_record_id:items[0]?.record_id||null,revision:String(photos.length),tasks:[{id:'t1',name:'一号任务'},{id:'t2',name:'二号任务'}]}}
 photos.reverse();
 await page.route('**/static/brand-logo.png?*',r=>r.fulfill({contentType:'image/png',path:path.join(frontend,'../static/brand-logo.png')}));
 await page.route('**/api/**',async r=>{
  const req=r.request(),u=new URL(req.url()),p=u.pathname;if(!p.startsWith('/api/'))return r.continue();requests.push(p);if(!['GET','HEAD'].includes(req.method()))writes.push(p);const reply=(json,status=200)=>r.fulfill({json,status});
  if(p==='/api/auth/status')return reply({authenticated:true,user:admin,features,default_user_permissions:['inspection'],setup_required:false});
  if(p==='/api/auth/users')return reply({users:[admin,user],features,default_user_permissions:['inspection']});
  if(p==='/api/user/preferences/tasks')return reply({exists:true,pinned_task_ids:[],archived_task_ids:[]});
  if(p==='/api/auth/users-data-summary')return reply({counts:{a:{tasks:2,training:0},admin:{tasks:0,training:0}}});
  if(p==='/api/auth/users/a/data')return reply({user,actor:admin,tasks:[],resources:[{kind:'dataset',resource_id:'d1',display_name:'冻结版本一',sample_count:105,archived:false},{kind:'dataset',resource_id:'history',display_name:'历史缺清单',sample_count:20,archived:false}],references:[],real_photo:[],legacy_feedback:[],audit:[],business:{},counts:{tasks:2,training:0,images:105,resources:2}});
  if(p.endsWith('/image')){if(p.includes('r104'))return reply({detail:'fixture missing image'},404);return r.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="60"><rect width="80" height="60" fill="#dbeafe"/><circle cx="40" cy="30" r="18" fill="#2563eb"/></svg>'})}
  if(p.endsWith('/versions')){historyReads++;return reply({annotations:[{version:1,status:'completed'}],reviews:[{decision:'exclude',reason:'模拟旧版本'}]})}
  if(p.endsWith('/detection-photos'))return failed?reply({detail:'模拟读取失败'},503):reply(photoPage(u));
  if(p.includes('/detection-photos/'))return reply(photos.find(x=>x.record_id===p.split('/').pop()));
  if(p.includes('/datasets/')&&p.endsWith('/members')){const historical=p.includes('/history/'),start=u.searchParams.has('cursor')?Number(u.searchParams.get('cursor')):0;return reply({dataset:{id:historical?'history':'d1',name:historical?'历史缺清单':'冻结版本一',sample_count:historical?20:105,members_available:!historical},items:historical?[]:Array.from({length:Math.min(24,105-start)},(_,i)=>({id:String(start+i),sample_id:'s'+(start+i),record_id:'',split:['train','val','test'][i%3],current_status:'disabled',annotation_version:1,image_url:'/api/auth/users/a/data/datasets/d1/members/'+(start+i)+'/image'})),total:historical?0:105,next_cursor:historical||start+24>=105?null:String(start+24),reason:historical?'历史数据集没有可读取的成员清单；不推断其图片组成':null})}
  return reply({});
 });
 await page.goto(base+'/workspace/users');await page.getByRole('button',{name:'管理数据 →'}).last().click();
 await page.getByRole('button',{name:'数据集与模型',exact:true}).click();
 await page.getByRole('heading',{name:'检测照片与筛选状态'}).waitFor();
 await page.getByText('检测记录：105',{exact:true}).waitFor();
 assert.equal(await page.locator('.admin-dataset-photo-grid article').count(),24);
 await page.getByRole('button',{name:'加载更多检测照片'}).click();
 await page.getByRole('button',{name:'查看检测照片 r057'}).waitFor();assert.equal(await page.locator('.admin-dataset-photo-grid article').count(),48);
 await page.getByRole('button',{name:'查看检测照片 r104'}).click();
 await page.getByRole('dialog').getByText('当前合格',{exact:true}).waitFor();assert.equal(historyReads,0);
 await page.getByRole('dialog').getByText('版本历史 · s104',{exact:true}).click();await page.getByRole('dialog').getByText('模拟旧版本',{exact:false}).waitFor();assert.equal(historyReads,1);
 await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click();
 photos.unshift({...photos[0],record_id:'new-photo',created_at:200,image_url:'/api/auth/users/a/data/detection-photos/new-photo/image'});
 await page.getByRole('button',{name:'刷新并查看新增照片'}).waitFor();
 assert.equal(await page.getByRole('button',{name:'查看检测照片 new-photo'}).count(),0);
 assert.equal(await page.locator('.admin-dataset-photo-grid article').count(),48);
 await page.getByRole('button',{name:'刷新并查看新增照片'}).click();await page.getByRole('button',{name:'查看检测照片 new-photo'}).waitFor();assert.equal(await page.locator('.admin-dataset-photo-grid article').count(),24);
 await page.getByLabel('照片状态').selectOption('excluded');await page.getByText('匹配：13',{exact:true}).waitFor();assert.equal(await page.locator('.admin-dataset-photo-grid').getByText('已排除',{exact:true}).count(),13);
 await page.getByLabel('检测任务').selectOption('t1');await page.getByText('检测记录：52',{exact:true}).waitFor();
 await page.getByLabel('照片状态').selectOption('');await page.getByLabel('检测任务').selectOption('');
 await page.getByRole('button',{name:'刷新照片',exact:true}).click();await page.getByRole('button',{name:'查看检测照片 new-photo'}).waitFor();
 await page.locator('.admin-table-wrap tbody tr').filter({hasText:'冻结版本一'}).getByRole('button',{name:'详情',exact:true}).click();
 const dialog=page.getByRole('dialog');await dialog.getByText('冻结版本记录 105 张 · 可读取成员 105 张',{exact:true}).waitFor();
 await dialog.getByRole('button',{name:'加载更多训练图片'}).click();await dialog.getByRole('button',{name:'查看训练图片 47',exact:true}).waitFor();
 await dialog.getByRole('button',{name:'查看训练图片 0',exact:true}).click();await dialog.getByText('当前来源状态：已停用',{exact:true}).waitFor();await dialog.getByRole('button',{name:'返回成员列表'}).click();
 await page.screenshot({path:path.join(output,'frozen-members.png'),fullPage:true});await dialog.getByRole('button',{name:'关闭',exact:true}).click();
 await page.locator('.admin-table-wrap tbody tr').filter({hasText:'历史缺清单'}).getByRole('button',{name:'详情',exact:true}).click();await page.getByRole('dialog').getByText('历史数据集没有可读取的成员清单；不推断其图片组成',{exact:true}).waitFor();await page.getByRole('dialog').getByRole('button',{name:'关闭',exact:true}).click();
 await page.evaluate(()=>window.__fixtureHidden=true);await page.waitForTimeout(700);const readsBefore=requests.filter(p=>p.endsWith('/detection-photos')).length;await page.waitForTimeout(1100);assert.equal(requests.filter(p=>p.endsWith('/detection-photos')).length,readsBefore);await page.evaluate(()=>{window.__fixtureHidden=false;document.dispatchEvent(new Event('visibilitychange'))});
 failed=true;await page.getByRole('alert').filter({hasText:'模拟读取失败'}).waitFor();failed=false;await page.getByRole('button',{name:'刷新照片',exact:true}).click();await page.getByRole('alert').filter({hasText:'模拟读取失败'}).waitFor({state:'hidden'});
 await page.screenshot({path:path.join(output,'photos-desktop.png'),fullPage:true});await page.setViewportSize({width:390,height:844});await page.getByRole('heading',{name:'检测照片与筛选状态'}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(output,'photos-mobile.png'),fullPage:false});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.equal(writes.length,0);assert.deepEqual(errors,[]);
 console.log('PASS actual React photos: paging, scoped filters, current/historical states, lazy history, stable visible-only polling, new arrivals, frozen/orphan members, missing media/manifest, errors, 390px; '+output);
})().catch(async e=>{console.error(e);if(page){console.error((await page.locator('body').innerText()).slice(0,1400));await page.screenshot({path:path.join(output,'failure.png'),fullPage:true});console.error(output)}process.exitCode=1}).finally(async()=>{await browser?.close();vite.kill('SIGTERM')});
