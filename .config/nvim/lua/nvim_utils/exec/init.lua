local utils = require("nvim_utils")
local M = {}

---Run a shell command and get the stdout string in return. Blocking.
---@param cmd string cmd to run
---@param stdin string? stdin into cmd
---@return string
M.shell = function(cmd, stdin)
	local stdout_str = nil
	local on_exit = function(obj)
		stdout_str = obj.stdout
	end
	local args = utils.string_to_args(cmd)
	vim.system(args, { text = true, stdin = stdin }, on_exit):wait()
	-- Strip the final newline
	return stdout_str:gsub("\n+$", "") or ""
end

return M
