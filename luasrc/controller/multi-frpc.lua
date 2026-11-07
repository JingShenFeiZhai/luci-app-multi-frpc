module("luci.controller.multi-frpc", package.seeall)

-- This controller intentionally declares no module-level local variables,
-- because some firmware Lua runtimes behave badly with captured upvalues.
-- Plain io is used instead of nixio.fs: on the affected firmware
-- `require "nixio.fs"` returns nil, and indexing it in index() breaks the
-- whole LuCI menu tree.
--
-- Menu registration is wrapped in pcall(): if anything goes wrong here the
-- plugin entry is simply missing, but the rest of LuCI stays usable.
-- The reason is written to /tmp/multi-frpc-menu-error.log for debugging.

function index()
	local ok, err = pcall(function()
		local fh = io.open("/etc/config/multi-frpc", "r")
		if not fh then
			return
		end
		fh:close()

		entry({"admin", "services", "multi-frpc"}, alias("admin", "services", "multi-frpc", "base"), _("Multi Frpc"), 100).dependent = true
		entry({"admin", "services", "multi-frpc", "base"}, cbi("multi-frpc/basic"), _("Frp Setting"), 1).leaf = true
		entry({"admin", "services", "multi-frpc", "service_log"}, cbi("multi-frpc/log"), _("Plugin Log"), 2).leaf = true
		entry({"admin", "services", "multi-frpc", "client_log"}, cbi("multi-frpc/client_log"), _("Client Log"), 3).leaf = true
		entry({"admin", "services", "multi-frpc", "config"}, cbi("multi-frpc/config")).leaf = true
		entry({"admin", "services", "multi-frpc", "server"}, cbi("multi-frpc/server")).leaf = true
		entry({"admin", "services", "multi-frpc", "status"}, call("act_status")).leaf = true
		entry({"admin", "services", "multi-frpc", "server_list"}, call("get_server")).leaf = true
		entry({"admin", "services", "multi-frpc", "get_log"}, call("get_log")).leaf = true
	end)

	if not ok then
		local log = io.open("/tmp/multi-frpc-menu-error.log", "w")
		if log then
			log:write(tostring(err), "\n")
			log:close()
		end
	end
end

function act_status()
	local e = {}
	-- only look for frpc processes started by this plugin
	e.running = luci.sys.call("pgrep -f '/var/etc/multi-frpc/frpc-' > /dev/null") == 0
	luci.http.prepare_content("application/json")
	luci.http.write_json(e)
end

function get_server()
	local ret = {}
	local uci = require "luci.model.uci"
	uci = uci.cursor()
	uci:load("multi-frpc")
	uci:foreach("multi-frpc", "server", function (s)
		table.insert(ret, s["name"])
	end)
	luci.http.prepare_content("application/json")
	luci.http.write_json(ret) 
end

function get_log() 
	local name = luci.http.formvalue("name") or ""
	-- only plain names are accepted, never a path
	if name:find("/", 1, true) or name:find("\\", 1, true) or name:find("..", 1, true) then
		name = ""
	end
	local log = "NOT FOUND"
	local fh = io.open(string.format("/var/etc/multi-frpc/frpc-%s.log", name), "r")
	if fh then
		log = fh:read("*a") or ""
		fh:close()
	end
	luci.http.write(log)
end
