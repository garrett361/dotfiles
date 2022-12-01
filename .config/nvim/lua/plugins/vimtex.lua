local prequire = require("nvim_utils").prequire
local function config()
	vim.cmd([[
    let g:vimtex_compiler_latexmk = {
        \ 'aux_dir' : '',
        \ 'out_dir' : '',
        \ 'callback' : 1,
        \ 'continuous' : 1,
        \ 'executable' : 'latexmk',
        \ 'hooks' : [],
        \ 'options' : [
        \   '-verbose',
        \   '-file-line-error',
        \   '-shell-escape',
        \   '-synctex=1',
        \   '-interaction=nonstopmode',
        \ ],
        \}
    ]])

	vim.cmd([[let g:tex_flavor = 'latex']])
	vim.cmd([[let g:vimtex_view_method= 'skim']])
	vim.cmd([[let g:vimtex_view_skim_sync = 1]])
	vim.cmd([[let g:vimtex_view_skim_activate = 1]])
	vim.cmd([[let g:vimtex_view_enabled = 1]])
	vim.cmd([[let g:vimtex_mappings_enabled = 1]])
end

return {
	"lervag/vimtex",
	config = config,
	keys = {
		{
			"<leader>tg",
			"<Plug>(vimtex-view)",
			ft = "tex",
		},
		{
			"<leader>tt",
			"<Plug>(vimtex-compile)",
			ft = "tex",
		},
	},
	ft = "tex",
}
