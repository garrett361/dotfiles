local prequire = require("nvim_utils").prequire
local function config()
	local typst_preview = prequire("typst-preview")
    typst_preview.setup({invert_colors="auto"})

end
return {
	"chomosuke/typst-preview.nvim",
	ft = "typst",
	version = "1.*",
    config=config,
    dependencies_bin = { ['tinymist'] = 'tinymist' },
	opts = {
		get_main_file = function(path_of_buffer)
			local typst_files =
				require("nvim_utils.os").get_files_in_directory(vim.fn.getcwd(), false, ".*%.typ")
			for _, file in ipairs(typst_files) do
				if file:match(".*main.typ") then
					return file
				end
			end
			return path_of_buffer
		end,
	}, -- lazy.nvim will implicitly calls `setup {}`
	keys = {
		{
			"<leader>tg",
			"<cmd>TypstPreviewFollowCursorToggle<cr>",
			ft = "typst",
		},
		{
			"<leader>tt",
			"<cmd>TypstPreview<cr>",
			ft = "typst",
		},
	},
}
