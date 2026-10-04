-- DAWSync: start on a generated session.rpp; save normally to publish updates.
-- Lua runs inside REAPER on Windows or macOS. No Python, SWS, or plugins required.
local _, script = reaper.get_action_context()
local script_dir = script:match("^(.*)[/\\]")
local codec = dofile(script_dir .. "/codec.lua")
local function norm(p) return (p:gsub("\\", "/")):gsub("/+$", "") end
local function dirname(p) return norm(p):match("^(.*)/[^/]+$") end
local function join(a,b) return norm(a).."/"..b end
local function read(p)
  local f=io.open(p,"rb") if not f then return nil end
  local s=f:read("*a") f:close() return s
end
local function write(p,s)
  local f=assert(io.open(p,"wb"),"Cannot write "..p) assert(f:write(s)) f:close()
end
local function mkdir(p) reaper.RecursiveCreateDirectory(p,0) end
local function copy(from,to)
  mkdir(dirname(to))
  local source=assert(io.open(from,"rb"),"Media not downloaded: "..from)
  local target=assert(io.open(to,"wb"),"Cannot write "..to)
  while true do
    local chunk=source:read(1048576) if not chunk then break end assert(target:write(chunk))
    if coroutine.isyieldable() then coroutine.yield() end
  end
  source:close() target:close()
