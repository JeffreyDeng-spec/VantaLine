import * as queries from "../../api/queries";
import type {ActionDefinition, Schema} from "./contracts";

async function assetId(accessoryId: string, sourcePath: string) {
  const bytes = new TextEncoder().encode(`${accessoryId}\0${sourcePath}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map(value => value.toString(16).padStart(2,"0")).join("");
}
async function assets(accessoryId: string) {
  const detail = await queries.getAccessoryDetail(accessoryId);
  const gallery = await Promise.all((detail.gallery ?? []).map(async item => ({...item, asset_id:await assetId(accessoryId,item.source_path || "")})));
  return {...detail,gallery};
}
async function resolve(input: Record<string,unknown>) {
  const detail = await assets(String(input.accessoryId));
  const asset = detail.gallery.find(item => item.asset_id === input.asset_id && item.source_path);
  if (!asset) throw new Error("Asset is no longer in this accessory. Refresh its gallery.");
  return asset.source_path!;
}
const identity: Record<string,Schema> = {accessoryId:{type:"string",minLength:1},asset_id:{type:"string",minLength:64,maxLength:64}};
const base = {domain:"accessories",permissions:["accessory_library"],invalidates:["accessories","training"]};
export const accessoryActions: ActionDefinition[] = [
  {...base,name:"get_accessory_detail",description:"Read the accessory and current gallery, including opaque asset IDs for crop, reference selection and deletion.",readOnly:true,inputSchema:{type:"object",properties:{accessoryId:identity.accessoryId},required:["accessoryId"],additionalProperties:false},execute:input=>assets(String(input.accessoryId))},
  {...base,name:"set_accessory_ai_reference",description:"Select a current accessory asset as its AI reference using its asset ID.",readOnly:false,inputSchema:{type:"object",properties:identity,required:Object.keys(identity),additionalProperties:false},execute:async input=>queries.setAccessoryAiReference(String(input.accessoryId),await resolve(input))},
  {...base,name:"delete_accessory_file",description:"Delete the specified owned accessory asset using the existing removal workflow.",readOnly:false,inputSchema:{type:"object",properties:identity,required:Object.keys(identity),additionalProperties:false},execute:async input=>queries.deleteAccessoryFile(String(input.accessoryId),await resolve(input))},
  {...base,name:"crop_accessory_text_image",description:"Crop a current text asset with four ordered corners (top-left, top-right, bottom-right, bottom-left), coordinates in source-image percent, 0–100.",readOnly:false,inputSchema:{type:"object",properties:{...identity,corners:{type:"array",minItems:4,maxItems:4,items:{type:"object",properties:{x:{type:"number",minimum:0,maximum:100},y:{type:"number",minimum:0,maximum:100}},required:["x","y"],additionalProperties:false}}},required:[...Object.keys(identity),"corners"],additionalProperties:false},execute:async input=>queries.cropAccessoryTextImage(String(input.accessoryId),{source_path:await resolve(input),corners:input.corners as {x:number;y:number}[]})}
];
