import { Link } from "react-router-dom";
import { workspacePath } from "../../app/paths";
import "./vantaline-public.css";
import "./navigation-pages.css";

export function DocumentationPage() {
  return <div className="vl-source-page">
    <header className="docs-header">
      <Link className="brand" to="/">VantaLine</Link>
      <nav aria-label="文档导航"><Link to="/">产品介绍</Link><Link className="button button-primary" to={workspacePath()}>进入工作台</Link></nav>
    </header>
    <main className="docs-layout">
      <aside className="docs-toc" aria-label="文档目录">
        <span>使用文档</span>
        <a href="#start">开始使用</a><a href="#labels">标签与文字检验</a>
        <a href="#inspection">配件检测</a><a href="#evidence">结果与证据</a><a href="#help">常见问题</a>
      </aside>
      <article className="docs-content">
        <header><p className="eyebrow">VANTALINE / DOCUMENTATION</p><h1>从第一张图片开始</h1><p>了解工作台的基本流程。功能入口由你的账户权限和管理员配置决定。</p></header>
        <section id="start"><h2>开始使用</h2><ol>
          <li>打开<Link to={workspacePath()}>工作台</Link>，使用管理员分配的账号登录。可以直接收藏工作台或任务链接，无需经过产品介绍页。</li>
          <li>从左侧选择“文字检验”或“检测中心”。常用任务可以在任务库中固定到侧栏。</li>
          <li>需要帮助时，通过“关于与帮助”打开本文档；官网和文档在新标签页打开，不替换正在操作的页面。</li>
        </ol></section>
        <section id="labels"><h2>标签与文字检验</h2><ol>
          <li>进入<Link to={workspacePath("/text-compare-beta")}>文字检验</Link>，选择订单及标准。导入文档后检查提取出来的内容，确认保留或排除的图片，再启用标准。</li>
          <li>选中一个已启用的标准标签。右侧可以点击或拖拽上传实物照片，也可以选择摄像头拍照。</li>
          <li>账户启用提取功能后，根据当前方法框选或定位标签；放大检查目标、边缘、文字和图标，必要时手动修正，再明确确认。</li>
          <li>提交对比并检查差异。提取成功不代表文字完整或质量合格；反光、模糊和遮挡时应重新拍摄。</li>
        </ol><p className="docs-note">标准图像、实物图像与历史证据各自独立。人工确认与复核不能用模型的“成功”状态代替。</p></section>
        <section id="inspection"><h2>配件检测</h2><p>在<Link to={workspacePath("/inspect")}>检测中心</Link>选择已配置的任务和模型，再使用图片、视频或专用摄像头流程进行检测。模型和任务准备入口位于“训练与资产”。</p>
          <p>摄像头与本地串口需要浏览器授权。PLC 只能由授权的工作站页面连接并执行；普通图片上传、视频分析以及查看文档不会触发 PLC 写入。</p>
          <p className="docs-note">串口超时、断连或写入结果不明时，不要自动重复发送。先停止操作并由现场负责人确认设备状态。</p>
        </section>
        <section id="evidence"><h2>结果与证据</h2><p>在结果页和数据分析中查看检测记录。标签对比的 Raw Output 默认折叠，可展开核对模型输出和提取诊断；记录和媒体仍受账户权限限制。</p><p>反馈问题时附上记录编号、发生时间、页面显示的错误和“关于与帮助”里的版本号。不要发送 API Key、密码或未经授权的客户图片。</p></section>
        <section id="help"><h2>常见问题</h2>
          <details><summary>提示没有配置 Key，怎么办？</summary><p>请联系管理员检查对应步骤的模型配置。图像提取和文字对比可能使用不同的服务；不要把 Key 填入图片、备注或反馈内容。</p></details>
          <details><summary>为什么看不到某个功能或任务？</summary><p>先确认当前账号、权限与数据范围。访问受限不等于数据被删除，请联系工作区管理员核对。</p></details>
          <details><summary>登录失效或请求失败，是否会自动重复检测？</summary><p>登录失效后重新登录可返回原页面，但不会自动重放检测、模型请求或设备写入。网络错误先查看现有任务和记录，避免重复提交。</p></details>
          <details><summary>如何反馈问题？</summary><p>联系为你开通账号的工作区管理员，提供上述记录编号、版本与错误信息。先脱敏，再分享日志。</p></details>
        </section>
      </article>
    </main>
  </div>;
}
