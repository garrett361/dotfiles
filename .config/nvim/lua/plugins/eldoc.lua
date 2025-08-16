local prequire = require("nvim_utils").prequire
local function config()
	local eldoc = prequire("nvim-eldoc")
	eldoc.setup()
end
return {
	"sj2tpgk/nvim-eldoc",
	lazy = false,
	config = config,
}
