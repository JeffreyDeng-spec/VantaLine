import { FormEvent, useMemo, useState } from "react";
import { Copy, KeyRound, Plus, Save, Trash2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createUser,
  deleteUser,
  getUsers,
  queryKeys,
  resetUserPassword,
  updateUser
} from "../../api/queries";
import { ErrorState, LoadingState } from "../../components/LoadingState";
import { useToast } from "../../components/ToastProvider";
import type { AuthUser } from "../../api/types";
import { useAuth } from "../auth/auth-context";
import { recordAuditText } from "../../utils/format";

function formPermissions(form: HTMLFormElement, fieldName: string) {
  return Array.from(form.querySelectorAll<HTMLInputElement>(`input[name="${fieldName}"]:checked`)).map(
    (input) => input.value
  );
}

function PermissionGrid({
  entries,
  selected,
  name
}: {
  entries: Array<[string, string]>;
  selected: string[];
  name: string;
}) {
  const selectedSet = new Set(selected);
  return (
    <div className="permission-grid">
      {entries.map(([key, label]) => (
        <label className="permission-toggle" key={key}>
          <input name={name} type="checkbox" value={key} defaultChecked={selectedSet.has(key)} />
          <span>{label}</span>
        </label>
      ))}
    </div>
  );
}

export function UsersPage() {
  const auth = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [temporaryPasswords, setTemporaryPasswords] = useState<Record<string, string>>({});

  const usersQuery = useQuery({
    queryKey: queryKeys.users,
    queryFn: getUsers
  });

  const featureEntries = useMemo(() => {
    const features = usersQuery.data?.features || auth.features || {};
    return Object.entries(features).filter(([key]) => key !== "user_management");
  }, [auth.features, usersQuery.data?.features]);

  const defaultUserPermissions = usersQuery.data?.default_user_permissions || auth.defaultUserPermissions || [];

  const refreshUsers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.users }),
      queryClient.invalidateQueries({ queryKey: queryKeys.authStatus })
    ]);
  };

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: async () => {
      await refreshUsers();
      notify({ title: "用户已创建", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "创建用户失败", description: error.message, tone: "error" })
  });

  const updateMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: Parameters<typeof updateUser>[1] }) =>
      updateUser(userId, payload),
    onSuccess: async () => {
      await refreshUsers();
      notify({ title: "用户已更新", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "用户更新失败", description: error.message, tone: "error" })
  });

  const passwordMutation = useMutation({
    mutationFn: ({ userId, payload }: { userId: string; payload: Parameters<typeof resetUserPassword>[1] }) =>
      resetUserPassword(userId, payload),
    onSuccess: async (result, variables) => {
      if (result.temporary_password) {
        setTemporaryPasswords((current) => ({ ...current, [variables.userId]: result.temporary_password || "" }));
      } else {
        setTemporaryPasswords((current) => ({ ...current, [variables.userId]: "" }));
      }
      await refreshUsers();
      notify({
        title: result.temporary_password ? "临时密码已生成" : "密码已重置",
        description: result.revoked_sessions ? `已撤销 ${result.revoked_sessions} 个会话` : undefined,
        tone: "success"
      });
    },
    onError: (error: Error) => notify({ title: "密码更新失败", description: error.message, tone: "error" })
  });

  const deleteMutation = useMutation({
    mutationFn: deleteUser,
    onSuccess: async (_result, userId) => {
      setTemporaryPasswords((current) => ({ ...current, [userId]: "" }));
      await refreshUsers();
      notify({ title: "用户已删除", tone: "success" });
    },
    onError: (error: Error) => notify({ title: "删除失败", description: error.message, tone: "error" })
  });

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    await createMutation.mutateAsync({
      username: String(data.get("username") || "").trim(),
      display_name: String(data.get("display_name") || "").trim(),
      password: String(data.get("password") || ""),
      role: String(data.get("role") || "user"),
      permissions: formPermissions(form, "new_permissions")
    });
    form.reset();
  }

  function handleUpdateUser(user: AuthUser) {
    return async (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const form = event.currentTarget;
      const data = new FormData(form);
      await updateMutation.mutateAsync({
        userId: user.id,
        payload: {
          display_name: String(data.get("display_name") || "").trim(),
          role: String(data.get("role") || "user"),
          permissions: formPermissions(form, `permissions_${user.id}`)
        }
      });
    };
  }

  async function handlePasswordReset(userId: string, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const password = String(new FormData(form).get("password") || "");
    if (!password.trim()) {
      notify({ title: "请输入新密码", description: "或使用生成临时密码。", tone: "error" });
      return;
    }
    await passwordMutation.mutateAsync({ userId, payload: { password, revoke_sessions: true } });
    form.reset();
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

  if (usersQuery.isLoading) return <LoadingState label="正在加载用户" />;
  if (usersQuery.isError) return <ErrorState error={usersQuery.error} />;

  const users = usersQuery.data?.users || [];
  const busy =
    createMutation.isPending || updateMutation.isPending || passwordMutation.isPending || deleteMutation.isPending;

  return (
    <section className="view active">
      <header className="page-head">
        <div>
          <h2>用户管理</h2>
          <p className="page-desc">创建账号、调整角色与功能权限，并重置目标用户密码。</p>
        </div>
      </header>

      <section className="panel page-panel">
        <div className="section-title">
          <h3>新建用户</h3>
        </div>
        <form className="user-create-form" onSubmit={handleCreate}>
          <div className="form-grid">
            <label className="field">
              用户名
              <input name="username" type="text" autoComplete="off" required />
            </label>
            <label className="field">
              显示名称
              <input name="display_name" type="text" autoComplete="off" />
            </label>
            <label className="field">
              初始密码
              <input name="password" type="password" autoComplete="new-password" minLength={8} required />
            </label>
            <label className="field">
              角色
              <select name="role" defaultValue="user">
                <option value="user">普通用户</option>
                <option value="admin">Admin</option>
              </select>
            </label>
          </div>
          <PermissionGrid entries={featureEntries} selected={defaultUserPermissions} name="new_permissions" />
          <button className="primary compact-action" type="submit" disabled={busy}>
            <Plus size={16} aria-hidden="true" />
            创建用户
          </button>
        </form>
      </section>

      <section className="panel page-panel">
        <div className="section-title">
          <h3>账号与权限</h3>
          <span className="pill neutral">{users.length} 个用户</span>
        </div>
        <div className="user-management-list">
          {users.length ? (
            users.map((user) => {
              const isSelf = user.id === auth.user.id;
              const temporaryPassword = temporaryPasswords[user.id] || "";
              return (
                <article className="user-row" key={user.id}>
                  <form className="user-row-form" onSubmit={handleUpdateUser(user)}>
                    <div className="user-row-main">
                      <strong>{user.display_name || user.username}</strong>
                      <span>{user.username}</span>
                      <span>{recordAuditText(user, { owner: false, includeUpdated: true })}</span>
                    </div>
                    <div className="form-grid tight">
                      <label className="field">
                        显示名称
                        <input name="display_name" type="text" defaultValue={user.display_name || ""} />
                      </label>
                      <label className="field">
                        角色
                        <select name="role" defaultValue={user.role === "admin" ? "admin" : "user"}>
                          <option value="user">普通用户</option>
                          <option value="admin">Admin</option>
                        </select>
                      </label>
                      <div className="field compact-status">
                        账号
                        <span className={`pill ${user.active === false ? "fail" : "ok"}`}>
                          {user.active === false ? "停用" : "启用"}
                        </span>
                      </div>
                    </div>
                    <PermissionGrid
                      entries={featureEntries}
                      selected={user.role === "admin" ? featureEntries.map(([key]) => key) : user.permissions || []}
                      name={`permissions_${user.id}`}
                    />
                    <div className="user-row-actions">
                      <button className="secondary compact-action" type="submit" disabled={busy}>
                        <Save size={16} aria-hidden="true" />
                        保存
                      </button>
                      <button
                        className="secondary compact-action danger"
                        type="button"
                        disabled={busy || isSelf}
                        onClick={() =>
                          updateMutation.mutate({
                            userId: user.id,
                            payload: { active: user.active === false }
                          })
                        }
                      >
                        {user.active === false ? "启用" : "停用"}
                      </button>
                      <button
                        className="secondary icon-label danger"
                        type="button"
                        disabled={busy || isSelf}
                        onClick={() => {
                          if (window.confirm(`确认删除用户 ${user.username}？`)) deleteMutation.mutate(user.id);
                        }}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                        删除
                      </button>
                    </div>
                  </form>

                  <form className="user-password-reset" onSubmit={(event) => handlePasswordReset(user.id, event)}>
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
                      <button className="secondary compact-action" type="submit" disabled={busy}>
                        <KeyRound size={16} aria-hidden="true" />
                        设置新密码
                      </button>
                      <button
                        className="secondary compact-action"
                        type="button"
                        disabled={busy || isSelf}
                        title={isSelf ? "当前登录账号不能生成临时密码；需要改密时请直接设置新密码。" : undefined}
                        onClick={() =>
                          passwordMutation.mutate({
                            userId: user.id,
                            payload: { generate: true, revoke_sessions: true }
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
                    {temporaryPassword ? <code className="user-temp-password">{temporaryPassword}</code> : null}
                    {isSelf ? <p className="hint-line">当前登录账号不能生成临时密码；需要改密时请直接设置新密码。</p> : null}
                  </form>
                </article>
              );
            })
          ) : (
            <div className="empty-panel">暂无用户</div>
          )}
        </div>
      </section>
    </section>
  );
}
