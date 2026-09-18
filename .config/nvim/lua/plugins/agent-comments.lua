local prequire = require("nvim_utils").prequire

-- Vendored fork of the Lua half of ChmaraX/herdr-nvim (MIT); provenance and the running list of
-- changes are in local_plugins/agent-comments/README.md. The path is absolute on purpose: lazy
-- expands a leading `~` and collapses slashes but never resolves a relative `dir`.
local dir = vim.fn.stdpath("config") .. "/local_plugins/agent-comments"

local function config()
	prequire("agent-comments").setup({ clear_after_send = true })
end

return {
	dir = dir,
	-- lazy derives both of these anyway; spelled out so a directory rename is a visible change and
	-- so the local-plugin nature is obvious at a glance.
	name = "agent-comments",
	-- :checkhealth resolves a health module by runtimepath, and lazy only adds a plugin's directory
	-- to the runtimepath once that plugin loads, so lazy-loading would hide this healthcheck until
	-- something else pulled the plugin in.
	lazy = false,
	config = config,
	keys = {
		{
			"<leader>zc",
			function()
				prequire("agent-comments").comment_line()
			end,
		},
		{
			"<leader>zc",
			function()
				prequire("agent-comments").comment_selection()
			end,
			mode = "x",
		},
		{
			"<leader>zl",
			function()
				prequire("agent-comments").list_comments()
			end,
		},
		{
			"<leader>zS",
			function()
				prequire("agent-comments").send_all({ submit = false })
			end,
		},
		{
			"<leader>zs",
			function()
				prequire("agent-comments").send_all({ submit = true })
			end,
		},
	},
}
