local prequire = require("nvim_utils").prequire
return {
	"mfussenegger/nvim-dap",
	dependencies = {
		"rcarriga/cmp-dap",
		"mfussenegger/nvim-dap-python",
		"igorlfs/nvim-dap-view",
		"theHamsta/nvim-dap-virtual-text",
		"julianolf/nvim-dap-lldb",
		"ibhagwan/fzf-lua",
	},
	lazy = true,
	config = prequire("user.dap").config,
	keys = prequire("user.dap").lazy_keymaps,
}
