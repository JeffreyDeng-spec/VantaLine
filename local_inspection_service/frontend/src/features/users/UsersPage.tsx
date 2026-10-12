import { FormEvent, useMemo, useState } from "react";
import { useAgentActions } from "../agent/useAgentActions";
import { Copy, KeyRound, Plus, Save, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createUser,
  deleteUser,
  getUsers,
  queryKeys,
  resetUserPassword,
  updateUser,
} from "../../api/queries";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { useToast } from "../../components/ToastProvider";
import type { AuthUser } from "../../api/types";
import { useAuth } from "../auth/auth-context";
import { AdminDialog, AdminConfirm, AdminConfirmation } from "./AdminDialog";
import { UserDataWorkbench } from "./UserDataWorkbench";
import { apiClient } from "../../api/client";
import "./users-workbench.css";
import { recordAuditText } from "../../utils/format";

function formPermissions(form: HTMLFormElement, fieldName: string) {
  return Array.from(
    form.querySelectorAll<HTMLInputElement>(
      `input[name="${fieldName}"]:checked`,
    ),
  ).map((input) => input.value);
}

function PermissionGrid({
  entries,
  selected,
  name,
  role = "user",
}: {
  entries: Array<[string, string]>;
  selected: string[];
  name: string;
  role?: string;
}) {
  const selectedSet = new Set(selected);
  return (
    <div className="permission-grid">
      {entries.map(([key, label]) => (
        <label className="permission-toggle" key={key}>
          <input
            name={name}
            type="checkbox"
            value={key}
            defaultChecked={
              role === "admin" ||
              (selectedSet.has(key) &&
                ![
                  "user_management",
                  "ai_config",
                  "agent_config",
                  "system_settings",
                ].includes(key))
            }
            disabled={
              role === "admin" ||
              [
                "user_management",
                "ai_config",
                "agent_config",
                "system_settings",
              ].includes(key)
            }
          />
          <span>
            {label}
            {["ai_config", "agent_config", "system_settings"].includes(key) && (
              <small> · 管理员专属</small>
            )}
          </span>
        </label>
      ))}
    </div>
  );
}

