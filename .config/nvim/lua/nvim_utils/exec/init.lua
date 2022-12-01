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

---Run a series of piped shell commands.
---@param cmds string[] cmds to run, one piped to the next.
---@return string
M.shell_piped = function(cmds)
	local res = nil
	for _, cmd in ipairs(cmds) do
		res = M.shell(cmd, res)
	end
	return res
end

---Run a shell command and get the stdout string as a new-line split table in return. Blocking.
---@param cmd string cmd to run
---@return string[]
M.shell_as_table = function(cmd)
	local stdout_str = M.shell(cmd)
	return vim.split(stdout_str, "\n", { trimempty = true })
end

---Run a series of piped shell commands, get the output as a new-line split table.
---@param cmds string[] cmds to run, one piped to the next.
---@return string[]
M.shell_piped_as_table = function(cmds)
	local stdout_str = M.shell_piped(cmd)
	return vim.split(stdout_str, "\n", { trimempty = true })
end

return M
