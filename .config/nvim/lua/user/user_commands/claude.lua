local aliases = {
	c = { prompt = "/commit-staged", flags = { "--model", "haiku" } },
	r = { prompt = "/reword-commit", flags = { "--model", "haiku" } },
}

vim.api.nvim_create_user_command("C", function(opts)
	local args = opts.args
	local first, rest = args:match("^(%S+)%s*(.*)")
	local alias = aliases[first]

	local cmd = { "claude", "-p" }
	local prompt
	if alias then
		vim.list_extend(cmd, alias.flags or {})
		prompt = (alias.prompt .. " " .. rest):gsub("%s+$", "")
	else
		prompt = args
	end
	table.insert(cmd, prompt)

	vim.notify(table.concat(cmd, " "), vim.log.levels.INFO)
	vim.system(cmd, { text = true }, function(obj)
		vim.schedule(function()
			if obj.code == 0 then
				vim.notify(obj.stdout, vim.log.levels.INFO)
			else
				vim.notify(obj.stderr, vim.log.levels.ERROR)
			end

		end)
	end)
end, {
	nargs = "+",
	desc = "Run a claude -p command asynchronously",
})
