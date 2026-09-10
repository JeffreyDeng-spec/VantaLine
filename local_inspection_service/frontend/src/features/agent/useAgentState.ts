import type { Schema } from "./contracts";
import { useAgentActions } from "./useAgentActions";

/** Page-owned fields reuse the React setters used by the human form. */
export function useAgentState(name: string, domain: string, fields: Record<string, { value: unknown; schema: Schema; set: (value: never) => void }>) {
  useAgentActions([
    {name:`${name}_get_state`,domain,description:`Read the editable ${name} workspace fields.`,readOnly:true,inputSchema:{type:"object",properties:{},additionalProperties:false},execute:()=>Object.fromEntries(Object.entries(fields).map(([key,field])=>[key,field.value]))},
    {name:`${name}_set_fields`,domain,description:`Set ${name} form and selection fields using the same state setters as the page. This does not submit or save the form.`,readOnly:false,inputSchema:{type:"object",properties:Object.fromEntries(Object.entries(fields).map(([key,field])=>[key,field.schema])),additionalProperties:false},execute:input=>{
      for(const [key,value] of Object.entries(input)) fields[key].set(value as never);
      return {status:"completed",data:{updated_fields:Object.keys(input)},next_action:`${name}_get_state`};
    }}
  ]);
}
