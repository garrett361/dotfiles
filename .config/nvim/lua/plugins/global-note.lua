-- Helpers
local notes_dir = vim.fn.expand("$GITHUB") .. "/garrett361/notes/vim_notes/"

local get_project_name = function()
	local project_name = vim
		.fn
		.system({
			"git",
			"rev-parse",
			"--show-toplevel",
		})
		:match("[^/]*$") -- Get the git directory name
		:gsub("\n", "") -- Remove EOL

	return project_name
end

-- Config below on https://www.reddit.com/r/neovim/comments/1apsyjb/comment/kq98ojc/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button
return {
	"backdround/global-note.nvim",
	cmd = { "Note", "NoteProject" },
	lazy = true,
	keys = {
		{
			"<leader>n",
			"<cmd>NoteProject<cr>",
		},
		{
			"<leader>N",
			"<cmd>Note<cr>",
		},
	},
	opts = function()
		return {
			autosave = false,
			directory = notes_dir,
			filename = "global.md",
			command_name = "Note",
			additional_presets = {
				project_private = {
					directory = function()
						return notes_dir .. get_project_name()
					end,
					filename = "note.md",
					title = function()
						return "Project Note:" .. get_project_name()
					end,
					command_name = "NoteProject",
				},
			},
		}
	end,
}
