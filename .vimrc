filetype plugin indent on

set nobackup " creates a backup file
set cmdheight=2 " more space in the neovim command line for displaying messages
set conceallevel=0 " so that `` is visible in markdown files
set expandtab " convert tabs to spaces
set fileencoding=utf-8 " the encoding written to a file
set formatoptions=cqr " do not autoformat to linewidth; use gw/gwip/etc
set guifont=monospace:h17 " the font used in graphical neovim applications
set hlsearch " highlight all matches on previous search pattern
set noignorecase " ignore case in search patterns
set linebreak " companion to wrap don't split words
set mouse=a " allow the mouse to be used in neovim
set number " set numbered lines
set numberwidth=4 " set number column width to 2 {default 4}
set pumheight=10 " pop up menu height
set relativenumber " set relative numbered lines
set scrolloff=8 " minimal number of screen lines to keep above and below the cursor
set shiftwidth=4 " the number of spaces inserted for each indentation
set showtabline=2 " always show tabs
set sidescrolloff=8 " minimal number of screen columns either side of cursor if wrap is `false`
set signcolumn=yes " always show the sign column otherwise it would shift the text each time
set smartcase " smart case
set smartindent " make indenting smarter again
set splitbelow " force all horizontal splits to go below current window
set splitright " force all vertical splits to go to the right of current window
set noswapfile " creates a swapfile
set tabstop=4 " insert 4 spaces for a tab
set termguicolors " set term gui colors (most terminals support this)
set textwidth=100
set timeoutlen=300 " time to wait for a mapped sequence to complete (in milliseconds)
set undofile " enable persistent undo
set updatetime=300 " faster completion (4000ms default)
set whichwrap=bs<>[]hl " which horizontal keys are allowed to travel to prev/next line
set nowrap " display lines as one long line
set nowritebackup " if a file is being edited by another program (or was written to file while editing with another program) it is not allowed to be edited
set colorcolumn=100

set cursorline
augroup VimStartup
au!
au VimEnter * highlight CursorLine guifg=black guibg=LightRed ctermfg=black ctermbg=LightRed
augroup END
autocmd InsertLeave * highlight CursorLine guifg=black guibg=LightRed ctermfg=black ctermbg=LightRed
autocmd InsertEnter * highlight CursorLine guifg=NONE guibg=NONE ctermfg=NONE ctermbg=NONE


" Keymaps
nnoremap <silent> <Space> <Nop>
let mapleader=" "
let maplocalleader=" "
nnoremap <silent> <leader>w <cmd>w<CR>
nnoremap <silent> <leader>W <cmd>wq<CR>
nnoremap <silent> <leader>q <cmd>q<CR>
nnoremap <silent> <leader>Q <cmd>qa<CR>
nnoremap <silent> <leader>w <cmd>w<CR>
nnoremap <silent> <leader>x <cmd>bdelete<CR>

" Ex
nnoremap <silent> - <cmd>Ex<CR>

" Up/Down half page w/ centering
nnoremap <silent> <C-u> <C-u>zz
nnoremap <silent> <C-d> <C-d>zz

" Yank
nnoremap <silent> Y y$

" Center when moving to next
nnoremap <silent> n nzzzv
nnoremap <silent> N Nzzzv

" Inserting blank lines above or below
nnoremap <silent> oo mpo<Esc>`p
nnoremap <silent> OO mpO<Esc>`p

" Navigate windows
nnoremap <silent> <Left> <C-w>h
nnoremap <silent> <Down> <C-w>j
nnoremap <silent> <Up> <C-w>k
nnoremap <silent> <Right> <C-w>l

" Resize windows
nnoremap <silent> <C-h> :vertical res +3<cr>
nnoremap <silent> <C-j> :res +3<cr>
nnoremap <silent> <C-k> :res -3<cr>
nnoremap <silent> <C-l> :vertical res -3<cr>


" Changing word under cursor and go to next instance ()
nnoremap <silent> c* *``cgn
nnoremap <silent> c# #``cgN

vnoremap <silent> < <gv
vnoremap <silent> > >gv

" Retain selection after visual paste
vnoremap <silent> p P

cmap <C-s> %s///gc|up<Left><Left><Left><Left><Left><Left><Left>
cmap <C-g> \\(\\)<Left><Left>
cmap <C-k> \\(.*\\)
cmap <C-b> \\<
cmap <C-e> \\>



" Appearance
colorscheme zellner



