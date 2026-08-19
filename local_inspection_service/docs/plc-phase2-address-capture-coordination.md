# PLC Phase 2：中文地址、到位拍照与多实例协调

## 已实现的软件闭环

本阶段把固定的 `D206/Y04` 升级为 PLC 编程人员可直接填写的逻辑设备名：

`PLC 输入寄存器到位沿 → 独占浏览器工作站拍照 → 最终检测 → 输出寄存器 → 可选 Y 控制点`

- 主表单使用中文，输出寄存器默认 `D206`，输出控制点默认 `Y04` 且可清空，输入寄存器默认留空。
- 用户不能提交 `119C/0108` 等协议地址。服务端唯一转换器按 D 十进制、Y 八进制换算，并把结果作为只读诊断信息返回。
- `output_control_point=""` 是唯一的“不控制 Y”语义；v2 计划、frame、attempt、重试和审计均不生成 Y 指令。
- v2 dispatch 绑定逻辑地址、派生地址、配置 generation 和真实 frame。v1 历史记录继续由冻结的 v1 verifier 验证。
- 旧配置只能以完整 v1 字段族迁移；新旧地址字段混用、无法反算或不规范的旧地址会被拒绝并保持无效/关闭。

## 到位触发与浏览器会话

- 输入监听每 200ms 尝试一次，读取和结果写入共享同一串口仲裁器，写入优先；轮询抢不到锁会跳过本轮。
- 启动、配置 generation 变化或 owner epoch 变化后都不武装。先看到非触发值，再看到精确触发值时才创建一个持久 `trigger_id`。
- 触发值持续不变不会重复；再次读到其他值后重新武装；服务端不清零 PLC 输入寄存器。
- 触发事件只分配给一个带心跳的浏览器会话，并绑定用户、模型、配置 generation。无有效会话时记为 `missed`，事件超过 1 秒不会再用于拍摄后续工件。
- 图片接口在解码、落盘和推理前验证 `trigger_id + session_id + model + 图片指纹`。同一触发的同一图片重试返回原结果；不同图片返回冲突，不重复检测或 PLC dispatch。

## PostgreSQL 多实例边界

- `plc_runtime_coordination` 已定义 I/O owner、heartbeat、epoch、接管隔离窗口、触发状态、工作站租约和 capture event 的代码路径。
- 非 owner worker 的结果可以先持久化为 `queued`；代码只允许 v2、同 generation、完整配置快照相同、2 秒 deadline 内且从未产生 operation 的记录进入安全接管候选。v1、过期、旧配置和任何已开始记录均为 0 I/O。
- 但现有 repository 只有通用 namespace CAS，尚未提供“PostgreSQL 服务器时间 + owner epoch 校验 + attempt 声明”同事务原语。因此 `plc_pg_coordination_available()` 刻意要求一个尚未实现的专用 fenced-attempt 方法，生产能力门保持关闭。
- 也就是说，本阶段保留并测试协调状态机，但不宣称已经完成真正的跨主机 physical-I/O fencing。缺少该原语时读取和写入均保持 fail-closed，串口打开次数为 0。

## 仍未授权生产启用

仓库中没有真实 PLC 型号和读协议的权威证据。因此 D 寄存器读帧实现仅用于 fake transport 和现场 golden-frame 验证，生产必须同时满足：

1. `VANTALINE_PLC_DEVICE_PROFILE_FINGERPRINT` 与已签字的型号、地址范围、线缆、串口、地址和写协议配置完全匹配；
2. 使用输入触发时，`VANTALINE_PLC_READ_PROFILE_FINGERPRINT` 与真实读帧、输入地址、触发值、响应长度、字节序和 checksum 配置完全匹配；
3. PostgreSQL runtime 实现并通过 DB-clock fenced-attempt 原语、uncertain barrier 和真实多进程故障测试；
4. 部署包已锁定安装 `pyserial`；
5. 现场确认输出寄存器、可选 Y 点和输入寄存器均未被 PLC 程序占用。

缺少任意一项时 `effective_enabled=false`。本阶段没有连接、扫描、读取或写入真实 PLC，也没有修改生产配置。

## 专项验证

- `smoke_plc_phase1.py`：原有写协议、配置 API、最终检测触发与 no-I/O 语义。
- `smoke_plc_phase2.py`：D/Y 地址转换、旧配置迁移、字段冲突、Y 空值、独立读响应、触发沿、会话和上传幂等。
- `smoke_plc_phase1_hardening.py`：typed reducer/CAS、故障矩阵、queued 安全接管、已开始记录不重放、PG 非 owner 排队与 fenced adoption。
- `smoke_plc_frontend_contract.py`：中文字段、只读派生地址、自动拍照会话和状态文案。
- 前端 TypeScript typecheck 与 production Vite build。
