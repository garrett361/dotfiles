local function config()
	local oil = require("nvim_utils").prequire("oil")

	-- Autocmd for opening up quickfix menu when adding to it
	vim.api.nvim_create_autocmd({ "QuickFixCmdPost" }, {
		callback = function()
			vim.cmd("copen")
		end,
	})

	oil.setup({
		-- Keymaps in oil buffer. A string matching "actions.<name>" resolves to
		-- require("oil.actions").<name>; false removes a default mapping.
		keymaps = {
			["g?"] = "actions.show_help",
			["<CR>"] = "actions.select",
			["<M-a>"] = "actions.send_to_qflist",
			["<M-q>"] = { callback = "actions.send_to_qflist", opts = { action = "a" } },
			["<C-c>"] = "actions.close",
			["<C-h>"] = "actions.select_split",
			["<C-l>"] = "actions.refresh",
			["<C-p>"] = "actions.preview",
			["<C-v>"] = false,
			["<C-t>"] = "actions.select_tab",
			["-"] = "actions.parent",
			["_"] = "actions.open_cwd",
			["`"] = "actions.cd",
			["~"] = "actions.tcd",
			["g."] = "actions.toggle_hidden",
		},
		view_options = { show_hidden = true },
	})
end
return {
	"stevearc/oil.nvim",
	lazy = true,
	config = config,
	keys = {
		{
			"-",
			function()
				local oil = require("nvim_utils").prequire("oil")
				oil.open()
			end,
		},
	},
}
