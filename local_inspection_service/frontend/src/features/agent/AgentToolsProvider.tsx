import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../auth/auth-context";
import { apiClient } from "../../api/client";
import { hasPermission } from "../../app/permissions";
import { actionRegistry } from "./registry";
import { apiActions } from "./apiActions.generated";
import { accessoryActions } from "./accessoryActions";
import { clearFiles, listFiles } from "./files";
import { connectWebMCP } from "./webmcpAdapter";
import { useAgentActions } from "./useAgentActions";

export const workspaces: Record<string, string> = { detection: "/inspect", accessories: "/accessories", text: "/text-compare-beta", training: "/training-library", pipeline: "/pipeline", analysis: "/data-analysis", settings: "/rules", users: "/users", overview: "/" };
function domainFor(path: string) {
  if (path.startsWith("/tasks/") && path.endsWith("/inspect")) return "detection";
  if (path.startsWith("/tasks/")) return "pipeline";
  return Object.entries(workspaces).find(([, route]) => route !== "/" && path.startsWith(route))?.[0] ?? "core";
}

export function AgentToolsProvider() {
  const auth = useAuth();
  const authRef = useRef(auth); authRef.current = auth;
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const domain = useRef(domainFor(location.pathname)); domain.current = domainFor(location.pathname);
  const adapterRef = useRef<ReturnType<typeof connectWebMCP> | null>(null);
  const [registrationError, setRegistrationError] = useState("");
  const [registrationReady, setRegistrationReady] = useState(false);
  const policy = useQuery({ queryKey: ["agent", "capabilities", auth.user.id], queryFn: () => apiClient.get<{ enabled: boolean }>("/api/agent/capabilities"), retry: false, staleTime: 0, refetchInterval: 15000 });
  const enabled = policy.data?.enabled === true;
  useLayoutEffect(() => {
    actionRegistry.configure(action => enabled && (!action.permissions?.length || action.permissions.some(permission => hasPermission(authRef.current.user, permission))), async action => {
      if (action.invalidates?.length) await queryClient.invalidateQueries({refetchType:"active",predicate:query=>action.invalidates!.includes(String(query.queryKey[0]))});
      // Allow React to commit local state before the Agent reads it again.
      await new Promise<void>(resolve => {
        const fallback = setTimeout(resolve,100);
        requestAnimationFrame(() => { clearTimeout(fallback); resolve(); });
      });
    });
    return () => { actionRegistry.reset(); clearFiles(); };
  }, [enabled, auth.user.id, auth.dataUserId, queryClient]);
  useEffect(() => actionRegistry.register([...apiActions(() => authRef.current), ...accessoryActions]), []);
  useEffect(() => {
    if (!enabled || typeof document.modelContext?.registerTool !== "function") return;
    let adapter: ReturnType<typeof connectWebMCP> | undefined;
    // Let React finish a mount/StrictMode cleanup cycle before publishing native
    // tools; otherwise a client can discover the throwaway first registration.
    const start = setTimeout(() => {
      adapter = connectWebMCP(document.modelContext!, actionRegistry, () => domain.current, setRegistrationError, setRegistrationReady);
      adapterRef.current = adapter;
    }, 0);
    return () => { clearTimeout(start); if(adapterRef.current===adapter)adapterRef.current=null; void adapter?.close(); };
  }, [enabled, auth.user.id, auth.dataUserId]);
  useEffect(() => { adapterRef.current?.refresh(); }, [location.pathname]);
  useAgentActions([
    { name: "get_context", domain: "core", description: "Read current workspace and account scope. Use list_capabilities for the tool menu.", readOnly: true, inputSchema: {type:"object",properties:{},additionalProperties:false}, execute: () => ({ route: location.pathname, account_id: auth.user.id, data_scope: auth.dataUserId || auth.user.id, workspace: domain.current, files: listFiles(), action_count: actionRegistry.list().length }) },
    { name: "list_capabilities", domain: "core", description: "Page the authorized tool menu. Request an action name for its full schema. Workspace actions appear after opening that workspace.", readOnly: true, inputSchema: {type:"object",properties:{domain:{type:"string"},name:{type:"string"},offset:{type:"integer",minimum:0},limit:{type:"integer",minimum:1,maximum:50}},additionalProperties:false}, execute: input => {
      const matches = actionRegistry.list().filter(action => (!input.domain || action.domain === input.domain) && (!input.name || action.name === input.name));
      const offset = Number(input.offset ?? 0), limit = Number(input.limit ?? 25);
      return {workspaces, total:matches.length, next_offset:offset + limit < matches.length ? offset + limit : null, actions:matches.slice(offset, offset + limit).map(({inputSchema,...action}) => input.name ? {...action,inputSchema} : action)};
    } },
    { name: "open_workspace", domain: "core", description: "Open an application workspace; then refresh capabilities to use its business tools.", readOnly: false, inputSchema: {type:"object",properties:{workspace:{type:"string",enum:Object.keys(workspaces)}},required:["workspace"],additionalProperties:false}, execute: input => { navigate(workspaces[String(input.workspace)]); return { status: "accepted", next_action: "get_context" }; } },
    { name: "list_files", domain: "core", description: "List files explicitly selected in the current signed-in page; identifiers can be used in multipart actions.", readOnly: true, inputSchema:{type:"object",properties:{},additionalProperties:false}, execute: listFiles },
    {name:"get_operation",domain:"core",description:"Read the status and version of a durable operation owned by this account.",readOnly:true,inputSchema:{type:"object",properties:{operation_id:{type:"string",minLength:1,maxLength:128}},required:["operation_id"],additionalProperties:false},execute:input=>apiClient.get(`/api/operations/${encodeURIComponent(String(input.operation_id))}`)},
    {name:"cancel_operation",domain:"core",description:"Request cancellation of an owned durable operation at its current version. Running work keeps its reservation until cancellation is verified.",readOnly:false,inputSchema:{type:"object",properties:{operation_id:{type:"string",minLength:1,maxLength:128},expected_version:{type:"integer",minimum:1}},required:["operation_id","expected_version"],additionalProperties:false},execute:input=>apiClient.post(`/api/operations/${encodeURIComponent(String(input.operation_id))}/cancel`,{expected_version:input.expected_version})},
    { name: "logout", domain:"core",description:"End the current application login session and revoke its active tool access.",readOnly:false,endsSession:true,inputSchema:{type:"object",properties:{},additionalProperties:false},execute:()=>auth.logout() }
  ]);
  if (!enabled) return null;
  return <aside data-agent-ready={registrationReady} aria-label="Agent 工具状态" style={{padding:"4px 12px",fontSize:12}}>
    {registrationError || (document.modelContext ? (registrationReady ? "Agent 工具已启用 · 使用当前账号权限" : "正在准备 Agent 工具") : "此浏览器未提供 WebMCP；平台功能正常可用")}
  </aside>;
}
