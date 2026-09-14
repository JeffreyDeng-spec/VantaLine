import { useRef, useState, type PointerEvent } from 'react';
import { labels, mediaURL, type Box, type Region, type Task } from './api';
export const dimensions: Record<string,string> = {text:'文字内容', typography:'字体外观', color:'颜色', graphics:'图案与符号', completeness:'数量与完整性', orientation:'方向与顺序', shape:'形状与边框', layout:'布局与比例', codes:'二维码与条码', print:'可见印刷异常'};
const categories: Record<string,string> = {text:'文字',logo:'标志',symbol:'符号',diagram:'图案',code:'条码',color_block:'色块',outline:'轮廓',engineering:'工程要求'};
function Geometry({region, text, selected, onSelect}: {region: Region; text: string; selected: boolean; onSelect:()=>void}) {
  const [x,y,w,h] = region.box;
  return <g role="button" tabIndex={0} aria-label={`定位 ${text}`} className={selected?'selected':''} onClick={onSelect} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect();}}}>
    {region.polygon ? <polygon points={region.polygon.map(p=>`${p[0]*1000},${p[1]*1000}`).join(' ')}/> : <rect x={x*1000} y={y*1000} width={w*1000} height={h*1000}/>}
    <text x={Math.min(x*1000+3,930)} y={Math.max(20,y*1000+20)}>{text}</text>
  </g>;
}
function Crops({task, ids}: {task:Task; ids:string[]}) {
  return <div className="cc-crops">{ids.map(id=>{const a=task.artifacts?.find(x=>x.id===id);return a?<a key={id} href={mediaURL(task.id,a.image)} target="_blank" rel="noreferrer"><img src={mediaURL(task.id,a.preview)} alt={`${a.source==='reference'?'标准':'实拍'}局部证据`}/></a>:null;})}</div>;
}
export function LabelReport({task}: {task:Task}) {
  const [selected,setSelected]=useState(''), [problemsOnly,setProblemsOnly]=useState(false), [dimension,setDimension]=useState('');
  const elements=task.elements||[], checks=task.checks||[], issues=task.issues||[];
  const active=issues.filter(x=>!x.resolved), selectedIssue=issues.find(x=>x.id===selected);
  const selectedCheck=checks.find(x=>x.id===(selectedIssue?.check_id||selected)), linked=selectedCheck?.element_ids||[selected];
  const visibleChecks=checks.filter(c=>(!dimension||c.dimension===dimension)&&(!problemsOnly||['difference','uncertain'].includes(c.status)));
  const visibleElements=elements.filter(e=>!problemsOnly||visibleChecks.some(c=>c.element_ids.includes(e.id)));
  return <section className="cc-label-report"><h3>元素与检查清单</h3>
    <p role="status">已记录 {elements.length} 个元素 · 已处理 {task.progress?.settled||0}/{task.progress?.total||0} 项 · 待确认 {task.counts.uncertain} 项</p>
    <p className="cc-muted">已处理包含待确认和不适用，不代表全部通过。灰色项目尚未检查。</p>
    <div className="cc-filters"><label><input type="checkbox" checked={problemsOnly} onChange={e=>setProblemsOnly(e.target.checked)}/>仅显示问题与待确认</label><select aria-label="检查维度" value={dimension} onChange={e=>setDimension(e.target.value)}><option value="">全部维度</option>{Object.entries(dimensions).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select><button onClick={()=>setSelected('')}>显示全部元素</button></div>
    <div className="cc-pair">{(['reference','actual'] as const).map(side=><figure key={side}><div className="cc-image"><img src={mediaURL(task.id,task.inputs[side].preview)} alt={side==='reference'?'标准标签元素':'实拍标签元素'}/>
      <svg className="cc-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label={side==='reference'?'标准元素标注':'实拍元素标注'}>
        {side==='reference'&&task.inputs.reference_region&&<g className="cc-roi"><Geometry region={{box:task.inputs.reference_region}} text="标签范围" selected={false} onSelect={()=>setSelected('')}/></g>}
        {visibleElements.map(e=>e[side]&&<Geometry key={e.id} region={e[side]!} text={e.id} selected={linked.includes(e.id)} onSelect={()=>setSelected(e.id)}/>)}
        {active.filter(i=>!dimension||checks.find(c=>c.id===i.check_id)?.dimension===dimension).map(i=>i[side]&&<g key={i.id} className="cc-issue-mark"><Geometry region={i[side]!} text={i.id} selected={selected===i.id||selected===i.check_id} onSelect={()=>setSelected(i.id)}/></g>)}
      </svg></div><figcaption>{side==='reference'?'标准':'实拍'} · <a href={mediaURL(task.id,task.inputs[side].image)} target="_blank" rel="noreferrer">放大原图</a></figcaption></figure>)}</div>
    {!elements.length&&<p>等待 Codex 发布元素拆解…</p>}
    <div className="cc-elements">{visibleElements.map(e=><button key={e.id} aria-pressed={linked.includes(e.id)} onClick={()=>setSelected(e.id)}><strong>{e.id} · {e.name}</strong><span>{categories[e.category]||e.category} · {e.description}</span>{(!e.reference||!e.actual)&&<small>部分位置缺失或无法可靠定位</small>}</button>)}</div>
    <div className="cc-items">{visibleChecks.filter(c=>!selected||!elements.some(e=>e.id===selected)||c.element_ids.includes(selected)).map(c=><article key={c.id} className={`cc-item ${c.status} ${selectedCheck?.id===c.id?'selected':''}`}>
      <button aria-pressed={selectedCheck?.id===c.id} onClick={()=>setSelected(c.id)}>{labels[c.status]||c.status} · {dimensions[c.dimension]} · {c.element_ids.join('、')||'标签整体'}</button>
      <p>预期：{c.expected}</p><p>观察：{c.observed||'尚未检查'}</p><p>{c.explanation}</p><Crops task={task} ids={c.artifact_ids}/>
      {issues.filter(i=>i.check_id===c.id).map(i=><div className={`cc-issue ${i.resolved?'resolved':''}`} key={i.id}><button onClick={()=>setSelected(i.id)} aria-pressed={selected===i.id}>{i.id} · {i.title}{i.resolved?'（已修正）':''}</button><p>{i.explanation}</p>{(!i.reference||!i.actual)&&<small>仅标注可靠位置，另一侧请按说明复核</small>}<Crops task={task} ids={i.artifact_ids}/></div>)}
    </article>)}</div><details><summary>报告版本</summary><p>{task.report_version} · {task.skill_version||'等待加载检查 skill'}</p><p>Skill SHA256：{task.skill_sha256||'尚未加载'}</p></details>
  </section>;
}
export function ReferenceRegion({url,value,onChange,disabled}: {url:string;value:Box;onChange:(b:Box)=>void;disabled:boolean}) {
  const start=useRef<[number,number]|null>(null), [drag,setDrag]=useState<Box|null>(null); const b=drag||value;
  const point=(e:PointerEvent<HTMLDivElement>):[number,number]=>{const r=e.currentTarget.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];};
  const rectangle=(a:[number,number],z:[number,number]):Box=>[Math.min(a[0],z[0]),Math.min(a[1],z[1]),Math.abs(a[0]-z[0]),Math.abs(a[1]-z[1])];
  return <section className="cc-region"><h3>选定一枚标签</h3><p>单枚标签可使用整图；多枚标签请拖动框选其中一枚。包装展开图不支持。</p>
    <div className="cc-image cc-region-image" onPointerDown={e=>{if(disabled)return;start.current=point(e);e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(start.current)setDrag(rectangle(start.current,point(e)));}} onPointerUp={e=>{if(!start.current)return;const next=rectangle(start.current,point(e));start.current=null;setDrag(null);if(next[2]>.01&&next[3]>.01)onChange(next);}} onPointerCancel={()=>{start.current=null;setDrag(null);}}>
      <img src={url} alt="框选标准中的单枚标签" draggable={false}/><span className="cc-box" style={{left:`${b[0]*100}%`,top:`${b[1]*100}%`,width:`${b[2]*100}%`,height:`${b[3]*100}%`}}/>
    </div><button disabled={disabled} onClick={()=>onChange([0,0,1,1])}>使用整张单枚标签图</button>
    <div className="cc-region-fields">{['左边界','上边界','右边界','下边界'].map((label,i)=><label key={label}>{label} %<input type="number" min={0} max={100} step={.1} disabled={disabled} value={Math.round((i<2?value[i]:value[i-2]+value[i])*1000)/10} onChange={e=>{const v=Number(e.target.value)/100;const edges=[value[0],value[1],value[0]+value[2],value[1]+value[3]];edges[i]=v;if(edges.every(x=>x>=0&&x<=1)&&edges[2]>edges[0]&&edges[3]>edges[1])onChange([edges[0],edges[1],edges[2]-edges[0],edges[3]-edges[1]]);}}/></label>)}</div>
  </section>;
}
