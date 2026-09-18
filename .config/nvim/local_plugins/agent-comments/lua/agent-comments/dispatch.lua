local M = {}
local exec_mod = require("agent-comments.exec")

function M.send(target, text, opts, exec)
	opts = opts or {}
	exec = exec or exec_mod.default_exec
	if opts.submit then
		-- deliver the text and submit it (presses Enter for you)
		local r = exec({ "herdr", "agent", "prompt", target, text })
		if r.code ~= 0 then
			return false,
				"herdr agent prompt failed: "
					.. (r.stderr ~= "" and r.stderr or ("exit " .. r.code))
		end
	else
		-- deliver the text without submitting it
		local r = exec({ "herdr", "pane", "send-text", target, text })
		if r.code ~= 0 then
			return false,
				"herdr pane send-text failed: "
					.. (r.stderr ~= "" and r.stderr or ("exit " .. r.code))
		end
	end
	return true
end

return M
