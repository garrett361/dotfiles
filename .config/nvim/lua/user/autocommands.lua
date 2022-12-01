vim.cmd([[
  augroup _general_settings
    autocmd!
    autocmd FileType qf,help,man,lspinfo,dap-float,query nnoremap <silent> <buffer> q :close<CR>
    autocmd TextYankPost * silent!lua require('vim.highlight').on_yank({higroup = 'Visual', timeout = 200})
    autocmd BufWinEnter * :set formatoptions-=cro
    autocmd FileType qf set nobuflisted
  augroup end
]])

-- Yank ring: https://www.reddit.com/r/neovim/comments/1jv03t1/comment/mm6txbm/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button

-- Shift numbered registers up (1 becomes 2, etc.)
local function yank_shift()
	for i = 9, 1, -1 do
		vim.fn.setreg(tostring(i), vim.fn.getreg(tostring(i - 1)))
	end
end

-- Create autocmd for TextYankPost event
vim.api.nvim_create_autocmd("TextYankPost", {
	callback = function()
		local event = vim.v.event
		if event.operator == "y" then
			yank_shift()
		end
	end,
})
