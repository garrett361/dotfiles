local prequire = require("nvim_utils").prequire

-- Everything goes through setup here: lazy.nvim ignores `opts` whenever a spec supplies its own
-- `config`, so get_main_file was silently dropped while it lived in an `opts` table.
-- `dependencies_bin` was also on the spec rather than in opts, which lazy.nvim drops outright.
local function config()
	local typst_preview = prequire("typst-preview")
	typst_preview.setup({
		invert_colors = "auto",
		dependencies_bin = { tinymist = "tinymist" },
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
	})
end

return {
	"chomosuke/typst-preview.nvim",
	ft = "typst",
	version = "1.*",
	config = config,
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
