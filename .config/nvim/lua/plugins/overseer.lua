local prequire = require("nvim_utils").prequire
local function config()
	local overseer = prequire("overseer")

	overseer.setup({
		template_dirs = { "overseer/template/user" },
		component_aliases = {
			default = {
				{ "open_output", on_start = "always" },
				"on_exit_set_status",
				"on_complete_notify",
				{ "on_complete_dispose", require_view = { "SUCCESS", "FAILURE" } },
			},
		},
	})

	-- Map q to close overseer window in task list and output buffers
	vim.api.nvim_create_autocmd("BufEnter", {
		callback = function(args)
			local ft = vim.bo[args.buf].filetype
			local has_task = vim.b[args.buf].overseer_task ~= nil
			if ft == "OverseerList" or has_task then
				vim.keymap.set("n", "q", "<cmd>OverseerClose<CR>", { buffer = args.buf })
			end
		end,
	})
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
