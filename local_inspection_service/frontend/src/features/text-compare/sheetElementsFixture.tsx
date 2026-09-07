// Development-only entry referenced by tests/sheet-elements.html, not application routes.
import {useState} from "react";
import {createRoot} from "react-dom/client";
import {SheetElementsPanel} from "./SheetElementsPanel";
const canvas=document.createElement("canvas");canvas.width=900;canvas.height=500;
const ctx=canvas.getContext("2d")!;ctx.fillStyle="white";ctx.fillRect(0,0,900,500);ctx.fillStyle="black";ctx.font="40px sans-serif";ctx.fillText("20V",100,100);
const image=canvas.toDataURL("image/png");
(window as unknown as {fixtureUrl:string}).fixtureUrl=image;
function Fixture(){const [asset,setAsset]=useState("asset_a"),[file,setFile]=useState(new File(["fixture"],"image.png"));return <><button onClick={()=>setAsset(v=>v==="asset_a"?"asset_b":"asset_a")}>更换标准</button><button onClick={()=>setFile(new File(["next"],"next.png"))}>更换实拍</button><SheetElementsPanel assetId={asset} revision={asset+"_rev"} referenceUrl={image} file={file} capture={async()=>file} onCaptured={setFile} onZoom={()=>{}}/></>}
createRoot(document.getElementById("root")!).render(<Fixture/>);
