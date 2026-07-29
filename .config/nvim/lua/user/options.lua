local options = {
	completeopt = { "menuone", "noselect" }, -- mostly just for cmp
	-- confirm = true, -- https://www.reddit.com/r/neovim/comments/1ja1ydw/neovim_how_to_remove_e37_and_e162_errors_which/
	cursorline = true, -- highlight the current line
	diffopt = "internal,filler,closeoff,indent-heuristic,linematch:60,algorithm:histogram", -- https://www.reddit.com/r/neovim/comments/1j9fy2w/comment/mhdjdna/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button
	expandtab = true, -- convert tabs to spaces
	fileencoding = "utf-8", -- the encoding written to a file
	formatoptions = "cqr", -- do not autoformat to linewidth; use gw/gwip/etc
	guicursor = "n-v-c:block-Cursor/lCursor-blinkon0,i-ci-ve:ver25,r-cr:hor20,o:hor50,a:blinkwait700-blinkoff400-blinkon250-Cursor/lCursor", -- cursor style
	guifont = "monospace:h17", -- the font used in graphical neovim applications
	laststatus = 3, -- lines between all splits and only one status bar
	linebreak = true, -- companion to wrap, don't split words
	mouse = "a", -- allow the mouse to be used in neovim
	number = true, -- set numbered lines
	pumheight = 10, -- pop up menu height
	relativenumber = true, -- set relative numbered lines
	scrolloff = 8, -- minimal number of screen lines to keep above and below the cursor
	shada = "!,'10,f1,<10,s10,h", -- https://vi.stackexchange.com/questions/37863/limit-the-amount-of-oldfiles-in-vim-and-neovim
	shiftwidth = 4, -- the number of spaces inserted for each indentation
	showmode = false, -- we don't need to see things like -- INSERT -- anymore
	showtabline = 2, -- always show tabs
	sidescrolloff = 8, -- minimal number of screen columns either side of cursor if wrap is `false`
	signcolumn = "yes", -- always show the sign column, otherwise it would shift the text each time
	smartcase = true, -- smart case
	smartindent = true, -- make indenting smarter again
	splitbelow = true, -- force all horizontal splits to go below current window
	splitright = true, -- force all vertical splits to go to the right of current window
	swapfile = false, -- creates a swapfile
	tabstop = 4, -- insert 4 spaces for a tab
	termguicolors = true, -- set term gui colors (most terminals support this)
	textwidth = 100,
	timeoutlen = 500, -- time to wait for a mapped sequence to complete (in milliseconds)
	undofile = true, -- enable persistent undo
	updatetime = 300, -- faster completion (4000ms default)
	whichwrap = "bs<>[]hl", -- which "horizontal" keys are allowed to travel to prev/next line
	wrap = false, -- display lines as one long line
	writebackup = false, -- if a file is being edited by another program (or was written to file while editing with another program), it is not allowed to be edited
}

for k, v in pairs(options) do
	vim.opt[k] = v
end

-- autoread: https://stackoverflow.com/a/74230727
vim.api.nvim_create_autocmd({ "BufEnter", "CursorHold", "CursorHoldI", "FocusGained" }, {
	command = "if mode() != 'c' | checktime | endif",
	pattern = { "*" },
})
vim.api.nvim_create_autocmd({ "FileChangedShellPost" }, {
	command = 'echohl WarningMsg | echo "File changed on disk. Buffer reloaded." | echohl None',
	pattern = { "*" },
})

-- Clipboard handling: https://github.com/neovim/neovim/discussions/28010#discussioncomment-10187140
vim.o.clipboard = "unnamedplus"
if vim.env.SSH_TTY ~= nil then
	local function my_paste()
		return function()
			return vim.split(vim.fn.getreg('"'), "\n")
		end
	end

	vim.g.clipboard = {
		name = "OSC 52",
		copy = {
			["+"] = require("vim.ui.clipboard.osc52").copy("+"),
			["*"] = require("vim.ui.clipboard.osc52").copy("*"),
		},
		paste = {
			["+"] = my_paste(),
			["*"] = my_paste(),
		},
	}
end

vim.opt.shortmess = "ilmnrx" -- flags to shorten vim messages, see :help 'shortmess'
vim.opt.shortmess:append("c") -- don't give |ins-completion-menu| messages
vim.opt.iskeyword:append("-") -- hyphenated words recognized by searches
vim.opt.runtimepath:remove("/usr/share/vim/vimfiles") -- separate vim plugins from neovim in case vim still in use

vim.wo.colorcolumn = "100" -- set color column

--spelling
vim.opt.spell = true
vim.opt.spelllang = { "en_us" }

-- folds
vim.wo.foldmethod = "expr"
vim.wo.foldexpr = "v:lua.vim.treesitter.foldexpr()"
vim.wo.foldlevel = 1
vim.cmd([[set nofoldenable]]) -- Folds open by default

-- py venv
local function set_python_host_prog()
	local conda_prefix = vim.env.CONDA_PREFIX
	local py_venv = vim.env.VIRTUAL_ENV
	if conda_prefix ~= nil then
		vim.g.python3_host_prog = conda_prefix .. "/bin/python"
	elseif py_venv ~= nil then
		vim.g.python3_host_prog = py_venv .. "/bin/python"
	else
		vim.g.python3_host_prog = "python3"
	end
end

set_python_host_prog()

-- Separate shada files per git dir, if in a git dir
-- https://www.reddit.com/r/neovim/comments/1gv3uqk/comment/lxzjejr/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button
local git_root = vim.fs.root(0, { ".git" })
if git_root ~= nil then
	vim.opt.exrc = true
	local cache_dir = vim.fn.stdpath("data")
	local unique_id = vim.fn.fnamemodify(git_root, ":t") .. "_" .. vim.fn.sha256(git_root):sub(1, 8) ---@type string
	local shadafile = cache_dir .. "/myshada/" .. unique_id .. ".shada"
	vim.opt.shadafile = shadafile
end

-- Diff styling. Return HL group fn, so it can be called after the colorscheme is applied.
vim.opt.fillchars:append({ diff = "╱" })

local M = {}
M.set_diff_hl = function()
	vim.cmd("hi DiffAdd guibg=#1a6236")
	vim.cmd("hi DiffDelete guibg=#ff3f5c")
	vim.cmd("hi DiffChange guibg=#346345")
	vim.cmd("hi DiffText guibg=#5a0267")
end
return M
