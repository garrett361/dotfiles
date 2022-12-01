local function config()
	local venn = require("nvim_utils").prequire("venn")
	venn.set_arrow("up", "△")
	venn.set_arrow("down", "▽")
	venn.set_arrow("left", "◁")
	venn.set_arrow("right", "▷")

	vim.api.nvim_create_user_command("Draw", function(opts)
		vim.cmd([[setlocal ve=all]])
		-- draw a line on HJKL keystokes
		vim.api.nvim_buf_set_keymap(0, "n", "J", "<C-v>j:VBox<CR>", { noremap = true })
		vim.api.nvim_buf_set_keymap(0, "n", "K", "<C-v>k:VBox<CR>", { noremap = true })
		vim.api.nvim_buf_set_keymap(0, "n", "L", "<C-v>l:VBox<CR>", { noremap = true })
		vim.api.nvim_buf_set_keymap(0, "n", "H", "<C-v>h:VBox<CR>", { noremap = true })
		-- draw a box by pressing "f" with visual selection
		vim.api.nvim_buf_set_keymap(0, "v", "<CR>", ":VBox<CR>", { noremap = true })
	end, {})

	vim.api.nvim_create_user_command("DrawOff", function(opts)
		vim.cmd([[setlocal ve=]])
		vim.cmd([[mapclear <buffer>]])
	end, {})
end
return {
	"jbyuki/venn.nvim",
	lazy = true,
	config = config,
	cmd = "Draw",
}
