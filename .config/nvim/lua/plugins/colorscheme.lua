local function config()
	require("nvim_utils").prequire("bamboo").load()
	-- Set diff colors after loading colorscheme, so that they're not overwritten.
	require("user.options").set_diff_hl()
end
return { "ribru17/bamboo.nvim", config = config, lazy = false, priority = 1000 }
