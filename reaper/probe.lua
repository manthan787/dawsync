-- Read-only diagnostics used during development; no project changes.
local _, filename = reaper.get_action_context()
local script_dir = filename:match("^(.*[/\\])")
local diagnostics = reaper.GetResourcePath() .. "/DAWSync/diagnostics"
reaper.RecursiveCreateDirectory(diagnostics, 0)
local output = assert(io.open(diagnostics .. "/reaper-probe.txt", "w"))
for i = 0, 65535 do
  local cmd = reaper.kbd_enumerateActions(0, i)
  if cmd == 0 then break end
  local text = reaper.kbd_getTextFromCmd(cmd, 0)
  if text:lower():find("render") and (text:lower():find("recent") or text:lower():find("close")) then
    output:write(cmd, " ", text, "\n")
  end
end
output:write("EXTSTATE=", select(2, reaper.GetProjExtState(0, "DAWSYNC", "project_id")), "\n")
local codec = dofile(script_dir .. "codec.lua")
assert(codec.sha256("")=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
assert(codec.sha256("abc")=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
assert(codec.sha256(string.rep("a",1000000))=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0")
local json=codec.encode({unicode="Café 🎸",empty=codec.array(),marker=codec.array({{name="A",seconds=1.25}})})
local parsed=codec.decode(json)
assert(parsed.unicode=="Café 🎸" and parsed.marker[1].seconds==1.25 and #parsed.empty==0)
output:write("CODEC_TESTS=passed\n")
output:write("RENDER_FORMAT=",select(2,reaper.GetSetProjectInfo_String(0,"RENDER_FORMAT","",false)),"\n")
for i=0,reaper.CountTracks(0)-1 do
 local tr=reaper.GetTrack(0,i)
 output:write("TRACK_ID=",select(2,reaper.GetSetMediaTrackInfo_String(tr,"P_EXT:DAWSYNC_ID","",false))," ROLE=",select(2,reaper.GetSetMediaTrackInfo_String(tr,"P_EXT:DAWSYNC_ROLE","",false)),"\n")
end
output:close()
