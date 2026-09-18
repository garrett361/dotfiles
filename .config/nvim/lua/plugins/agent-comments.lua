local prequire = require("nvim_utils").prequire

-- Vendored fork of the Lua half of ChmaraX/herdr-nvim (MIT); provenance and the running list of
-- changes are in local_plugins/agent-comments/README.md. The path is absolute on purpose: lazy
-- expands a leading `~` and collapses slashes but never resolves a relative `dir`.
local dir = vim.fn.stdpath("config") .. "/local_plugins/agent-comments"

local function config()
	-- Outside a herdr pane there is no HERDR_WORKSPACE_ID, and agents.lua then treats every agent in
	-- every workspace as a candidate, so a send would go to an unrelated agent. No keymaps there.
	prequire("agent-comments").setup({
		prefix = "<leader>z",
		keymaps = vim.env.HERDR_TAB_ID ~= nil,
	})
end

return {
	dir = dir,
	-- lazy derives both of these anyway; spelled out so a directory rename is a visible change and
	-- so the local-plugin nature is obvious at a glance.
	name = "agent-comments",
	lazy = false,
	config = config,
}
