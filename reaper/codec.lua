-- Dependency-free JSON and streaming SHA-256 for REAPER's built-in Lua 5.3+.
local M = {}
local array_mt = {}
function M.array(t) return setmetatable(t or {}, array_mt) end
local mask = 0xffffffff
local function ror(x,n) return ((x >> n) | (x << (32-n))) & mask end
local K = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2}
local function block(h,s,p)
  local w = {}
  for i=1,16 do w[i] = string.unpack(">I4",s,p+(i-1)*4) end
  for i=17,64 do
    local a,b = w[i-15],w[i-2]
    local s0,s1 = ror(a,7) ~ ror(a,18) ~ (a >> 3), ror(b,17) ~ ror(b,19) ~ (b >> 10)
    w[i]=(w[i-16]+s0+w[i-7]+s1)&mask
  end
  local a,b,c,d,e,f,g,hh = table.unpack(h)
  for i=1,64 do
    local s1=ror(e,6) ~ ror(e,11) ~ ror(e,25)
    local ch=(e & f) ~ ((~e)&g)
    local t1=(hh+s1+ch+K[i]+w[i])&mask
    local s0=ror(a,2) ~ ror(a,13) ~ ror(a,22)
    local maj=(a&b) ~ (a&c) ~ (b&c)
    local t2=(s0+maj)&mask
    hh,g,f,e,d,c,b,a=g,f,e,(d+t1)&mask,c,b,a,(t1+t2)&mask
  end
  local v={a,b,c,d,e,f,g,hh}
  for i=1,8 do h[i]=(h[i]+v[i])&mask end
end
function M.sha256_stream(read)
  local h={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}
  local tail,total="",0
  while true do
    local s=read()
    if not s or #s==0 then break end
    total=total+#s
    s=tail..s
    local count=#s-#s%64
    for p=1,count,64 do block(h,s,p) end
    tail=s:sub(count+1)
  end
  tail=tail.."\128"..string.rep("\0",(55-total)%64)..string.pack(">I8",total*8)
  for p=1,#tail,64 do block(h,tail,p) end
  local result={}
  for i=1,8 do result[i]=string.format("%08x",h[i]) end
  return table.concat(result)
end
function M.sha256(s)
  local done=false
  return M.sha256_stream(function() if not done then done=true return s end end)
end
function M.sha256_file(path)
  local f=assert(io.open(path,"rb"),"Cannot read "..path)
  local hash=M.sha256_stream(function()
    if coroutine.isyieldable() then coroutine.yield() end
    return f:read(16384)
  end)
  local size=f:seek("end")
  f:close()
  return hash,size
end
local escapes={['"']='\\"',['\\']='\\\\',['\b']='\\b',['\f']='\\f',['\n']='\\n',['\r']='\\r',['\t']='\\t'}
function M.quote(s)
  return '"'..s:gsub('[%z\1-\31\\"]',function(c) return escapes[c] or string.format("\\u%04x",c:byte()) end)..'"'
end
function M.encode(v)
  local t=type(v)
  if t=="nil" then return "null" end
  if t=="boolean" then return tostring(v) end
  if t=="number" then assert(v==v and math.abs(v)~=math.huge,"Nonfinite JSON number") return string.format("%.17g",v) end
  if t=="string" then return M.quote(v) end
  assert(t=="table","Unsupported JSON value")
  local keys={}
  for k in pairs(v) do keys[#keys+1]=k end
  local array=getmetatable(v)==array_mt or (#keys>0 and #v==#keys)
  if array then
    for i=1,#v do if v[i]==nil then array=false break end end
  end
  local out={}
  if array then
    for i=1,#v do out[i]=M.encode(v[i]) end
    return "["..table.concat(out,",").."]"
  end
  table.sort(keys)
  for _,k in ipairs(keys) do out[#out+1]=M.quote(k)..":"..M.encode(v[k]) end
  return "{"..table.concat(out,",").."}"
end
function M.decode(s)
  local p=1
  local function ws() p=(s:find("[^ \t\r\n]",p) or (#s+1)) end
  local parse
  local function str()
    assert(s:sub(p,p)=='"',"Expected JSON string") p=p+1
    local out={}
    while p<=#s do
      local c=s:sub(p,p) p=p+1
      if c=='"' then return table.concat(out) end
      if c=='\\' then
        c=s:sub(p,p) p=p+1
        local esc={['"']='"',['\\']='\\',['/']='/',['b']='\b',['f']='\f',['n']='\n',['r']='\r',['t']='\t'}
        if c=='u' then
          local hex=s:sub(p,p+3) assert(hex:match('^%x%x%x%x$'),"Invalid Unicode escape")
          local code=tonumber(hex,16) p=p+4
          if code>=0xd800 and code<=0xdbff then
            assert(s:sub(p,p+1)=='\\u',"Missing Unicode surrogate")
            local low=tonumber(s:sub(p+2,p+5),16) assert(low and low>=0xdc00 and low<=0xdfff)
            code=0x10000+(code-0xd800)*1024+low-0xdc00 p=p+6
          end
          out[#out+1]=utf8.char(code)
        else assert(esc[c],"Invalid JSON escape") out[#out+1]=esc[c] end
      else assert(c:byte()>=32,"Invalid JSON control character") out[#out+1]=c end
    end
    error("Unterminated JSON string")
  end
  parse=function()
    ws() local c=s:sub(p,p)
    if c=='"' then return str() end
    if c=='{' or c=='[' then
      local object=c=='{' local stop=object and '}' or ']' local result={}
      p=p+1 ws() if s:sub(p,p)==stop then p=p+1 return result end
      while true do
        local key
        if object then ws() key=str() ws() assert(s:sub(p,p)==':') p=p+1 end
        local val=parse() if object then result[key]=val else result[#result+1]=val end
        ws() c=s:sub(p,p) p=p+1
        if c==stop then return result end
        assert(c==',',"Expected JSON separator")
      end
    end
    for literal,val in pairs({['true']=true,['false']=false}) do
      if s:sub(p,p+#literal-1)==literal then p=p+#literal return val end
    end
    if s:sub(p,p+3)=='null' then p=p+4 return nil end
    local token=s:sub(p):match('^-?%d+%.?%d*[eE]?[+-]?%d*')
    local n=token and tonumber(token) assert(n,"Invalid JSON value") p=p+#token return n
  end
  local value=parse() ws() assert(p>#s,"Extra JSON content") return value
end
return M
