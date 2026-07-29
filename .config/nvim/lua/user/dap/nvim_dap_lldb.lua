local M = {}

local function get_default_binary()
	local pwd = vim.fn.expand("%:h") .. "/"

	local default_file_path = vim.fn.expand("%:p")
	local default_binary_path = default_file_path:gsub("%.cpp", "")
	local input_binary = vim.fn.input({
		prompt = "Binary: ",
		default = default_binary_path,
	})
	return input_binary
end

local function get_args()
	local argv = {}
	local arg = vim.fn.input("argv: ")
	for a in string.gmatch(arg, "%S+") do
		table.insert(argv, a)
	end
	vim.cmd('echo ""')
	return argv
end

local config = {
	name = "Current File",
	type = "lldb",
	request = "launch",
	cwd = "${workspaceFolder}",
	program = get_default_binary,
	args = get_args,
}

local cfg = {
	configurations = {
		-- C lang configurations
		c = { config },
		cpp = { config },
	},
}

M.config = function()
	local dap_lldb = require("nvim_utils").prequire("dap-lldb")
	dap_lldb.setup(cfg)
end
return M
