local prequire = require("nvim_utils").prequire

---Resolve the ref to diff HEAD's merge-base against: the current branch's open PR base (via
---`gh`) when available, else the repo's detected default branch.
---@return string
local function get_diff_base_ref()
	if vim.fn.executable("gh") == 1 then
		local result = vim.system({ "gh", "pr", "view", "--json", "baseRefName", "-q", ".baseRefName" }, {
			text = true,
			timeout = 3000,
		}):wait()
		if result.code == 0 then
			local base = vim.trim(result.stdout or "")
			if base ~= "" then
				vim.fn.system("git rev-parse --verify -q origin/" .. base)
				if vim.v.shell_error == 0 then
					return "origin/" .. base
				end
				return base
			end
		end
	end

	-- No `gh`, no open PR, or the call failed/timed out: fall back to the repo's default branch.
	local default_branch = vim.trim(vim.fn.system("git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null"))
	if vim.v.shell_error == 0 and default_branch ~= "" then
		return default_branch
	end

	for _, candidate in ipairs({ "origin/main", "origin/master", "main", "master" }) do
		vim.fn.system("git rev-parse --verify -q " .. candidate)
		if vim.v.shell_error == 0 then
			return candidate
		end
	end

	vim.notify("get_diff_base_ref: couldn't resolve a base ref, falling back to HEAD", vim.log.levels.WARN)
	return "HEAD"
end

---Diffview of this branch's PR-style diff: merge-base(HEAD, base) .. HEAD, matching GitHub's PR
---view.
local function diffview_pr()
	local base_ref = get_diff_base_ref()
	local merge_base = vim.trim(vim.fn.system("git merge-base HEAD " .. base_ref))
	if vim.v.shell_error ~= 0 or merge_base == "" then
		vim.notify("diffview_pr: couldn't determine merge-base against " .. base_ref, vim.log.levels.ERROR)
		return
	end
	vim.cmd("DiffviewOpen " .. merge_base)
end

local function config()
	local diffview = prequire("diffview")
	-- Call the setup function to change the default behavior
	diffview.setup({
		keymaps = {
			file_panel = {
				{
					"n",
					"<down>",
					false,
				},
				{
					"n",
					"<up>",
					false,
				},
			},
			file_history_panel = {
				{
					"n",
					"<down>",
					false,
				},
				{
					"n",
					"<up>",
					false,
				},
			},
		},
	})
end

return {
	"dlyongemallo/diffview.nvim",
	lazy = true,
	config = config,
	cmd = "DiffviewOpen",
	keys = {
		{
			"<leader>ad",
			"<cmd>DiffviewOpen<cr>",
		},
		{
			"<leader>aD",
			":DiffviewOpen ",
		},
		{
			"<leader>ag",
			diffview_pr,
		},
		{
			"<leader>aS",
			":DiffviewOpen --staged<cr>",
		},
		{
			"<leader>ah",
			"<cmd>DiffviewFileHistory %<cr>",
		},
		{
			"<leader>aq",
			"<cmd>DiffviewClose<cr>",
		},
	},
}
