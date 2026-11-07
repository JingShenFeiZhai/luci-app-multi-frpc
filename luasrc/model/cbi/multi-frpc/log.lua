f = SimpleForm("log view")
f.reset = false
f.submit = false

t=f:field(TextValue,"conf")
t.rows=26
t.readonly="readonly"
t.wrap = "off"
t.cfgvalue = function(t,t)
	local fh = io.open("/var/etc/multi-frpc/frp.log", "r")
	if not fh then
		return ""
	end
	local data = fh:read("*a")
	fh:close()
	return data or ""
end
t.write = function(e,e,e)
end
return f
