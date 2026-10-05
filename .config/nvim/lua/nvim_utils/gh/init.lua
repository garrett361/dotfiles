local M = {}

---Run a `gh` command that prints a URL and copy that URL to the clipboard
---@param cmd string[]
---@param cwd string?
---@param not_found_msg string
local function copy_gh_url(cmd, cwd, not_found_msg)
	if vim.fn.executable("gh") == 0 then
		vim.notify("gh not found", vim.log.levels.WARN)
		return
	end
	vim.system(cmd, { text = true, cwd = cwd }, function(obj)
		vim.schedule(function()
			if obj.code ~= 0 then
				vim.notify(vim.trim(obj.stderr), vim.log.levels.WARN)
				return
			end
			local url = vim.trim(obj.stdout)
			if url == "" then
				vim.notify(not_found_msg, vim.log.levels.WARN)
				return
			end
			vim.fn.setreg("+", url)
			vim.notify("Copied " .. url)
		end)
	end)
end

---Copy the GitHub URL of the PR associated with a commit, preferring a merged PR
---@param commit_hash string
---@param cwd string?
M.copy_commit_pr_url = function(commit_hash, cwd)
	copy_gh_url({
		"gh",
		"api",
		"repos/{owner}/{repo}/commits/" .. commit_hash .. "/pulls",
		"--jq",
		"(map(select(.merged_at)) + .)[0].html_url // empty",
	}, cwd, "No PR found for " .. commit_hash)
end

---Copy the GitHub URL of the PR whose head is a branch
---@param branch string
---@param cwd string?
M.copy_branch_pr_url = function(branch, cwd)
	copy_gh_url(
		{ "gh", "pr", "view", branch, "--json", "url", "--jq", ".url" },
		cwd,
		"No PR found for " .. branch
	)
end

return M
