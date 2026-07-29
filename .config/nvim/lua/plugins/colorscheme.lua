-- local function config()
-- 	require("nvim_utils").prequire("bamboo").load()
-- end
-- return { "ribru17/bamboo.nvim", config = config, lazy = false, priority = 1000 }

return {
	"Skardyy/makurai-nvim",
	config = function()
		-- you don't have to call setup
		require("makurai").setup({
			transparent = false, -- removes the bg color
			bordered = false, -- removes the bg color from floats/popups
			increase_contrast = false, -- only changes the line number and active line number for now.
		})
		vim.cmd.colorscheme("makurai_dark")
		-- Set diff colors after loading colorscheme, so that they're not overwritten.
		require("user.options").set_diff_hl()
	end,
}

-- return {
-- 	"github-main-user/lytmode.nvim",
-- 	lazy = false,
-- 	priority = 1000,
-- 	config = function()
-- 		require("lytmode").setup()
-- 		vim.cmd.colorscheme("lytmode")
-- 	-- Set diff colors after loading colorscheme, so that they're not overwritten.
-- 	require("user.options").set_diff_hl()
-- 	end,
-- }
