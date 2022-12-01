local M = {}
M.config = function()
	local dapui = require("nvim_utils").prequire("dapui")
	local dap = require("nvim_utils").prequire("dap")
	dapui.setup({
		controls = {
			enabled = false,
		},
		layouts = {
			{
				elements = {
					{
						id = "repl",
						size = 0.7,
					},
					{
						id = "console",
						size = 0.3,
					},
				},
				position = "bottom",
				size = 10,
			},
			{
				elements = {
					{
						id = "watches",
						size = 0.5,
					},
					{
						id = "scopes",
						size = 0.5,
					},
				},
				position = "bottom",
				size = 5,
			},
		},
		mappings = {
			edit = "e",
			expand = { "<CR>", "<2-LeftMouse>" },
			open = "o",
			remove = "d",
			repl = "r",
			toggle = "t",
		},
		render = {
			indent = 1,
			max_value_lines = 100,
		},
	})
	-- Auto open/close dapui
	dap.listeners.before.attach.dapui_config = function()
		dapui.open(1)
	end
	dap.listeners.before.launch.dapui_config = function()
		dapui.open(1)
	end
	-- dap.listeners.before.event_terminated.dapui_config = function()
	-- 	dapui.close(1)
	-- end
end
return M
