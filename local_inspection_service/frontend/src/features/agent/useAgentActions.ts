import { useLayoutEffect, useRef } from "react";
import type { ActionDefinition } from "./contracts";
import { actionRegistry } from "./registry";

// Hooks publish existing business callbacks, never DOM selectors or click events.
export function useAgentActions(actions: ActionDefinition[]) {
  const current = useRef(actions);
  current.current = actions;
  const names = actions.map(action => action.name).join("|");
  useLayoutEffect(() => actionRegistry.register(current.current.map(action => ({
    ...action,
    workspaceLocal: true,
    available: () => current.current.find(item => item.name === action.name)?.available?.() ?? null,
    execute: input => {
      const latest = current.current.find(item => item.name === action.name);
      if (!latest) throw new Error("Workspace action is no longer mounted");
      return latest.execute(input);
    }
  }))), [names]);
  useLayoutEffect(() => { actionRegistry.refresh(); });
}