end
local function filehash(path)
  -- Built-in OS tools are fast; Lua remains a cooperative fallback.
  local command
  if reaper.GetOS():find("Win") then
    local literal="'"..path:gsub("'","''").."'"
    local ps="(Get-FileHash -Algorithm SHA256 -LiteralPath "..literal..").Hash"
    -- Encode PowerShell's UTF-16 command to keep paths out of shell syntax.
    local bytes={}
    for _,c in utf8.codes(ps) do
      if c>0xffff then
        c=c-0x10000
        bytes[#bytes+1]=string.pack("<I2I2",0xd800+(c>>10),0xdc00+(c&1023))
      else bytes[#bytes+1]=string.pack("<I2",c) end
    end
    local data=table.concat(bytes)
    local alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    local encoded={}
    for i=1,#data,3 do
      local a,b,c=data:byte(i,i+2)
      local v=(a<<16)|((b or 0)<<8)|(c or 0)
      encoded[#encoded+1]=alphabet:sub((v>>18)+1,(v>>18)+1)..alphabet:sub(((v>>12)&63)+1,((v>>12)&63)+1)..
        (b and alphabet:sub(((v>>6)&63)+1,((v>>6)&63)+1) or "=")..(c and alphabet:sub((v&63)+1,(v&63)+1) or "=")
    end
    command="powershell.exe -NoProfile -NonInteractive -EncodedCommand "..table.concat(encoded)
  else command="/usr/bin/shasum -a 256 '"..path:gsub("'","'\\''").."'" end
  local output=reaper.ExecProcess(command,2000)
  local status,body=(output or ""):match("^(%-?%d+)\n(.*)")
  local hash=body and body:match("([%x]+)")
  if status=="0" and hash and #hash==64 then
    local f=assert(io.open(path,"rb")) local size=f:seek("end") f:close()
    return hash:lower(),size
  end
  return codec.sha256_file(path)
end
local function guid() return reaper.genGuid():gsub("[{}%-]", ""):lower() end
local function ext(project,key) return select(2,reaper.GetProjExtState(project,"DAWSYNC",key)) end
local function setext(project,key,val) reaper.SetProjExtState(project,"DAWSYNC",key,val) end
local function trackext(track,key) return select(2,reaper.GetSetMediaTrackInfo_String(track,"P_EXT:DAWSYNC_"..key,"",false)) end
local function q(s) return '"'..s:gsub('["\\\r\n%z\1-\31]'," ")..'"' end
local function portable(relative)
  assert(type(relative)=="string" and not relative:find("\\") and not relative:find("^/") and not relative:find("%.%.") and relative:match("^[%w_./%-]+$"),"Unsafe package path")
  return relative
end
local function verify(folder,m)
  assert(m.schema==1 and m.kind=="dawsync-revision", "Unsupported DAWSync revision")
  assert(m.project_id:match("^[%w_-]+$") and m.revision_id:match("^[%w_-]+$"),"Invalid revision identity")
  for relative,info in pairs(m.files) do
    local path=join(folder,portable(relative))
    local hash,size=filehash(path)
    assert(hash==info.sha256 and size==info.size,"Waiting for complete media: "..relative)
  end
end
local function wav(path)
  local f=assert(io.open(path,"rb"))
  local header=f:read(12) assert(header and header:sub(1,4)=="RIFF" and header:sub(9)=="WAVE","Expected RIFF WAV")
  local length=string.unpack("<I4",header,5)+8
  local rate,channels,align,frames,format,bits,subformat
  while f:seek()+8<=length do
    local chunk=f:read(8) if not chunk or #chunk<8 then break end
    local tag,size=string.unpack("<c4I4",chunk) local pos=f:seek()
    if tag=="fmt " then
      local bytes=f:read(math.min(size,40))
      local byte_rate
      format,channels,rate,byte_rate,align,bits=string.unpack("<I2I2I4I4I2I2",bytes)
      if format==65534 and #bytes>=40 then subformat=string.unpack("<I2",bytes,25) end
      assert(channels<=2 and channels>=1,"Only mono/stereo WAV supported")
    elseif tag=="data" then assert(align and size%align==0) frames=size/align end
    f:seek("set",pos+size+size%2)
  end
  local actual=f:seek("end") f:close()
  assert(actual>=length and rate and frames and frames>0,"Render is incomplete")
  return {sample_rate=rate,channels=channels,frames=frames,duration=frames/rate,format=format,bits=bits,subformat=subformat}
end
local function project_text(m)
  local lines={'<REAPER_PROJECT 0.1 7 1','  RIPPLE 0','  TIMELOCKMODE 0','  MASTER_VOLUME 1',
    '  SAMPLERATE '..m.sample_rate,'  TEMPO '..m.tempo.bpm..' '..m.tempo.numerator..' '..m.tempo.denominator,'  RECORD_PATH "recordings"',
    '  <EXTSTATE','    <DAWSYNC','      project_id '..q(m.project_id),'      revision_id '..q(m.revision_id),
    '      content_end_seconds '..q(tostring(m.content_end_seconds)),'    >','  >'}
  for _,mark in ipairs(m.markers) do lines[#lines+1]=string.format('  MARKER %d %.12g %s 0',mark.index,mark.seconds,q(mark.name)) end
  for _,t in ipairs(m.tracks) do
    local muted=t.role=="reference" and 1 or 0
    local name=(muted==1 and "REFERENCE — " or "")..t.name
    local chunk={'  <TRACK '..reaper.genGuid(),'    NAME '..q(name),'    VOLPAN 1 0 1 -1',
      '    MUTESOLO '..muted..' 0 0','    MAINSEND 1','    ISBUS 0 0','    REC 0 -1 0 0 0 0 0 0',
      '    <EXT','      DAWSYNC_ID '..q(t.id),'      DAWSYNC_ROLE '..q(t.role),'    >','    <ITEM',
      '      POSITION 0','      LENGTH '..string.format('%.12g',t.duration),'      VOLPAN 1 0 1 -1',
      '      SOFFS 0','      BEAT 0','      LOOP 0','      FADEIN 1 0 0','      FADEOUT 1 0 0',
      '      <EXTI','        DAWSYNC_SOURCE_END '..q(tostring(m.content_end_seconds)),'      >',
      '      NAME '..q(t.name),'      <SOURCE WAVE','        FILE '..q(t.file),'      >','    >','  >'}
    for _,l in ipairs(chunk) do lines[#lines+1]=l end
  end
  lines[#lines+1]='>' return table.concat(lines,"\n").."\n"
end

local function publish(project,exchange)
  assert(reaper.GetPlayStateEx(project)==0,"Stop playback before publishing")
  local project_id=ext(project,"project_id")
  local parent=ext(project,"revision_id")
  assert(project_id~="" and parent~="","Project has no DAWSync identity")
  local numerator,denominator,bpm=reaper.TimeMap_GetTimeSigAtTime(project,0)
  assert(numerator>=1 and numerator<=32 and (denominator==1 or denominator==2 or denominator==4 or denominator==8 or denominator==16 or denominator==32),
    "Unsupported project time signature")
  for i=0,reaper.CountTempoTimeSigMarkers(project)-1 do
    local _,time,_,_,mbpm,num,den=reaper.GetTempoTimeSigMarker(project,i)
    assert(math.abs(mbpm-bpm)<0.0000001 and (num==0 or num==numerator) and (den==0 or den==denominator),
      "Tempo or time-signature changes need a map adapter")
  end
  local rid=guid()
  local stage=join(reaper.GetResourcePath(),"DAWSync/jobs/"..rid)
  local audio=join(stage,"audio") mkdir(audio)
  local selected,names,transfer={},{},{}
  for i=0,reaper.CountTracks(project)-1 do
    local tr=reaper.GetTrack(project,i)
    selected[tr]=reaper.IsTrackSelected(tr)
    local _,name=reaper.GetTrackName(tr) names[tr]=name
    reaper.SetTrackSelected(tr,false)
    if reaper.GetParentTrack(tr)==nil and reaper.GetMediaTrackInfo_Value(tr,"B_MAINSEND")==1 and trackext(tr,"ROLE")~="reference" then
      local id=trackext(tr,"ID") if id=="" then id="t_"..guid() end
      transfer[#transfer+1]={track=tr,id=id,name=name}
    end
  end
  assert(#transfer>0,"No top-level tracks routed to the master")
  local numeric_keys={"RENDER_SETTINGS","RENDER_BOUNDSFLAG","RENDER_CHANNELS","RENDER_SRATE","RENDER_STARTPOS","RENDER_ENDPOS","RENDER_TAILFLAG","RENDER_TAILMS","RENDER_ADDTOPROJ","RENDER_DITHER","RENDER_NORMALIZE"}
  local string_keys={"RENDER_FILE","RENDER_PATTERN","RENDER_FORMAT","RENDER_FORMAT2"}
  local saved={}
  for _,key in ipairs(numeric_keys) do saved[key]=reaper.GetSetProjectInfo(project,key,0,false) end
  for _,key in ipairs(string_keys) do saved[key]=select(2,reaper.GetSetProjectInfo_String(project,key,"",false)) end
  local rate=reaper.GetSetProjectInfo(project,"PROJECT_SRATE",0,false)
  if rate==0 then rate=44100 end
  local content_end=0
  for i=0,reaper.CountMediaItems(project)-1 do
    local item=reaper.GetMediaItem(project,i)
    if trackext(reaper.GetMediaItem_Track(item),"ROLE")~="reference" then
      local position=reaper.GetMediaItemInfo_Value(item,"D_POSITION")
      local length=reaper.GetMediaItemInfo_Value(item,"D_LENGTH")
      local take=reaper.GetActiveTake(item)
      local endpoint=tonumber(select(2,reaper.GetSetMediaItemInfo_String(item,"P_EXT:DAWSYNC_SOURCE_END","",false)))
      if endpoint and take and reaper.GetTakeNumStretchMarkers(take)==0 and reaper.GetMediaItemInfo_Value(item,"B_LOOPSRC")==0 then
        local offset=reaper.GetMediaItemTakeInfo_Value(take,"D_STARTOFFS")
        local speed=reaper.GetMediaItemTakeInfo_Value(take,"D_PLAYRATE")
        length=math.min(length,math.max(0,(endpoint-offset)/speed))
      end
      content_end=math.max(content_end,position+length)
    end
  end
  assert(content_end>0,"No audible media items")
  local endtime=content_end+4
  local tracks=codec.array()
  local ok,result=xpcall(function()
    for _,t in ipairs(transfer) do
      reaper.GetSetMediaTrackInfo_String(t.track,"P_NAME",t.id,true)
      reaper.SetTrackSelected(t.track,true)
    end
    local settings={RENDER_SETTINGS=1,RENDER_BOUNDSFLAG=0,RENDER_CHANNELS=2,RENDER_SRATE=rate,
      RENDER_STARTPOS=0,RENDER_ENDPOS=endtime,RENDER_TAILFLAG=0,RENDER_TAILMS=0,
      RENDER_ADDTOPROJ=0,RENDER_DITHER=16,RENDER_NORMALIZE=0}
    for key,val in pairs(settings) do reaper.GetSetProjectInfo(project,key,val,true) end
    reaper.GetSetProjectInfo_String(project,"RENDER_FILE",audio,true)
    reaper.GetSetProjectInfo_String(project,"RENDER_PATTERN","$track",true)
    -- Native REAPER WAV configuration: little-endian 'evaw' + 32-bit float.
    reaper.GetSetProjectInfo_String(project,"RENDER_FORMAT","ZXZhdyAAAQ==",true)
    reaper.GetSetProjectInfo_String(project,"RENDER_FORMAT2","",true)
    reaper.Main_OnCommandEx(42230,0,project)
    for _,t in ipairs(transfer) do
      local file=t.id..".wav" local path=join(audio,file)
      local info=wav(path)
      assert(info.sample_rate==rate,"Wrong render sample rate")
      assert(info.bits==32 and (info.format==3 or info.subformat==3),"Expected 32-bit float WAV; render format was not applied")
      tracks[#tracks+1]={id=t.id,name=t.name,role="stem",file="audio/"..file,frames=info.frames,
        duration=info.duration,start_seconds=0,channels=info.channels}
    end
    local master
    for i=0,10000 do
      local filename=reaper.EnumerateFiles(audio,i) if not filename then break end
      if filename:lower()=="master.wav" then master=filename break end
    end
    assert(master,"Master reference render is missing")
    local info=wav(join(audio,master))
    local ref="reference_main.wav" assert(os.rename(join(audio,master),join(audio,ref)))
    tracks[#tracks+1]={id="reference_main",name="Main mix",role="reference",file="audio/"..ref,
      frames=info.frames,duration=info.duration,start_seconds=0,channels=info.channels}
    for _,t in ipairs(tracks) do assert(t.frames==tracks[1].frames,"Render lengths differ") end
    return true
  end,debug.traceback)
  -- Restore all settings even after a cancelled render or missing plugin.
  for key,val in pairs(saved) do
    if type(val)=="number" then reaper.GetSetProjectInfo(project,key,val,true)
    else reaper.GetSetProjectInfo_String(project,key,val,true) end
  end
  for tr,name in pairs(names) do reaper.GetSetMediaTrackInfo_String(tr,"P_NAME",name,true) reaper.SetTrackSelected(tr,selected[tr]) end
  if not ok then error(result) end
  for _,t in ipairs(transfer) do reaper.GetSetMediaTrackInfo_String(t.track,"P_EXT:DAWSYNC_ID",t.id,true) end
  local render_state=reaper.GetProjectStateChangeCount(project)
  local m={schema=1,kind="dawsync-revision",project_id=project_id,project_name=ext(project,"project_name"),
    revision_id=rid,parent_revision=parent,source_daw="reaper",created_at=os.date("!%Y-%m-%dT%H:%M:%SZ"),
    sample_rate=rate,tempo={bpm=bpm,numerator=numerator,denominator=denominator},tracks=tracks,markers=codec.array(),
    content_end_seconds=content_end,
    reaper_project="session.rpp",render_policy="top-level post-fader buses and separate returns; master is a muted reference"}
  local index=0
  while true do
    local retval,isregion,pos,_,name,idx=reaper.EnumProjectMarkers3(project,index)
    if retval==0 then break end
    if not isregion then m.markers[#m.markers+1]={index=idx,name=name,seconds=pos} end
    index=index+1
  end
  write(join(stage,"session.rpp"),project_text(m))
  copy(join(script_dir,"DAWSync.lua"),join(stage,"DAWSync.lua"))
  copy(join(script_dir,"codec.lua"),join(stage,"codec.lua"))
  m.files={}
  local files={"session.rpp","DAWSync.lua","codec.lua"}
  for _,t in ipairs(tracks) do files[#files+1]=t.file end
  for _,relative in ipairs(files) do
    local hash,size=filehash(join(stage,relative)) m.files[relative]={sha256=hash,size=size}
  end
  write(join(stage,"manifest.json"),codec.encode(m).."\n")
  local destination=join(exchange,project_id.."/revisions/"..rid)
  assert(not read(join(destination,"manifest.json")),"Revision already exists") mkdir(destination)
  for _,relative in ipairs(files) do copy(join(stage,relative),join(destination,relative)) end
  copy(join(stage,"manifest.json"),join(destination,"manifest.json"))
  local changed=reaper.GetProjectStateChangeCount(project)~=render_state
  setext(project,"revision_id",rid)
  -- Edits made during cooperative copying remain unsaved until the musician
  -- saves them; the watcher will then render them as a following revision.
  if not changed then reaper.Main_SaveProject(project,false) end
  reaper.ShowConsoleMsg("DAWSync published "..rid.."\n")
  return changed
end

-- Keep editing outside immutable Drive revision folders. A working copy
-- retains the native REAPER effects and source edits between saves.
local function main()
local function open_working(folder,m,exchange)
  local before=reaper.EnumProjects(-1,"")
  verify(folder,m)
  local working=join(reaper.GetResourcePath(),"DAWSync/working/"..m.project_id.."/"..m.revision_id.."_"..guid():sub(1,8))
  mkdir(working)
  for relative in pairs(m.files) do copy(join(folder,relative),join(working,portable(relative))) end
  copy(join(folder,"manifest.json"),join(working,"manifest.json"))
  verify(working,m)
  assert(reaper.EnumProjects(-1,"")==before and reaper.IsProjectDirty(before)==0 and reaper.GetPlayStateEx(before)==0,
    "Project changed while receiving. Save your work and stop playback to receive the update.")
  reaper.Main_openProject(join(working,"session.rpp"))
  local project,path=reaper.EnumProjects(-1,"")
  setext(project,"project_id",m.project_id) setext(project,"revision_id",m.revision_id)
  setext(project,"project_name",m.project_name) setext(project,"exchange_folder",exchange)
  reaper.Main_SaveProject(project,false)
  return project,norm(path)
end
local project,path=reaper.EnumProjects(-1,"")
path=norm(path)
if path=="" then reaper.MB("Open a generated DAWSync session.rpp first.","DAWSync",0) return end
local exchange=ext(project,"exchange_folder")
if exchange=="" then
  local folder=dirname(path)
  local data=read(join(folder,"manifest.json"))
  if not data then reaper.MB("Open a generated session.rpp next to its manifest.json first.","DAWSync",0) return end
  if reaper.IsProjectDirty(project)~=0 then reaper.MB("Save your edits before starting DAWSync.","DAWSync",0) return end
  local ok,m=pcall(codec.decode,data)
  if not ok then reaper.MB(tostring(m),"DAWSync",0) return end
  exchange=dirname(dirname(dirname(folder)))
  local ok,p,newpath=pcall(open_working,folder,m,exchange)
  if not ok then reaper.MB(tostring(p),"DAWSync: waiting for Drive",0) return end
  project,path=p,newpath
end
local last_hash=codec.sha256(read(path) or "")
local pending_at,last_check,last_incoming,busy=nil,0,0,false
local warned_branch
local function incoming()
  local revisions=join(exchange,ext(project,"project_id").."/revisions")
  local candidates={}
  for i=0,10000 do
    local name=reaper.EnumerateSubdirectories(revisions,i) if not name then break end
    local folder=join(revisions,name)
    local data=read(join(folder,"manifest.json"))
    if data then
      local ok,m=pcall(codec.decode,data)
      if ok and m.source_daw=="ableton" and m.project_id==ext(project,"project_id") and m.parent_revision==ext(project,"revision_id") then
        candidates[#candidates+1]={folder=folder,m=m}
      end
    end
  end
  if #candidates>1 then
    if warned_branch~=ext(project,"revision_id") then
      warned_branch=ext(project,"revision_id")
      reaper.ShowConsoleMsg("DAWSync: multiple incoming branches. Open the chosen revision explicitly; all copies are preserved.\n")
    end
  elseif #candidates==1 then
    local c=candidates[1]
    local ready=pcall(verify,c.folder,c.m)
    if ready then
      project,path=open_working(c.folder,c.m,exchange)
      last_hash=codec.sha256(read(path) or "")
      reaper.ShowConsoleMsg("DAWSync received Ableton revision "..c.m.revision_id..". Previous working copy is preserved.\n")
    end
  end
end
reaper.ShowConsoleMsg("DAWSync is watching saves. Working project: "..path.."\n")
local function tick()
  if not reaper.ValidatePtr(project,"ReaProject*") then return end
  local now=reaper.time_precise()
  local active=reaper.EnumProjects(-1,"")
  if now-last_check>=2 and not busy and active==project then
    last_check=now
    local data=read(path)
    if data then
      local hash=codec.sha256(data)
      if hash~=last_hash then last_hash=hash pending_at=now end
    end
    if pending_at and now-pending_at>=8 and reaper.IsProjectDirty(project)==0 and reaper.GetPlayStateEx(project)==0 then
      pending_at=nil busy=true
      local ok,err=xpcall(function() return publish(project,exchange) end,debug.traceback)
      busy=false
      last_hash=codec.sha256(read(path) or "")
      if not ok then
        reaper.MB("Publish stopped; your working project is preserved.\n\n"..tostring(err),"DAWSync",0)
      elseif err then
        pending_at=now
      end
    end
    if not pending_at and now-last_incoming>=20 and reaper.IsProjectDirty(project)==0 and reaper.GetPlayStateEx(project)==0 then
      last_incoming=now
      local ok,err=xpcall(incoming,debug.traceback)
      if not ok then reaper.ShowConsoleMsg("DAWSync incoming update deferred: "..tostring(err).."\n") end
    end
  end
end
while reaper.ValidatePtr(project,"ReaProject*") do tick() coroutine.yield() end
end
local task=coroutine.create(main)
local function resume()
  local ok,err=coroutine.resume(task)
  if not ok then reaper.MB("DAWSync stopped; working copies are preserved.\n\n"..tostring(err),"DAWSync",0)
  elseif coroutine.status(task)~="dead" then reaper.defer(resume) end
end
resume()
