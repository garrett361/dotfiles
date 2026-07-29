local function config()
	local boole = require("nvim_utils").prequire("boole")
	boole.setup({
		mappings = {
			increment = "<C-a>",
			decrement = "<C-x>",
		},
	})
end

return {
	"nat-418/boole.nvim",
	config = config,
	event = "VeryLazy",
}
