local aliases = {
	c = {
		prompt = "$commit-staged",
		sandbox = "danger-full-access",
	},
	rc = {
		prompt = "$reword-commit",
		sandbox = "danger-full-access",
	},
	rs = { prompt = "$review-staged" },
}

vim.api.nvim_create_user_command("X", function(opts)
	local args = opts.args
	local first, rest = args:match("^(%S+)%s*(.*)")
	local alias = aliases[first]

	local sandbox = alias and alias.sandbox or "workspace-write"
	local cmd = { "codex", "exec", "--sandbox", sandbox }
	local prompt
	if alias then
		prompt = (alias.prompt .. " " .. rest):gsub("%s+$", "")
	else
		prompt = args
	end
	table.insert(cmd, prompt)

	-- Run from git root of current buffer (like Fugitive)
	local buf_dir = vim.fn.expand("%:p:h")
	local git_root = vim.fs.root(buf_dir, ".git") or buf_dir

	vim.notify(table.concat(cmd, " "), vim.log.levels.INFO)
	vim.system(cmd, { text = true, cwd = git_root }, function(obj)
		vim.schedule(function()
			if obj.code == 0 then
				vim.notify(obj.stdout or "", vim.log.levels.INFO)
			else
				vim.notify(obj.stderr or "", vim.log.levels.ERROR)
			end
		end)
	end)
end, {
	nargs = "+",
	desc = "Run a codex exec command asynchronously",
})
