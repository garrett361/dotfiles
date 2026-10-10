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

---True when ref resolves to an object.
local function ref_exists(ref)
	return ok(run({ "git", "rev-parse", "--verify", "-q", ref }, 2000))
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

---A branch's `git tree` state from git config, or nil when unset.
local function git_tree_config(branch, key)
	local result = run({ "git", "config", "--get", ("branch.%s.%s"):format(branch, key) }, 2000)
	if not ok(result) then
		return nil
	end
	local value = vim.trim(result.stdout or "")
	return value ~= "" and value or nil
end

---The branch's recorded `git tree` fork commit while it is still an ancestor of HEAD, else nil.
local function git_tree_fork(branch)
	local fork = git_tree_config(branch, "tree-fork-commit")
	if fork and ok(run({ "git", "merge-base", "--is-ancestor", fork, "HEAD" }, 2000)) then
		return fork
	end
	return nil
end

---Base from the branch's `git tree` parent: the recorded fork commit while it is still an ancestor
---of HEAD, else the parent branch itself. Reads git config, since `git tree --json` takes seconds.
local function git_tree_base(branch)
	local parent = git_tree_config(branch, "tree-parent-branch")
	if not parent then
		return nil
	end
	local fork = git_tree_fork(branch)
	if fork then
		return fork, ("git tree fork of %s (%s)"):format(parent, fork:sub(1, 7))
	end
	return parent, "git tree parent " .. parent
end

---Number of commits in merge-base(HEAD, ref)..HEAD, or nil when either git call fails.
local function commits_since_merge_base(ref)
	local merge_base = run({ "git", "merge-base", "HEAD", ref }, 2000)
	if not ok(merge_base) then
		return nil
	end
	local count =
		run({ "git", "rev-list", "--count", vim.trim(merge_base.stdout) .. "..HEAD" }, 2000)
	if not ok(count) then
		return nil
	end
	return tonumber(vim.trim(count.stdout or ""))
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

---Base of the branch's open PR: whichever of `origin/<base>` (local `<base>` when that is missing)
---or the `git tree` fork has the merge-base nearest HEAD, so a locally rebased stack parent beats
---its stale `origin` ref, and a base branch already containing HEAD ranks last. The fork is skipped
---when the base is the default branch, whose unpushed local commits never reach the PR. `gh pr
---list` rather than `gh pr view`: it exits 0 with an empty list for no PR, so a non-zero exit
---means a real failure.
local function gh_pr_base(branch, decline)
	if vim.fn.executable("gh") ~= 1 then
		decline("no gh", vim.log.levels.INFO)
		return nil
	end
	local query =
		{ "gh", "pr", "list", "--head", branch, "--state", "open", "--json", "baseRefName" }
	local result = run(query, 3000)
	if not ok(result) then
		decline("gh failed: " .. error_detail(result), vim.log.levels.WARN)
		return nil
	end
	local prs = decode_json(result.stdout)
	if not prs then
		decline("gh output would not decode", vim.log.levels.WARN)
		return nil
	end
	local base = prs[1] and prs[1].baseRefName
	if not base or base == "" then
		decline("no open PR", vim.log.levels.INFO)
		return nil
	end

	local candidates = {}
	local remote_base = "refs/remotes/origin/" .. base
	local has_remote_base = ref_exists(remote_base)
	if has_remote_base then
		candidates[#candidates + 1] = { ref = remote_base, description = "origin/" .. base }
	else
		decline("no origin/" .. base, vim.log.levels.WARN)
	end
	local tree_parent = git_tree_config(branch, "tree-parent-branch")
	if tree_parent == base then
		local fork = git_tree_fork(branch)
		local default_branch = default_branch_base()
		local targets_default_branch = default_branch == base or default_branch == "origin/" .. base
		if fork and not targets_default_branch then
			local description = ("git tree fork of %s (%s)"):format(base, fork:sub(1, 7))
			candidates[#candidates + 1] = { ref = fork, description = description, is_fork = true }
		end
	elseif tree_parent then
		decline(("git tree parent %s != PR base %s"):format(tree_parent, base), vim.log.levels.WARN)
	end
	local local_base = "refs/heads/" .. base
	if not has_remote_base and ref_exists(local_base) then
		candidates[#candidates + 1] = { ref = local_base, description = "local " .. base }
	end

	local nearest, nearest_rank
	for _, candidate in ipairs(candidates) do
		local rank = commits_since_merge_base(candidate.ref)
		if rank == 0 and not candidate.is_fork then
			rank = math.huge
		end
		if rank and (nearest_rank == nil or rank < nearest_rank) then
			nearest, nearest_rank = candidate, rank
		end
	end
	if not nearest then
		decline("no usable ref for PR base " .. base, vim.log.levels.WARN)
		return nil
	end
	if has_remote_base and nearest.ref ~= remote_base then
		decline(("origin/%s stale"):format(base), vim.log.levels.INFO)
	end
	return nearest.ref, nearest.description
end

---Resolve the ref to diff HEAD's merge-base against, preferring the open PR's base, then the
---`git tree` parent, then the repo's default branch. Reasons collect why each step was passed
---over, plus notes on how the PR base was chosen, for `diffview_pr` to report.
---@return string ref
---@return string description
---@return string[] reasons
---@return integer level
local function get_diff_base_ref()
	local reasons = {}
	local level = vim.log.levels.INFO
	local function decline(reason, reason_level)
		reasons[#reasons + 1] = reason
		level = math.max(level, reason_level)
	end

	local branch = current_branch()
	if not branch then
		decline("no current branch", vim.log.levels.INFO)
	else
		local ref, description = gh_pr_base(branch, decline)
		if ref then
			return ref, description, reasons, level
		end

		ref, description = git_tree_base(branch)
		if ref then
			return ref, description, reasons, level
		end
	end

	local ref, description = default_branch_base()
	if ref then
		return ref, description, reasons, level
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

---Copy the GitHub URL of the PR associated with the file history entry under the cursor.
local function copy_pr_url_at_cursor()
	local view = require("diffview.lib").get_current_view()
	local entry = view and view.panel:get_log_entry_at_cursor()
	if not entry then
		vim.notify("No commit under the cursor", vim.log.levels.WARN)
		return
	end
	require("nvim_utils.gh").copy_commit_pr_url(entry.commit.hash, view.adapter.ctx.toplevel)
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
				{
					"n",
					"<M-y>",
					copy_pr_url_at_cursor,
					{ desc = "Copy the PR URL of the commit under the cursor" },
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
