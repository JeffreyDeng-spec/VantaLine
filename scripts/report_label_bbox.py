"""Render existing benchmark evidence only; never calls a model."""
import argparse
import html
import json
import statistics
from pathlib import Path
from PIL import Image,ImageDraw


def main():
    ap=argparse.ArgumentParser();ap.add_argument('directory');args=ap.parse_args()
    root=Path(args.directory).resolve();parent=root.parent
    read=lambda path:json.loads(path.read_text())
    settings=read(root/'settings.json');latencies=[];usage={'prompt_tokens':0,'completion_tokens':0,'total_tokens':0}
    cards=[];md=['## 同事矩形定位 · 千问移植首轮','','严格自动验收 **0/9**。9 次输出均复制提示词示例：labelCount=6，cropRect=(0.1,0.1,0.2,0.15)。这不是有效定位，不启用生产。未进行人工修正或追加付费请求。','']
    contact=Image.new('RGB',(1200,1050),'#eceff3');draw=ImageDraw.Draw(contact)
    for n in range(1,10):
        d=root/str(n);response=read(d/'response.json');review=read(d/'review.json');geo=read(d/'geometry.json');meta=read(d/'input.json')
        assert review['status']=='failed' and geo['original_pixels_equal']
        latencies.append(response['elapsed_ms'])
        for k in usage:usage[k]+=response['response'].get('usage',{}).get(k,0)
        crop=Image.open(d/'crop.png').convert('RGB');crop.thumbnail((380,290))
        x=((n-1)%3)*400;y=((n-1)//3)*350;contact.paste(crop,(x+10+(380-crop.width)//2,y+42+(290-crop.height)//2));draw.text((x+12,y+12),f'{n}.jpg | FAIL | {response["elapsed_ms"]} ms',fill='#9b1515')
        note=review['notes'];cards.append(f'<section><h2>{n}.jpg — FAIL</h2><p>{html.escape(note)}</p><div class="gallery">')
        md.extend([f'### {n}.jpg — 失败','',note,'',f'原图 {meta["source_size"]}；模型输入 {meta["input_size"]}；调用 {response["elapsed_ms"]} ms；原始像素核验通过。',''])
        for label,path in [('原图预览',parent/'report-assets'/f'{n}.jpg'),('实际模型输入',d/'model-input.jpg'),('原图定位框',d/'overlay.jpg'),('边缘放大',d/'overlay-detail.png'),('未经修正的裁剪',d/'crop.png')]:
            rel='../'+str(path.relative_to(parent));cards.append(f'<figure><a href="{rel}"><img loading="lazy" src="{rel}" alt="{label}"></a><figcaption>{label} · 点击放大</figcaption></figure>')
            md.extend([f'![{label}]({path})',''])
        cards.append('</div>')
        for name in ['input.json','prompt.txt','response.json','geometry.json','review.json']:
            cards.append(f'<details><summary>{name}</summary><pre>{html.escape((d/name).read_text())}</pre></details>');md.append(f'[{name}]({d/name})')
        cards.append('</section>');md.append('')
    contact.save(root/'contact.jpg',quality=94)
    summary={'model':settings['model'],'requests':9,'responses':9,'timeouts':0,'strict_automatic_passes':0,'pixel_provenance_passes':9,'median_latency_ms':statistics.median(latencies),'min_latency_ms':min(latencies),'max_latency_ms':max(latencies),'usage':usage,'actual_currency_charge':None,'production_enabled':False,'baseline':'Original colleague prompt on resolved Qwen model; not Doubao reproduction','finding':'All nine outputs equal the numeric JSON example; mechanism not proven'}
    (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    intro=f'<h1>同事矩形定位移植 · 0/9</h1><p>实际模型 {html.escape(settings["model"])}；九次响应均照搬示例坐标，未通过单标签验收。没有额外重试，没有改生产配置。</p><p>这是原提示词在千问上的移植结果，不代表豆包原版表现。模型输出与示例相同的原因尚未隔离验证。与之前人工挑选的较佳候选相比，本轮九图均不改善，不能替换现有路径。</p><p>原图像素保真 9/9，但保真不等于选对目标。9.jpg 还存在白底物理边界不清的独立限制。中位调用耗时 {summary["median_latency_ms"]} ms；输入 {usage["prompt_tokens"]} / 输出 {usage["completion_tokens"]} tokens；实际账单金额未知。</p><p><a href="summary.json">用量与结论</a> · <a href="../index.html">历轮日志</a></p><a href="contact.jpg"><img style="height:auto;width:100%" src="contact.jpg" alt="九图裁切失败总览"></a>'
    style='<style>body{font:16px system-ui;background:#101621;color:#e5eaf1;max-width:1400px;margin:30px auto;padding:20px}a{color:#85bcff}section{background:#192332;padding:20px;margin:20px 0;border-radius:12px}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}figure{margin:0}img{max-width:100%;height:230px;object-fit:contain}pre{white-space:pre-wrap;overflow-wrap:anywhere}details{margin-top:12px}h2{color:#ffb5a8}</style>'
    (root/'index.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>同事定位模块九图试验</title>'+style+intro+''.join(cards)+'</html>')
    (root/'TEST-LOG.md').write_text('\n'.join(md))
    # Append only; preserve every existing historical section/artifact.
    oldmd=parent/'TEST-LOG.md';marker='<!-- colleague-layout-qwen-v1 -->'
    if marker not in oldmd.read_text():
        with oldmd.open('a') as f:f.write('\n'+marker+'\n'+'\n'.join(md))
    index=parent/'index.html'
    if marker not in index.read_text():
        with index.open('a') as f:f.write(marker+f'<section><h2>新增：同事定位模块九图试验</h2><p>千问移植首轮 0/9，生产关闭。<a href="{root.name}/index.html">逐图图片、输入输出和结论</a></p><a href="{root.name}/index.html"><img src="{root.name}/contact.jpg" style="width:100%;height:auto" alt="九图结果"></a></section>')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
