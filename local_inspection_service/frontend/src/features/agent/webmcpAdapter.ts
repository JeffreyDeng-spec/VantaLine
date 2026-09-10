import type { ModelContext } from "./contracts";
import type { ActionRegistry } from "./registry";

type Registration = {owner:symbol; controller:AbortController};
type Binding = { owner: symbol; chain: Promise<void>; registered: Map<string,Registration>; inFlight:Map<string,number>; refresh?:()=>void };
const bindings = new WeakMap<ModelContext, Binding>();

// One queue per document, including React StrictMode remounts and session changes.
export function connectWebMCP(context: ModelContext, registry: ActionRegistry, domain: () => string, onError: (message: string) => void, onReady: (ready:boolean) => void = () => {}) {
  const owner = Symbol();
  onReady(false);
  let binding = bindings.get(context);
  if (!binding) { binding = {owner, chain: Promise.resolve(), registered: new Map(), inFlight:new Map()}; bindings.set(context, binding); }
  const shared = binding;
  shared.owner = owner;
  let closed = false;
  let revision = 0;
  const remove = async (name:string, registration:Registration) => {
    // Before Chrome 153, unregistration can abort an in-flight tool execution.
    // Keep its result channel until completion, while its wrapper rejects reuse.
    if (shared.inFlight.has(name)) return;
    registration.controller.abort();
    // Compatibility with older implementations; current WebMCP uses the signal.
    if (context.unregisterTool) await context.unregisterTool(name);
    shared.registered.delete(name);
  };
  const reconcile = () => {
    const requested = ++revision;
    shared.chain = shared.chain.then(async () => {
      if (requested !== revision || shared.owner !== owner) return;
      const wanted = closed ? [] : registry.list().filter(action => action.available && (action.workspaceLocal || action.domain === "core" || action.domain === domain()));
      const coreOrder=["get_context","list_capabilities","open_workspace","get_operation"];
      const priority=(name:string)=>{const index=coreOrder.indexOf(name);return index<0?coreOrder.length:index;};
      wanted.sort((a,b)=>priority(a.name)-priority(b.name));
      const names = new Set(wanted.map(action => `vantaline_${action.name}`));
      for (const [name,registration] of shared.registered) if (registration.owner !== owner || !names.has(name)) await remove(name,registration);
      for (const action of wanted) {
        if (closed || shared.owner !== owner) break;
        const name = `vantaline_${action.name}`;
        if (shared.registered.has(name)) continue;
        const controller=new AbortController();
        try {
          await context.registerTool({ name, description: action.description, inputSchema: action.inputSchema, annotations: { readOnlyHint: action.readOnly, untrustedContentHint:true }, execute: async (input,options) => {
            if (closed || shared.owner !== owner || controller.signal.aborted) return JSON.stringify({status:"failed",error:{code:"SESSION_CHANGED",message:"This tool registration is no longer active."}});
            if (options?.signal?.aborted) return JSON.stringify({status:"failed",error:{code:"CANCELLED",message:"Cancelled before execution."}});
            // Browser cancellation never implicitly replays or interrupts PLC I/O.
            shared.inFlight.set(name,(shared.inFlight.get(name) ?? 0)+1);
            try { return JSON.stringify(await registry.execute(action.name, input)); }
            finally { const remaining=(shared.inFlight.get(name) ?? 1)-1;if(remaining)shared.inFlight.set(name,remaining);else shared.inFlight.delete(name);shared.refresh?.(); }
          } }, {signal:controller.signal});
          shared.registered.set(name,{owner,controller});
        } catch (error) { controller.abort(); throw error; }
      }
      if (!closed && shared.owner === owner && requested === revision) onReady(true);
    }).catch(() => { onReady(false); onError("Browser tool registration failed; refresh the tool menu."); });
  };
  shared.refresh = reconcile;
  const unsubscribe = registry.subscribe(reconcile);
  reconcile();
  return { refresh: reconcile, close: () => { closed = true; unsubscribe(); reconcile(); return shared.chain; } };
}
