local function config()
	local treehopper = require("nvim_utils").prequire("tsht")

	-- vim.cmd("hi TSNodeUnmatched guifg=#ff9900")
	vim.cmd("hi TSNodeKey guifg=#ff9900")
end
return {
	"mfussenegger/nvim-treehopper",
	config = config,
	lazy = true,
	keys = {
		{
			"<leader>v",
			function()
				local treehopper = require("nvim_utils").prequire("tsht")
				treehopper.nodes()
			end,
		},
	},
}
