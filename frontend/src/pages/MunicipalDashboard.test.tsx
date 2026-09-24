import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MunicipalDashboard } from "./MunicipalDashboard";
import type { AuthState } from "../hooks/useAuth";

const auth: AuthState = { user: { user_id: "r", username: "reviewer", role: "EMPLOYEE" }, authRequired: true, initialized: true, loading: false, error: null, login: vi.fn(), logout: vi.fn() };
const connected = Date.now()/1000 - 30;
function backend() {
  const state = { count: 9, reason: "FRESH", condition: "NORMAL", generation: 1, metricGeneration: 1, cameraState: "ONLINE", budget: 5, stalled: false };
  const health = () => ({ camera_id:"camera-3",source_type:"RTSP",state:state.cameraState,generation:state.generation,last_connected_at:connected,last_frame_at:Date.now()/1000,heartbeat_at:Date.now()/1000,checked_at:Date.now()/1000,valid_for_seconds:10,camera_capture_fps:12,preview_publication_fps:12,ai_inference_fps:4,processing_fps:4 });
  vi.spyOn(globalThis,"fetch").mockImplementation(async(input) => {
    const url=String(input); const json=(body:unknown)=>new Response(JSON.stringify(body),{status:200});
    if(url==="/api/scenarios")return json({scenarios:[{scenario_id:"normal_traffic",title:"Normal Traffic",description:"Recorded",source_url:"user-provided"},{scenario_id:"congestion",title:"Heavy Congestion",description:"Recorded",source_url:"user-provided"}]});
    if(url==="/api/live-cameras")return json([health()]);
    if(url.endsWith("/metrics")){
      if(state.stalled)return new Promise<Response>(()=>{});
      return json({camera_id:"camera-3",checked_at:Date.now()/1000,max_age_seconds:5,valid_for_seconds:state.budget,reason:state.reason,health:health(),metrics:state.reason==="FRESH"?{frame:200,timestamp:Date.now()/1000,generation:state.metricGeneration,active_vehicle_count:state.count,cars:state.count,buses:0,trucks:0,motorcycles:0,bicycles:0,people:0,active_track_count:state.count,traffic_state:state.condition}:null});
    }
    if(url.includes("/live-cameras/")&&url.endsWith("/events"))return json({events:[{event_id:"old-live",event_type:"WRONG_WAY",timestamp:Date.now()/1000-600,confidence:.9,severity:"HIGH",camera_name:"DVR Camera 3",explanation:"Earlier proposed incident",evidence_image:"evidence/old.jpg",status:"PROPOSED"}],total:1});
    if(url.endsWith("/events"))return json({events:[],total:0});
    if(url.endsWith("/summary"))return json({status:"READY",annotated_video_available:true});
    if(url.endsWith("/timeline")){const n=url.includes("/congestion/")?42:3;const traffic_state=url.includes("/congestion/")?"HEAVY_CONGESTION":"NORMAL";return json({status:"READY",frames:[{frame:0,timestamp_sec:0,traffic_state,active_vehicle_count:n,cars:n,buses:0,trucks:0,motorcycles:0,people:0,bicycles:0}],message:"Recorded counts"});}
    return new Response("{}",{status:404});
  });
  return state;
}
function value(label:string){return within(screen.getByRole("region",{name:"Current traffic summary"})).getByText(label).closest("article")!.querySelector("strong")!.textContent;}
async function ready(){await screen.findByRole("button",{name:/DVR Camera 3/});}
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.useRealTimers();});

describe("Live truth",()=>{
  it("shows fresh live counts and preserves MODERATE independently of old incidents",async()=>{
    const state=backend();state.condition="MODERATE";render(<MunicipalDashboard auth={auth}/>);
    await waitFor(()=>expect(value("Vehicles")).toBe("9"));
    expect(value("Traffic status")).toBe("Moderate");
    expect(await screen.findByText("Earlier proposed incident")).toBeInTheDocument();
  });
  it.each(["MISSING","STALE","INVALID","GENERATION_MISMATCH"])("%s metrics show unknown, not recorded counts or zero",async(reason)=>{
    const state=backend();state.reason=reason;render(<MunicipalDashboard auth={auth}/>);
    await screen.findByText("WAITING FOR AI");
    expect(value("Vehicles")).toBe("—");expect(value("Tracks")).toBe("—");expect(value("Traffic status")).toBe("Unknown");
    expect(screen.getByAltText("Raw live preview for DVR Camera 3")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"AI VIEW"}));
    expect(screen.queryByAltText("AI processed view for DVR Camera 3")).not.toBeInTheDocument();
  });
  it("fresh zero remains zero",async()=>{
    const state=backend();state.count=0;render(<MunicipalDashboard auth={auth}/>);
    await screen.findByText("REAL LIVE CAMERA DATA");expect(value("Vehicles")).toBe("0");expect(value("Traffic status")).toBe("Normal");
  });
  it("switches recorded → live → recorded without cross-source fallback",async()=>{
    const state=backend();render(<MunicipalDashboard auth={auth}/>);await ready();
    fireEvent.click(screen.getByRole("button",{name:/Heavy Congestion/}));
    await waitFor(()=>expect(value("Vehicles")).toBe("42"));
    state.reason="MISSING";
    fireEvent.click(screen.getByRole("button",{name:/DVR Camera 3/}));
    expect(value("Vehicles")).toBe("—");
    await screen.findByText("WAITING FOR AI");expect(value("Vehicles")).toBe("—");
    fireEvent.click(screen.getByRole("button",{name:/Heavy Congestion/}));
    await waitFor(()=>expect(value("Vehicles")).toBe("42"));
    expect(value("Traffic status")).toBe("Heavy congestion");
  });
  it.each(["generation","reconnecting"])("invalidates existing values on %s while keeping incident history",async(change)=>{
    const state=backend();render(<MunicipalDashboard auth={auth}/>);
    await waitFor(()=>expect(value("Vehicles")).toBe("9"));
    if(change==="generation")state.generation=2;else state.cameraState="RECONNECTING";
    await waitFor(()=>expect(value("Vehicles")).toBe("—"),{timeout:3500});
    expect(screen.getByText("Earlier proposed incident")).toBeInTheDocument();
    if(change==="reconnecting")expect(screen.queryByAltText("Raw live preview for DVR Camera 3")).not.toBeInTheDocument();
  });
  it("expires cached counts even when the next metric request stalls",async()=>{
    const state=backend();state.budget=.3;render(<MunicipalDashboard auth={auth}/>);
    await waitFor(()=>expect(value("Vehicles")).toBe("9"));state.stalled=true;
    await waitFor(()=>expect(value("Vehicles")).toBe("—"),{timeout:1500});
    expect(screen.getByAltText("Raw live preview for DVR Camera 3")).toBeInTheDocument();
  });
});
