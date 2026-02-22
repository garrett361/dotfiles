vim.api.nvim_create_user_command("C", function(opts)
	local prompt = opts.args
	vim.notify("Running claude...", vim.log.levels.INFO)
	vim.system({ "claude", "-p", prompt }, { text = true }, function(obj)
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
