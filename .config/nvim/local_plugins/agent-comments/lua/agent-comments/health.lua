local M = {}

-- The decision, separated from vim.health so it can be tested with injected externals.
function M._report(env)
	env = env or {}
	local executable = env.executable or vim.fn.executable
	local available = env.available or require("agent-comments.agents").available
	local out = {}
	if executable("herdr") == 1 then
		out[#out + 1] = { "ok", "herdr found on PATH" }
	else
		out[#out + 1] = {
			"error",
			"herdr not found on PATH",
			"install herdr; without it every send fails at dispatch time",
		}
	end
	-- A missing session is a warning, not an error: commenting works without one, only
	-- sending needs it.
	local ok, reason = available()
	if ok then
		out[#out + 1] = { "ok", "herdr session detected" }
	else
		out[#out + 1] = { "warn", reason, "comments still work; sends will report this error" }
	end
	return out
end

function M.check()
	vim.health.start("agent-comments")
	for _, entry in ipairs(M._report()) do
		vim.health[entry[1]](entry[2], entry[3] and { entry[3] } or nil)
	end
end

return M
