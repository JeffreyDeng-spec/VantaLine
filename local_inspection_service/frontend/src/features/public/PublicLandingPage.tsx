import { Link } from "react-router-dom";
import "./vantaline-public.css";

const workflowSteps = [
  ["01", "Define parts", "Set the part context and inspection rules."],
  ["02", "Run inspection", "Detect objects and evaluate the frame."],
  ["03", "Review evidence", "Confirm results with annotated context."],
  ["04", "Grow dataset", "Keep useful accepted and rejected samples."],
  ["05", "Train remotely", "Launch a YOLO run on remote GPU capacity."],
  ["06", "Deploy & monitor", "Activate a model and follow its results."]
];

const attributes = [
  "Human-in-the-loop review",
  "Role-aware access",
  "Remote GPU training",
  "Auditable results"
];

function Brand() {
  return (
    <Link className="brand" to="/" aria-label="VantaLine home">
      <span className="brand-mark" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span>VantaLine</span>
    </Link>
  );
}

export function PublicLandingPage() {
  return (
    <div className="vl-source-page">
      <main>
        <header className="site-header">
          <div className="container nav-inner">
            <Brand />
            <nav className="desktop-nav" aria-label="Primary navigation">
              <a href="#inspect">Product</a>
              <a href="#workflow">Workflow</a>
              <a href="#capabilities">Capabilities</a>
              <a href="#reliability">Reliability</a>
            </nav>
            <div className="nav-actions">
              <Link className="login-link" to="/login">
                Log in
              </Link>
              <Link className="button nav-button" to="/login">
                Open workspace
              </Link>
            </div>
            <details className="mobile-menu">
              <summary aria-label="Open navigation">
                <span />
                <span />
              </summary>
              <nav aria-label="Mobile navigation">
                <a href="#inspect">Product</a>
                <a href="#workflow">Workflow</a>
                <a href="#capabilities">Capabilities</a>
                <a href="#reliability">Reliability</a>
                <Link to="/login">Log in</Link>
                <Link className="button button-primary" to="/login">
                  Open workspace
                </Link>
              </nav>
            </details>
          </div>
        </header>

        <section className="hero" aria-labelledby="hero-title">
          <div className="container hero-grid">
            <div className="hero-copy reveal">
              <p className="eyebrow">AI VISUAL INSPECTION FOR MANUFACTURING</p>
              <h1 id="hero-title">Turn every inspection into a better production model.</h1>
              <p className="hero-lede">
                VantaLine connects detection, human review, dataset growth, remote training, deployment, and
                evidence—so quality work improves with every run.
              </p>
              <div className="hero-actions">
                <Link className="button button-primary" to="/login">
                  Open workspace <span aria-hidden="true">↗</span>
                </Link>
                <a className="button button-secondary" href="#workflow">
                  See how it works <span aria-hidden="true">↓</span>
                </a>
              </div>
            </div>

            <div className="hero-visual reveal reveal-delay" aria-label="VantaLine inspection workspace preview">
              <div className="product-frame">
                <div className="product-topbar">
                  <div className="window-dots">
                    <i />
                    <i />
                    <i />
                  </div>
                  <p>Inspection / Task VL-2841</p>
                  <span className="live-chip">
                    <i /> Live
                  </span>
                </div>
                <div className="product-body">
                  <div className="camera-view">
                    <div className="camera-meta">
                      <span>CAM 04 · LINE B</span>
                      <span>14:32:08.491</span>
                    </div>
                    <div className="machine-surface">
                      <i />
                      <i />
                      <i />
                      <i />
                    </div>
                    <div className="part part-one">
                      <span>BRACKET_A · 98.4%</span>
                      <i />
                      <i />
                      <i />
                    </div>
                    <div className="part part-two">
                      <span>FASTENER · 94.7%</span>
                      <i />
                    </div>
                    <div className="scan-line" />
                    <div className="frame-result">
                      <span>PASS</span>
                      <p>3 / 3 checks confirmed</p>
                    </div>
                  </div>
                  <aside className="task-sidebar">
                    <div className="sidebar-heading">
                      <span>TASK PIPELINE</span>
                      <small>6 stages</small>
                    </div>
                    <div className="pipeline-list">
                      <div className="pipeline-step done">
                        <i>✓</i>
                        <p>
                          Capture received<small>14:32:08</small>
                        </p>
                      </div>
                      <div className="pipeline-step done">
                        <i>✓</i>
                        <p>
                          Objects detected<small>Model v2.8</small>
                        </p>
                      </div>
                      <div className="pipeline-step active">
                        <i>3</i>
                        <p>
                          Rule evaluation<small>In progress</small>
                        </p>
                      </div>
                      <div className="pipeline-step">
                        <i>4</i>
                        <p>
                          Human review<small>Queued</small>
                        </p>
                      </div>
                    </div>
                    <div className="model-mini">
                      <span>ACTIVE MODEL</span>
                      <strong>Bracket / v2.8</strong>
                      <div>
                        <i />
                      </div>
                      <small>Deployed 18 Jun</small>
                    </div>
                  </aside>
                </div>
                <div className="product-footer">
                  <span>
                    <i /> Camera connected
                  </span>
                  <span>27 ms inference</span>
                  <span>Reviewer: M. Chen</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="credibility" aria-label="Product attributes">
          <div className="container attribute-row">
            {attributes.map((attribute, index) => (
              <div className="attribute" key={attribute}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <p>{attribute}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="workflow-section section" id="workflow" aria-labelledby="workflow-title">
          <div className="container">
            <div className="section-heading">
              <p className="eyebrow">ONE CONTINUOUS SYSTEM</p>
              <h2 id="workflow-title">From production evidence to a stronger deployed model.</h2>
              <p>Each decision advances the same improvement loop. No disconnected tools, exports, or missing context.</p>
            </div>
            <div className="workflow-track">
              {workflowSteps.map(([number, title, description], index) => (
                <article className="workflow-step" key={title}>
                  <div className="step-top">
                    <span>{number}</span>
                    {index < workflowSteps.length - 1 ? <i aria-hidden="true" /> : null}
                  </div>
                  <h3>{title}</h3>
                  <p>{description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="capabilities section" id="capabilities" aria-label="VantaLine capabilities">
          <div className="container">
            <article className="capability" id="inspect">
              <div className="capability-copy">
                <p className="eyebrow">01 / INSPECTION</p>
                <h2>Inspect with context</h2>
                <p>
                  Move from a camera frame to a reviewable result without losing the production context around it.
                  VantaLine combines AI detections, rule evaluation, annotated evidence, and human review in one task.
                </p>
                <ul>
                  <li>Detection confidence stays visible</li>
                  <li>Reviewers can accept or reject evidence</li>
                  <li>Part rules travel with each inspection</li>
                </ul>
              </div>
              <div className="scene scene-inspect" aria-label="Annotated inspection evidence interface">
                <div className="scene-bar">
                  <span>REVIEW QUEUE / 018</span>
                  <span className="chip-blue">Needs review</span>
                </div>
                <div className="evidence-image">
                  <div className="evidence-part">
                    <span>SURFACE MARK · 87.2%</span>
                  </div>
                  <div className="crosshair">+</div>
                </div>
                <div className="decision-row">
                  <div>
                    <small>RULE RESULT</small>
                    <strong>Surface anomaly detected</strong>
                  </div>
                  <div className="decision-actions">
                    <button type="button" aria-label="Reject evidence">
                      Reject
                    </button>
                    <button type="button">Accept evidence</button>
                  </div>
                </div>
              </div>
            </article>

            <article className="capability capability-reverse" id="improve">
              <div className="capability-copy">
                <p className="eyebrow">02 / IMPROVEMENT</p>
                <h2>Improve from real production data</h2>
                <p>
                  Turn reviewed samples into a stronger dataset. Track readiness, launch remote YOLO training on RunPod,
                  and manage each model from training run to active deployment.
                </p>
                <ul>
                  <li>Accepted and rejected samples stay organized</li>
                  <li>Training progress is visible in the workspace</li>
                  <li>Model versions move through a clear lifecycle</li>
                </ul>
              </div>
              <div className="scene scene-training" aria-label="Remote model training progress interface">
                <div className="scene-bar">
                  <span>TRAINING RUN / YOLO-184</span>
                  <span className="chip-green">
                    <i /> Running
                  </span>
                </div>
                <div className="training-summary">
                  <div>
                    <small>MODEL</small>
                    <strong>Bracket defect v2.9</strong>
                  </div>
                  <div>
                    <small>DATASET</small>
                    <strong>1,842 images</strong>
                  </div>
                  <div>
                    <small>REMOTE GPU</small>
                    <strong>RunPod</strong>
                  </div>
                </div>
                <div className="progress-wrap">
                  <div className="progress-label">
                    <span>Epoch 72 / 100</span>
                    <span>72%</span>
                  </div>
                  <div className="progress-bar">
                    <i />
                  </div>
                </div>
                <div className="training-chart">
                  <div className="chart-grid" />
                  <div className="chart-line">
                    <i />
                    <i />
                    <i />
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
                <div className="training-footer">
                  <span>
                    <i className="legend-blue" /> Validation loss
                  </span>
                  <span>ETA 00:18:42</span>
                </div>
              </div>
            </article>

            <article className="capability" id="operate">
              <div className="capability-copy">
                <p className="eyebrow">03 / OPERATIONS</p>
                <h2>Operate with traceability</h2>
                <p>
                  Give every inspection an owner, every decision its evidence, and every model a history. Analytics,
                  permissions, and an audit trail keep improvement work understandable across the team.
                </p>
                <ul>
                  <li>Role-aware access for shared work</li>
                  <li>Task and result history in one record</li>
                  <li>Reproducible evidence for review</li>
                </ul>
              </div>
              <div className="scene scene-ops" aria-label="Operations analytics and task ownership interface">
                <div className="scene-bar">
                  <span>LINE PERFORMANCE / 7 DAYS</span>
                  <span>Export ready</span>
                </div>
                <div className="ops-metrics">
                  <div>
                    <small>INSPECTIONS</small>
                    <strong>8,204</strong>
                    <span>All assigned lines</span>
                  </div>
                  <div>
                    <small>REVIEW QUEUE</small>
                    <strong>124</strong>
                    <span>18 assigned to you</span>
                  </div>
                </div>
                <div className="ops-chart">
                  <div className="bars">
                    {[42, 66, 51, 82, 61, 74, 88, 72, 91, 83, 94, 78].map((height, index) => (
                      <i style={{ height: `${height}%` }} key={`${height}-${index}`} />
                    ))}
                  </div>
                </div>
                <div className="owner-row">
                  <span className="avatar">MC</span>
                  <p>
                    <strong>M. Chen reviewed task VL-2841</strong>
                    <small>Evidence accepted · Model v2.8 · 2 min ago</small>
                  </p>
                  <span>→</span>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section className="reliability section" id="reliability" aria-labelledby="reliability-title">
          <div className="container reliability-grid">
            <div className="reliability-copy">
              <p className="eyebrow">RELIABILITY BY DESIGN</p>
              <h2 id="reliability-title">Decisions remain reviewable. Evidence remains attached.</h2>
              <p>
                VantaLine assists inspection teams without hiding the path to a result. Confidence, annotations,
                reviewer actions, model version, and task history remain available for follow-up.
              </p>
              <div className="reliability-stat">
                <span className="status-dot" aria-hidden="true" />
                <div>
                  <strong>Evidence-backed workflow</strong>
                  <small>AI assistance with accountable human review</small>
                </div>
              </div>
            </div>
            <div className="audit-panel">
              <div className="audit-header">
                <div>
                  <small>EVIDENCE RECORD</small>
                  <strong>VL-2841 / Frame 0182</strong>
                </div>
                <span>Complete</span>
              </div>
              <ol>
                <li>
                  <time>14:32:08</time>
                  <i />
                  <p>
                    <strong>Inspection created</strong>
                    <small>Frame 0182 · Line B</small>
                  </p>
                </li>
                <li>
                  <time>14:32:09</time>
                  <i />
                  <p>
                    <strong>AI inference completed</strong>
                    <small>Model bracket_v2.8</small>
                  </p>
                </li>
                <li>
                  <time>14:34:21</time>
                  <i />
                  <p>
                    <strong>Evidence reviewed</strong>
                    <small>Accepted by M. Chen</small>
                  </p>
                </li>
                <li>
                  <time>14:34:22</time>
                  <i className="current" />
                  <p>
                    <strong>Result recorded</strong>
                    <small>PASS · Task VL-2841</small>
                  </p>
                </li>
              </ol>
              <div className="audit-footer">
                <span>4 linked events</span>
                <a href="#workflow">View workflow →</a>
              </div>
            </div>
          </div>
        </section>

        <section className="final-cta">
          <div className="container final-cta-inner">
            <p className="eyebrow">START WITH THE LINE YOU RUN TODAY</p>
            <h2>Build an inspection system that improves with the line.</h2>
            <Link className="button button-light" to="/login">
              Log in to VantaLine <span aria-hidden="true">↗</span>
            </Link>
          </div>
        </section>

        <footer className="site-footer">
          <div className="container footer-inner">
            <Brand />
            <nav aria-label="Footer navigation">
              <a href="#inspect">Product</a>
              <a href="#workflow">Workflow</a>
              <Link to="/login">Login</Link>
            </nav>
            <p>© 2026 VantaLine</p>
          </div>
        </footer>
      </main>
    </div>
  );
}