export function UsersPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [selected, setSelected] = useState("");
  const [tab, setTab] = useState("overview");
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  const [draftRoles, setDraftRoles] = useState<Record<string, string>>({});
  const [confirmation, setConfirmation] = useState<AdminConfirmation | null>(
    null,
  );
  const countsQuery = useQuery({
    queryKey: ["admin-user-counts"],
    queryFn: () =>
      apiClient.get<{
        counts: Record<string, { tasks: number; training: number }>;
      }>("/api/auth/users-data-summary"),
  });
  const [temporaryPasswords, setTemporaryPasswords] = useState<
    Record<string, string>
  >({});
  const [createDraft, setCreateDraft] = useState({
    username: "",
    display_name: "",
    role: "user",
    permissions: undefined as string[] | undefined,
  });
  const [secureRequest, setSecureRequest] = useState<{
    id: string;
    kind: "create" | "reset";
    target: string;
    status: "requires_user_input" | "completed" | "failed";
  } | null>(null);

  const usersQuery = useQuery({
    queryKey: queryKeys.users,
    queryFn: getUsers,
  });

  const featureEntries = useMemo(() => {
    const features = usersQuery.data?.features || auth.features || {};
    return Object.entries(features).filter(
      ([key]) => key !== "user_management",
    );
  }, [auth.features, usersQuery.data?.features]);

  const defaultUserPermissions =
    usersQuery.data?.default_user_permissions ||
    auth.defaultUserPermissions ||
    [];

  const refreshUsers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.users }),
      queryClient.invalidateQueries({ queryKey: queryKeys.authStatus }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-counts"] }),
      queryClient.invalidateQueries({ queryKey: ["admin-user-data"] }),
    ]);
  };

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: async (result) => {
      setSecureRequest((current) =>
        current?.kind === "create"
          ? {
              ...current,
              status: "completed",
              target: result.user?.id || current.target,
            }
          : current,
      );
      setCreateDraft({
        username: "",
        display_name: "",
        role: "user",
        permissions: undefined,
      });
      await refreshUsers();
      setShowCreate(false);
      notify({ title: "用户已创建", tone: "success" });
    },
    onError: (error: Error) =>
      notify({
        title: "创建用户失败",
        description: error.message,
        tone: "error",
      }),
  });

  const updateMutation = useMutation({
    mutationFn: ({
      userId,
      payload,
    }: {
      userId: string;
      payload: Parameters<typeof updateUser>[1];
    }) => updateUser(userId, payload),
    onSuccess: async () => {
      await refreshUsers();
      notify({ title: "用户已更新", tone: "success" });
    },
    onError: (error: Error) =>
      notify({
        title: "用户更新失败",
        description: error.message,
        tone: "error",
      }),
  });

  const passwordMutation = useMutation({
    mutationFn: ({
      userId,
      payload,
    }: {
      userId: string;
      payload: Parameters<typeof resetUserPassword>[1];
    }) => resetUserPassword(userId, payload),
    onSuccess: async (result, variables) => {
      setSecureRequest((current) =>
        current?.kind === "reset" && current.target === variables.userId
          ? { ...current, status: "completed" }
          : current,
      );
      if (result.temporary_password) {
        setTemporaryPasswords((current) => ({
          ...current,
          [variables.userId]: result.temporary_password || "",
        }));
      } else {
        setTemporaryPasswords((current) => ({
          ...current,
          [variables.userId]: "",
        }));
      }
      await refreshUsers();
      notify({
        title: result.temporary_password ? "临时密码已生成" : "密码已重置",
        description: result.revoked_sessions
          ? `已撤销 ${result.revoked_sessions} 个会话`
          : undefined,
        tone: "success",
      });
    },
    onError: (error: Error) =>
      notify({
        title: "密码更新失败",
        description: error.message,
        tone: "error",
      }),
  });

  const deleteMutation = useMutation({
    mutationFn: ({ userId, reason }: { userId: string; reason: string }) =>
      deleteUser(userId, reason),
    onSuccess: async (_result, { userId }) => {
      setTemporaryPasswords((current) => ({ ...current, [userId]: "" }));
      await refreshUsers();
      setSelected("");
      notify({ title: "用户已删除", tone: "success" });
    },
    onError: (error: Error) =>
      notify({ title: "删除失败", description: error.message, tone: "error" }),
  });

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const payload = {
      username: String(data.get("username") || "").trim(),
      display_name: String(data.get("display_name") || "").trim(),
      password: String(data.get("password") || ""),
      role: String(data.get("role") || "user"),
      permissions:
        createDraft.role === "admin"
          ? featureEntries.map(([key]) => key)
          : formPermissions(form, "new_permissions"),
    };
    setConfirmation({
      title: "确认创建用户",
      impact: `创建 ${payload.username}，角色为 ${payload.role === "admin" ? "Admin（全部管理权限）" : "普通用户"}。密码不进入操作记录。`,
      operation: async (reason) => {
        await createMutation.mutateAsync({ ...payload, reason });
        form.reset();
      },
    });
  }

  function handleUpdateUser(user: AuthUser) {
    return async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const form = event.currentTarget;
      const data = new FormData(form);
      const payload = {
        display_name: String(data.get("display_name") || "").trim(),
        role: String(data.get("role") || "user"),
        permissions:
          String(data.get("role")) === "admin"
            ? featureEntries.map(([key]) => key)
            : formPermissions(form, `permissions_${user.id}`),
      };
      setConfirmation({
        title: "确认账号与权限修改",
        impact: `账号 ${user.username}：名称 ${user.display_name || user.username} → ${payload.display_name}；角色 ${user.role} → ${payload.role}；授权 ${payload.permissions.length} 项功能。Admin 拥有全部功能。权限调整控制功能访问；后台任务需单独暂停，已发出的工作可以结算。`,
        operation: (reason) =>
          updateMutation.mutateAsync({
            userId: user.id,
            payload: { ...payload, reason },
          }),
      });
    };
  }

  async function handlePasswordReset(
    userId: string,
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = String(new FormData(form).get("password") || "");
    if (!password.trim()) {
      notify({
        title: "请输入新密码",
        description: "或使用生成临时密码。",
        tone: "error",
      });
      return;
    }
    setConfirmation({
      title: "设置新密码",
      impact:
        userId === auth.user.id
          ? "撤销其他会话，保留当前登录会话。密码不记录在审计中。"
          : "目标账号全部会话将撤销，密码不记录在审计中。",
      operation: async (reason) => {
        await passwordMutation.mutateAsync({
          userId,
          payload: { password, revoke_sessions: true, reason },
        });
        form.reset();
      },
    });
  }

  async function copyTemporaryPassword(userId: string) {
    const value = temporaryPasswords[userId] || "";
    if (!value) return;
    if (!navigator.clipboard?.writeText) {
      notify({ title: "浏览器不支持一键复制", tone: "error" });
      return;
    }
    await navigator.clipboard.writeText(value);
    notify({ title: "临时密码已复制", tone: "success" });
  }

  useAgentActions([
    {
      name: "users_prepare_create",
      domain: "users",
      permissions: ["user_management"],
      description:
        "Prepare the existing account creation form with non-secret fields. The user supplies the password in the site's secure form and submits it; no password enters tool arguments or results.",
      readOnly: false,
      inputSchema: {
        type: "object",
        properties: {
          username: { type: "string", minLength: 1, maxLength: 100 },
          display_name: { type: "string", maxLength: 200 },
          role: { type: "string", enum: ["user", "admin"] },
          permissions: {
            type: "array",
            items: { type: "string" },
            maxItems: 100,
          },
        },
        required: ["username", "role", "permissions"],
        additionalProperties: false,
      },
      available: () =>
        createMutation.isPending ||
        secureRequest?.status === "requires_user_input"
          ? "A secure account workflow is already pending"
          : null,
      execute: (input) => {
        setShowCreate(true);
        const id = crypto.randomUUID();
        setCreateDraft({
          username: String(input.username),
          display_name: String(input.display_name || ""),
          role: String(input.role),
          permissions: input.permissions as string[],
        });
        setSecureRequest({
          id,
          kind: "create",
          target: String(input.username),
          status: "requires_user_input",
        });
        return {
          status: "requires_user_input",
          operation_id: id,
          next_action: "users_secure_state",
        };
      },
    },
    {
      name: "users_prepare_password_reset",
      domain: "users",
      permissions: ["user_management"],
      description:
        "Request secure password entry for an existing user. The existing password form revokes sessions on successful reset; no secret is returned to the tool.",
      readOnly: false,
      inputSchema: {
        type: "object",
        properties: { user_id: { type: "string" } },
        required: ["user_id"],
        additionalProperties: false,
      },
      available: () =>
        passwordMutation.isPending ||
        secureRequest?.status === "requires_user_input"
          ? "A secure account workflow is already pending"
          : null,
      execute: (input) => {
        const target = String(input.user_id);
        if (!usersQuery.data?.users.some((user) => user.id === target))
          throw new Error("User is not in the current authorized account list");
        setSelected(target);
        setTab("account");
        const id = crypto.randomUUID();
        setSecureRequest({
          id,
          kind: "reset",
          target,
          status: "requires_user_input",
        });
        return {
          status: "requires_user_input",
          operation_id: id,
          next_action: "users_secure_state",
        };
      },
    },
    {
      name: "users_secure_state",
      domain: "users",
      permissions: ["user_management"],
      description:
        "Read secure-input workflow status and target identity, without reading any password or temporary secret.",
      readOnly: true,
      inputSchema: {
        type: "object",
        properties: {},
        additionalProperties: false,
      },
      execute: () => ({
        request: secureRequest,
        create_status: createMutation.status,
        reset_status: passwordMutation.status,
      }),
    },
  ]);

  if (usersQuery.isLoading) return <LoadingState label="正在加载用户" />;
  if (usersQuery.isError) return <ErrorState error={usersQuery.error} />;

  const users = usersQuery.data?.users || [];
  const target = users.find((u) => u.id === selected);
  const visible = users.filter(
    (u) =>
      `${u.username}${u.display_name || ""}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (!roleFilter || u.role === roleFilter) &&
      (!stateFilter || (u.active !== false) === (stateFilter === "active")),
  );
  const busy =
    createMutation.isPending ||
    updateMutation.isPending ||
    passwordMutation.isPending ||
    deleteMutation.isPending;

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>{target ? "用户管理工作台" : "用户管理"}</h2>
          <p className="page-desc">
            账号创建、角色权限与用户数据，在同一个管理空间完成。
          </p>
        </div>
        {!target && (
          <button
            className="primary"
            type="button"
            onClick={() => setShowCreate(true)}
          >
            ＋ 创建用户
          </button>
        )}
      </header>
      {target ? (
        <>
          <button
            className="admin-back"
            type="button"
            onClick={() => setSelected("")}
          >
            ← 返回用户管理
          </button>
          <section className="panel page-panel admin-context">
            <div>
              <strong>{target.display_name || target.username}</strong>
              <small>
                被管理账号：{target.username} · 操作人：{auth.user.username}
              </small>
            </div>
            <select
              aria-label="切换被管理账号"
              value={selected}
              onChange={(e) => {
                setSelected(e.target.value);
                setDraftRoles({});
              }}
            >
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.display_name || u.username}
                </option>
              ))}
            </select>
            <span className="pill neutral">
              {target.active === false ? "已停用" : "已启用"}
            </span>
          </section>
          <nav className="admin-tabs" aria-label="用户工作台">
            {[
              ["overview", "总览"],
              ["account", "账号与权限"],
              ["tasks", "任务与训练"],
              ["images", "图片资产"],
              ["assets", "数据集与模型"],
              ["audit", "操作记录"],
            ].map(([k, label]) => (
              <button
                key={k}
                type="button"
                aria-current={tab === k ? "page" : undefined}
                className={tab === k ? "active" : ""}
                onClick={() => setTab(k)}
              >
                {label}
              </button>
            ))}
          </nav>
          {target.active === false && (
            <p className="admin-impact">
              账号已停用；恢复账号后，任务与实拍回流仍需显式恢复。
            </p>
          )}
          {tab !== "account" && (
            <UserDataWorkbench key={target.id} owner={target.id} tab={tab} />
          )}
        </>
      ) : (
        <>
          <div className="admin-stats">
            <div className="panel">
              <span>全部账号</span>
              <strong>{users.length}</strong>
            </div>
            <div className="panel">
              <span>启用账号</span>
              <strong>{users.filter((u) => u.active !== false).length}</strong>
            </div>
            <div className="panel">
              <span>管理员</span>
              <strong>
                {
                  users.filter((u) => u.role === "admin" && u.active !== false)
                    .length
                }
              </strong>
            </div>
            <div className="panel">
              <span>当前操作人</span>
              <strong className="admin-actor-name">{auth.user.username}</strong>
            </div>
          </div>
          <section className="panel page-panel">
            <div className="admin-filters">
              <input
                aria-label="搜索用户"
                placeholder="搜索名称或用户名"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <select
                aria-label="角色筛选"
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value)}
              >
                <option value="">全部角色</option>
                <option value="user">普通用户</option>
                <option value="admin">Admin</option>
              </select>
              <select
                aria-label="账号状态筛选"
                value={stateFilter}
                onChange={(e) => setStateFilter(e.target.value)}
              >
                <option value="">全部状态</option>
                <option value="active">启用</option>
                <option value="inactive">停用</option>
              </select>
            </div>
            <div className="admin-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>账号</th>
                    <th>角色与权限</th>
                    <th>状态</th>
                    <th>业务数据</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <strong>{u.display_name || u.username}</strong>
                        <small>
                          {u.username}
                          {u.id === auth.user.id ? " · 当前登录" : ""}
                        </small>
                      </td>
                      <td>
                        {u.role === "admin"
                          ? "Admin / 全部功能"
                          : `普通用户 / ${u.permissions?.length || 0} 项权限`}
                      </td>
                      <td>{u.active === false ? "停用" : "启用"}</td>
                      <td>
                        {countsQuery.data
                          ? `${countsQuery.data.counts[u.id]?.tasks || 0} 个任务 · ${countsQuery.data.counts[u.id]?.training || 0} 个训练记录`
                          : countsQuery.isError
                            ? "统计暂不可用"
                            : "读取统计…"}
                      </td>
                      <td>
                        <div className="admin-actions">
                          <button
                            onClick={() => {
                              setSelected(u.id);
                              setTab("account");
                            }}
                          >
                            账号与权限
                          </button>
                          <button
                            className="primary"
                            onClick={() => {
                              setSelected(u.id);
                              setTab("overview");
                            }}
                          >
                            管理数据 →
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!visible.length && (
              <p className="empty-panel">没有符合条件的用户。</p>
            )}
          </section>
        </>
      )}

      {secureRequest?.status === "requires_user_input" ? (
        <div role="status" className="text-compare-alert">
          请在
          {secureRequest.kind === "create"
            ? "下方新建用户表单"
            : `账号 ${secureRequest.target} 的重置表单`}
          中输入并提交密码。密码不会返回给 Agent 工具。
          <button
            type="button"
            onClick={() =>
              setSecureRequest((current) =>
                current ? { ...current, status: "failed" } : current,
              )
            }
          >
            取消安全输入
          </button>
        </div>
      ) : null}

      {showCreate && (
        <AdminDialog
          title="创建用户"
          onClose={() => {
            setShowCreate(false);
            setSecureRequest(null);
          }}
        >
          <section className="panel page-panel">
            <div className="section-title">
              <h3>新建用户</h3>
            </div>
            <form className="user-create-form" onSubmit={handleCreate}>
              <div className="form-grid">
                <label className="field">
                  用户名
                  <input
                    name="username"
                    type="text"
                    autoComplete="off"
                    required
                    value={createDraft.username}
                    onChange={(event) =>
                      setCreateDraft((current) => ({
                        ...current,
                        username: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="field">
                  显示名称
                  <input
                    name="display_name"
                    type="text"
                    autoComplete="off"
                    value={createDraft.display_name}
                    onChange={(event) =>
                      setCreateDraft((current) => ({
                        ...current,
                        display_name: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="field">
                  初始密码
                  <input
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    minLength={8}
                    required
                  />
                </label>
                <label className="field">
                  角色
                  <select
                    name="role"
                    value={createDraft.role}
                    onChange={(event) =>
                      setCreateDraft((current) => ({
                        ...current,
                        role: event.target.value,
                      }))
                    }
                  >
                    <option value="user">普通用户</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
              </div>
              <PermissionGrid
                key={
                  (secureRequest?.kind === "create"
                    ? secureRequest.id
                    : "manual") + createDraft.role
                }
                entries={featureEntries}
                role={createDraft.role}
                selected={createDraft.permissions ?? defaultUserPermissions}
                name="new_permissions"
              />
              <button
                className="primary compact-action"
                type="submit"
                disabled={busy}
              >
                <Plus size={16} aria-hidden="true" />
                创建用户
              </button>
            </form>
          </section>
        </AdminDialog>
      )}

      {target && tab === "account" && (
        <section className="panel page-panel">
          <div className="section-title">
            <h3>账号与权限</h3>
            <span className="pill neutral">当前账号</span>
          </div>
          <div className="user-management-list">
            {users.length ? (
              users
                .filter((u) => u.id === selected)
                .map((user) => {
                  const isSelf = user.id === auth.user.id;
                  const temporaryPassword = temporaryPasswords[user.id] || "";
                  return (
                    <article className="user-row" key={user.id}>
                      <form
                        className="user-row-form"
                        onSubmit={handleUpdateUser(user)}
                      >
                        <div className="user-row-main">
                          <strong>{user.display_name || user.username}</strong>
                          <span>{user.username}</span>
                          <span>
                            {recordAuditText(user, {
                              owner: false,
                              includeUpdated: true,
                            })}
                          </span>
                        </div>
                        <div className="form-grid tight">
                          <label className="field">
                            显示名称
                            <input
                              name="display_name"
                              type="text"
                              defaultValue={user.display_name || ""}
                            />
                          </label>
                          <label className="field">
                            角色
                            <select
                              name="role"
                              value={draftRoles[user.id] || user.role}
                              onChange={(e) =>
                                setDraftRoles((current) => ({
                                  ...current,
                                  [user.id]: e.target.value,
                                }))
                              }
                            >
                              <option value="user">普通用户</option>
                              <option value="admin">Admin</option>
                            </select>
                          </label>
                          <div className="field compact-status">
                            账号
                            <span
                              className={`pill ${user.active === false ? "fail" : "ok"}`}
                            >
                              {user.active === false ? "停用" : "启用"}
                            </span>
                          </div>
                        </div>
                        <PermissionGrid
                          key={draftRoles[user.id] || user.role}
                          role={draftRoles[user.id] || user.role}
                          entries={featureEntries}
                          selected={user.permissions || defaultUserPermissions}
                          name={`permissions_${user.id}`}
                        />
                        <div className="user-row-actions">
                          <button
                            className="secondary compact-action"
                            type="submit"
                            disabled={busy}
                          >
                            <Save size={16} aria-hidden="true" />
                            保存
                          </button>
                          <button
                            className="secondary compact-action danger"
                            type="button"
                            disabled={busy || isSelf}
                            onClick={() =>
                              setConfirmation({
                                title:
                                  user.active === false
                                    ? "启用账号"
                                    : "停用账号",
                                impact:
                                  user.active === false
                                    ? "恢复访问；任务与实拍回流保持暂停，不会自动恢复训练。"
                                    : "撤销会话，暂停新的任务调度与实拍回流。已发出工作允许结算，历史证据保留。",
                                operation: (reason) =>
                                  updateMutation.mutateAsync({
                                    userId: user.id,
                                    payload: {
                                      active: user.active === false,
                                      reason,
                                    },
                                  }),
                              })
                            }
                          >
                            {user.active === false ? "启用" : "停用"}
                          </button>
                          <button
                            className="secondary icon-label danger"
                            type="button"
                            disabled={busy || isSelf}
                            onClick={() =>
                              setConfirmation({
                                title: "删除账号",
                                username: user.username,
                                impact:
                                  "删除登录身份与会话，停止新增调度。业务数据和历史证据保留。请优先停用；账号删除后不能从此页面恢复。",
                                operation: (reason) =>
                                  deleteMutation.mutateAsync({
                                    userId: user.id,
                                    reason,
                                  }),
                              })
                            }
                          >
                            <Trash2 size={16} aria-hidden="true" />
                            删除
                          </button>
                        </div>
                      </form>

                      <form
                        className="user-password-reset"
                        onSubmit={(event) =>
                          handlePasswordReset(user.id, event)
                        }
                      >
                        <label className="field">
                          重置密码
                          <input
                            name="password"
                            type="password"
                            autoComplete="new-password"
                            minLength={8}
                            placeholder="输入新密码"
                          />
                        </label>
                        <div className="user-password-actions">
                          <button
                            className="secondary compact-action"
                            type="submit"
                            disabled={busy}
                          >
                            <KeyRound size={16} aria-hidden="true" />
                            设置新密码
                          </button>
                          <button
                            className="secondary compact-action"
                            type="button"
                            disabled={busy || isSelf}
                            title={
                              isSelf
                                ? "当前登录账号不能生成临时密码；需要改密时请直接设置新密码。"
                                : undefined
                            }
                            onClick={() =>
                              setConfirmation({
                                title: "生成临时密码",
                                impact:
                                  "撤销目标账号全部会话；生成的临时密码仅在这里显示，请自行交付。密码不写入操作记录。",
                                operation: (reason) =>
                                  passwordMutation.mutateAsync({
                                    userId: user.id,
                                    payload: {
                                      generate: true,
                                      revoke_sessions: true,
                                      reason,
                                    },
                                  }),
                              })
                            }
                          >
                            生成临时密码
                          </button>
                          <button
                            className="secondary icon-label"
                            type="button"
                            disabled={!temporaryPassword}
                            onClick={() => copyTemporaryPassword(user.id)}
                          >
                            <Copy size={16} aria-hidden="true" />
                            复制
                          </button>
                        </div>
                        {temporaryPassword ? (
                          <>
                            <code className="user-temp-password">
                              {temporaryPassword}
                            </code>
                            <button
                              type="button"
                              className="secondary compact-action"
                              onClick={() =>
                                setTemporaryPasswords((current) => ({
                                  ...current,
                                  [user.id]: "",
                                }))
                              }
                            >
                              隐藏密码
                            </button>
                          </>
                        ) : null}
                        {isSelf ? (
                          <p className="hint-line">
                            当前登录账号不能生成临时密码；需要改密时请直接设置新密码。
                          </p>
                        ) : null}
                      </form>
                    </article>
                  );
                })
            ) : (
              <div className="empty-panel">暂无用户</div>
            )}
          </div>
        </section>
      )}
      {confirmation && (
        <AdminConfirm
          value={confirmation}
          onClose={() => setConfirmation(null)}
        />
      )}
    </section>
  );
}
