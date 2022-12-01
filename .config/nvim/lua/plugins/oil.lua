local function config()
	local oil = require("nvim_utils").prequire("oil")

	-- Autocmd for opening up quickfix menu when adding to it
	vim.api.nvim_create_autocmd({ "QuickFixCmdPost" }, {
		callback = function()
			vim.cmd("copen")
		end,
	})

	oil.setup({
		-- Oil will take over directory buffers (e.g. `vim .` or `:e src/`
		default_file_explorer = true,
		-- Skip the confirmation popup for simple operations
		skip_confirm_for_simple_edits = false,
		-- Keymaps in oil buffer. Can be any value that `vim.keymap.set` accepts OR a table of keymap
		-- options with a `callback` (e.g. { callback = function() ... end, desc = "", nowait = true })
		-- Additionally, if it is a string that matches "actions.<name>",
		-- it will use the mapping at require("oil.actions").<name>
		-- Set to `false` to remove a keymap
		-- See :help oil-actions for a list of all available actions
		keymaps = {
			["g?"] = "actions.show_help",
			["<CR>"] = "actions.select",
			["<M-a>"] = "actions.send_to_qflist",
			["<M-q>"] = "actions.add_to_qflist",
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
		-- Set to false to disable all of the above keymaps
		use_default_keymaps = true,
		view_options = {
			-- Show files and directories that start with "."
			show_hidden = true,
			-- This function defines what is considered a "hidden" file
			is_hidden_file = function(name, bufnr)
				return vim.startswith(name, ".")
			end,
			-- This function defines what will never be shown, even when `show_hidden` is set
			is_always_hidden = function(name, bufnr)
				return false
			end,
		},
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
