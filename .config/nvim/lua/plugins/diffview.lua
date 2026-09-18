local prequire = require("nvim_utils").prequire

local json_opts = { luanil = { object = true, array = true } }

---Run cmd, returning nil when it could not be spawned or did not report back in time.
local function run(cmd, timeout_ms)
	local spawned, proc = pcall(vim.system, cmd, { text = true, timeout = timeout_ms })
	if not spawned then
		return nil
	end
	return proc:wait()
end

---True when a `run` result came back and the command exited cleanly.
local function ok(result)
	return result ~= nil and result.code == 0
end

---Decode command output as JSON, or nil when it does not parse into a table.
local function decode_json(text)
	local decoded_ok, decoded = pcall(vim.json.decode, text or "", json_opts)
	if not decoded_ok or type(decoded) ~= "table" then
		return nil
	end
	return decoded
end

---First line of a failed command's stderr, short enough for a one-line message.
local function error_detail(result)
	if not result then
		return "no exit"
	end
	local first_line = vim.split(vim.trim(result.stderr or ""), "\n")[1]
	if first_line == nil or first_line == "" then
		return ("exit %d"):format(result.code)
	end
	return first_line:sub(1, 26)
end

---The checked-out branch, or nil when HEAD is detached or this is not a repo.
local function current_branch()
	local result = run({ "git", "branch", "--show-current" }, 2000)
	if not ok(result) then
		return nil
	end
	local branch = vim.trim(result.stdout or "")
	return branch ~= "" and branch or nil
end

---Base of the branch's open PR, as `origin/<base>` when that ref exists. `gh pr list` rather than
---`gh pr view`: it exits 0 with an empty list for no PR, so a non-zero exit means a real failure.
local function gh_pr_base(branch)
	if vim.fn.executable("gh") ~= 1 then
		return nil, nil, "no gh", vim.log.levels.INFO
	end
	local query =
		{ "gh", "pr", "list", "--head", branch, "--state", "open", "--json", "baseRefName" }
	local result = run(query, 3000)
	if not ok(result) then
		return nil, nil, "gh failed: " .. error_detail(result), vim.log.levels.WARN
	end
	local prs = decode_json(result.stdout)
	if not prs then
		return nil, nil, "gh output would not decode", vim.log.levels.WARN
	end
	local base = prs[1] and prs[1].baseRefName
	if not base or base == "" then
		return nil, nil, "no open PR", vim.log.levels.INFO
	end
	if ok(run({ "git", "rev-parse", "--verify", "-q", "origin/" .. base }, 2000)) then
		return "origin/" .. base
	end
	return base, "local " .. base, "no origin/" .. base, vim.log.levels.WARN
end

---Base from the branch's `git tree` parent: the recorded fork commit while it is still an ancestor
---of HEAD, else the parent branch itself.
local function git_tree_base(branch)
	local git_tree = "git-tree"
	if vim.fn.executable(git_tree) ~= 1 then
		git_tree = vim.fn.expand("~/.local/bin/git-tree")
		if vim.fn.executable(git_tree) ~= 1 then
			return nil
		end
	end

	local result = run({ git_tree, "--json" }, 1500)
	if not ok(result) then
		return nil, nil, "git tree failed: " .. error_detail(result), vim.log.levels.WARN
	end
	local forest = decode_json(result.stdout)
	if not forest or forest.ok ~= true then
		return nil, nil, "git tree --json failed", vim.log.levels.WARN
	end

	for _, entry in ipairs(forest.branches or {}) do
		if entry.name == branch and entry.parent then
			local fork = entry.fork_commit
			if fork and ok(run({ "git", "merge-base", "--is-ancestor", fork, "HEAD" }, 2000)) then
				return fork, ("git tree fork of %s (%s)"):format(entry.parent, fork:sub(1, 7))
			end
			return entry.parent, "git tree parent " .. entry.parent
		end
	end
	return nil
end

---The repo's detected default branch, else the first of the usual names that verifies.
local function default_branch_base()
	local result = run({ "git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD" }, 2000)
	if ok(result) then
		local default_branch = vim.trim(result.stdout or "")
		if default_branch ~= "" then
			return default_branch, default_branch
		end
	end
	for _, candidate in ipairs({ "origin/main", "origin/master", "main", "master" }) do
		if ok(run({ "git", "rev-parse", "--verify", "-q", candidate }, 2000)) then
			return candidate, candidate
		end
	end
	return nil
end

---Resolve the ref to diff HEAD's merge-base against, preferring the open PR's base, then the
---`git tree` parent, then the repo's default branch. Reasons collect why each step was passed
---over, for `diffview_pr` to report.
---@return string ref
---@return string description
---@return string[] reasons
---@return integer level
local function get_diff_base_ref()
	local reasons = {}
	local level = vim.log.levels.INFO
	local function decline(reason, reason_level)
		if reason then
			reasons[#reasons + 1] = reason
			level = math.max(level, reason_level)
		end
	end

	local branch = current_branch()
	if not branch then
		decline("no current branch", vim.log.levels.INFO)
	else
		local ref, description, reason, reason_level = gh_pr_base(branch)
		decline(reason, reason_level)
		if ref then
			return ref, description or ref, reasons, level
		end

		ref, description, reason, reason_level = git_tree_base(branch)
		decline(reason, reason_level)
		if ref then
			return ref, description or ref, reasons, level
		end
	end

	local ref, description = default_branch_base()
	if ref then
		return ref, description or ref, reasons, level
	end

	return "HEAD", "HEAD (no base resolved)", reasons, math.max(level, vim.log.levels.WARN)
end

---Diffview of this branch's PR-style diff: merge-base(HEAD, base) .. HEAD, matching GitHub's PR
---view.
local function diffview_pr()
	local base_ref, description, reasons, level = get_diff_base_ref()
	if #reasons > 0 then
		local reason_summary = table.concat(reasons, ", ")
		vim.notify(("diffview_pr: %s, using %s"):format(reason_summary, description), level)
	end

	local result = run({ "git", "merge-base", "HEAD", base_ref }, 2000)
	local merge_base = ok(result) and vim.trim(result.stdout or "") or ""
	if merge_base == "" then
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
	"dlyongemallo/diffview-plus.nvim",
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
			"<leader>ah",
			":'<,'>DiffviewFileHistory<cr>",
			mode = "v",
		},
		{
			"<leader>aq",
			"<cmd>DiffviewClose<cr>",
		},
	},
}
