local prequire = require("nvim_utils").prequire
local function config()
	local overseer = prequire("overseer")

	overseer.setup()

	-- Load in templates
	for path in
		io.popen("cd ~/.config/nvim/lua/overseer/template && find . -type f | grep .lua"):lines()
	do
		module = path:gsub("%./", ""):gsub("%.lua", ""):gsub("/", ".")
		overseer.load_template(module)
	end
end
return {
	"stevearc/overseer.nvim",
	config = config,
	lazy = true,
	keys = {
		{
			"<leader>r",
			"<cmd>OverseerRun<CR>",
		},
		-- Repeat last Overseer task
		{
			"<leader>R",
			function()
				local overseer = prequire("overseer")
				local tasks = overseer.list_tasks({ recent_first = true })
				if vim.tbl_isempty(tasks) then
					vim.notify("No tasks found", vim.log.levels.WARN)
				else
					overseer.run_action(tasks[1], "restart")
				end
			end,
		},
	},
}
