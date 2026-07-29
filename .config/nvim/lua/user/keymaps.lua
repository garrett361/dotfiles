local nvim_utils = require("nvim_utils")
local opts = { noremap = true, silent = true }
local term_opts = { silent = true }

-- Shorten function name
local keymap = vim.api.nvim_set_keymap
keymap("", "<Space>", "<Nop>", opts)
vim.g.mapleader = " "
vim.g.maplocalleader = " "

-- Modes
--   normal_mode = "n",
--   insert_mode = "i",
--   visual_mode = "v",
--   visual_block_mode = "x",
--   term_mode = "t",
--   command_mode = "c",

--------- Normal ---------

-- Large movements
keymap("n", "<C-u>", "<C-u>zz", opts) -- Up/Down half page w/ centering
keymap("n", "<C-d>", "<C-d>zz", opts)

-- Center when moving to next
keymap("n", "n", "nzzzv", opts)
keymap("n", "N", "Nzzzv", opts)

-- Comment out line and copy it below
keymap("n", "ycc", "yygccp", { noremap = false, silent = true })
-- visual mode version (lines)
keymap("v", "ycc", "ygvgcc<Esc>gv<Esc>p", { noremap = false, silent = true })

-- Inserting blank lines, above or below
keymap("n", "oo", "mpo<Esc>`p", opts)
keymap("n", "OO", "mpO<Esc>`p", opts)

-- Navigate windows
keymap("n", "<Left>", "<C-w>h", opts)
keymap("n", "<Down>", "<C-w>j", opts)
keymap("n", "<Up>", "<C-w>k", opts)
keymap("n", "<Right>", "<C-w>l", opts)

-- Resize windows
keymap("n", "<C-h>", ":vertical res +3<cr>", opts)
keymap("n", "<C-j>", ":res +3<cr>", opts)
keymap("n", "<C-k>", ":res -3<cr>", opts)
keymap("n", "<C-l>", ":vertical res -3<cr>", opts)

-- Replacements
local alt_sep = ";"
vim.keymap.set("n", "<leader><leader>s", function()
	local word = vim.fn.expand("<cword>")
	local move_left = "<Left><Left><Left><Left><Left><Left>"
	local sep = "/"
	if word == "" then
		move_left = move_left .. "<Left>"
	elseif word:find(sep) then
		sep = alt_sep
	end
	vim.notify(word)
	local keys = ":%s" .. sep .. word .. sep .. sep .. "gc|up" .. move_left
	nvim_utils.feedkeys(keys)
end, { noremap = true })

vim.keymap.set("x", "<leader><leader>s", function()
	local move_left = "<Left><Left><Left><Left><Left><Left>"
	local keys = nil
	if vim.api.nvim_get_mode().mode == "v" then
		local delete = "<BS><BS><BS><BS><BS>"
		local word = require("nvim_utils").get_vis_text()
		local sep = "/"
		if word:find(sep) then
			sep = alt_sep
		end
		keys = ":" .. delete .. "%s" .. sep .. word .. sep .. sep .. "gc|up" .. move_left
	else
		keys = ":s///gc|up" .. move_left .. "<Left>"
	end

	nvim_utils.feedkeys(keys)
end, { noremap = true })

vim.keymap.set("n", "<leader><leader>c", function()
	local word = vim.fn.expand("<cword>")
	local move_left = "<Left><Left><Left><Left><Left><Left>"
	local sep = "/"
	if word == "" then
		move_left = move_left .. "<Left>"
	elseif word:find(sep) then
		sep = alt_sep
	end
	local keys = ":cfdo %s" .. sep .. word .. sep .. sep .. "gc|up" .. move_left
	nvim_utils.feedkeys(keys)
end, { noremap = true })

vim.keymap.set("v", "<leader><leader>c", function()
	local word = require("nvim_utils").get_vis_text()
	local delete = "<BS><BS><BS><BS><BS>"
	local move_left = "<Left><Left><Left><Left><Left><Left>"
	local sep = "/"
	if word == "" then
		move_left = move_left .. "<Left>"
	elseif word:find(sep) then
		sep = alt_sep
	end
	local keys = ":" .. delete .. "cfdo %s" .. sep .. word .. sep .. sep .. "gc|up" .. move_left
	nvim_utils.feedkeys(keys)
end, { noremap = true })

-- Auto set next global mark
vim.keymap.set("n", "<leader><leader>m", function()
	require("nvim_utils.marks").update_or_set_global_mark()
end, { noremap = true })

-- Buffer management
keymap("n", "<leader>x", "<cmd>bdelete<CR>", opts) -- Close buffer
keymap("n", "<leader>X", "mp<cmd>%bd|e#<CR>'p", opts) -- Close all buffers except current

-- Write/Quit/etc. The W/w ones are overwritten by the conform/lint plugin, when loaded.
keymap("n", "<leader>w", "<cmd>w<CR>", opts)
keymap("n", "<leader>W", "<cmd>wq<CR>", opts)
keymap("n", "<leader>q", "<cmd>q<CR>", opts)
keymap("n", "<leader>Q", "<cmd>qa<CR>", opts)

-- Remove highlighting
keymap("n", "<Esc>", "<cmd>noh<CR>", opts)
--------- Insert ---------

--------- Visual ---------

-- Stay in indent mode
keymap("v", "<", "<gv", opts)
keymap("v", ">", ">gv", opts)

-- Retain selection after visual paste
keymap("v", "p", "P", opts)
keymap("v", "<C-r>", 'c<C-r>=<C-r>"<cr>', opts)

--------- Visual Block ---------

--------- Terminal ---------

-- Better terminal navigation
keymap("t", "<Esc>", "<C-\\><C-n>", term_opts)

--------- Command ---------
keymap("c", "<C-s>", "%s///gc|up<Left><Left><Left><Left><Left><Left><Left>", {})
keymap("c", "<C-g>", "\\(\\)<Left><Left>", {})
keymap("c", "<C-k>", "\\(.*\\)", {})
keymap("c", "<C-b>", "\\<", {})
keymap("c", "<C-e>", "\\>", {})
