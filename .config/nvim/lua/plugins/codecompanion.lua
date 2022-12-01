local prequire = require("nvim_utils").prequire
local function config()
	local codecompanion = prequire("codecompanion")

	--- Save/restore code companion sessions
	--- https://github.com/fredrikaverpil/dotfiles/blob/64d47392e4e59684a1181e8d957a2433b04625c5/nvim-fredrik/lua/fredrik/plugins/codecompanion.lua
	local function save_path()
		local Path = require("plenary.path")
		local p = Path:new(vim.fn.stdpath("data") .. "/codecompanion_chats")
		p:mkdir({ parents = true })
		return p
	end

	---Load a saved chat filepath into a new chat session.
	---@param filepath string
	local function load_chat(filepath)
		vim.cmd("CodeCompanionChat")

		-- Read contents of saved chat file
		local lines = vim.fn.readfile(filepath)

		-- Get the current buffer (which should be the new CodeCompanion chat)
		local current_buf = vim.api.nvim_get_current_buf()

		-- Paste contents into the new chat buffer
		vim.api.nvim_buf_set_lines(current_buf, 0, -1, false, lines)
	end

	--- Load a saved codecompanion.nvim chat file into a new CodeCompanion chat buffer.
	--- Usage: CodeCompanionLoad
	vim.api.nvim_create_user_command("CodeCompanionLoad", function()
		local fzf = require("fzf-lua")

		local function start_picker()
			local files = vim.fn.glob(save_path() .. "/*", false, true)

			fzf.fzf_exec(files, {
				prompt = "Saved CodeCompanion Chats | <c-r>: remove >",
				previewer = "builtin",
				fzf_opts = { ["--multi"] = true },
				actions = {
					["default"] = function(selected)
						if #selected > 0 then
							local filepath = selected[1]
							load_chat(filepath)
						end
					end,
					["ctrl-r"] = function(selected)
						for _, s in ipairs(selected) do
							local filepath = s
							os.remove(filepath)
							-- Refresh the picker
							start_picker()
						end
					end,
				},
			})
		end

		start_picker()
	end, {})

	--- Save the current codecompanion.nvim chat buffer to a file in the save_folder.
	--- Usage: CodeCompanionSave <filename>.md
	---@param opts table
	vim.api.nvim_create_user_command("CodeCompanionSave", function(opts)
		local success, chat = pcall(function()
			return codecompanion.buf_get_chat(0)
		end)
		if not success or chat == nil then
			vim.notify(
				"CodeCompanionSave should only be called from CodeCompanion chat buffers",
				vim.log.levels.ERROR
			)
			return
		end
		if #opts.fargs == 0 then
			vim.notify(
				"CodeCompanionSave requires at least 1 arg to make a file name",
				vim.log.levels.ERROR
			)
		end
		local save_name = table.concat(opts.fargs, "-") .. ".md"
		local save_file = save_path():joinpath(save_name)
		local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
		save_file:write(table.concat(lines, "\n"), "w")
		-- save_file:write(table.concat(lines, "\n"), "w")
	end, { nargs = "*" })

	-- Call the setup function to change the default behavior
	codecompanion.setup({
		strategies = {
			chat = {
				adapter = "anthropic",
				keymaps = {
					close = {
						modes = {
							n = "<C-c>",
							i = "<M-p>", -- Set to some value I'd never use to avoid <C-c> insert mode default
						},
						index = 2,
						callback = "keymaps.close",
						description = "Close Chat",
					},
				},
			},
			inline = {
				adapter = "anthropic",
			},
			agent = {
				adapter = "anthropic",
			},
		},
	})
end
return {
	"olimorris/codecompanion.nvim",
	dependencies = {
		"nvim-lua/plenary.nvim",
		"nvim-treesitter/nvim-treesitter",
	},
	config = config,
	lazy = true,
	keys = {
		{
			"<leader>cc",
			function()
				vim.cmd([[CodeCompanionChat Toggle]])
			end,
		},
		{
			"<leader>cl",
			function()
				prequire("codecompanion")
				vim.cmd([[CodeCompanionLoad]])
			end,
		},
	},
}
