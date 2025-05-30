local prequire = require("nvim_utils").prequire

local function config()
	local fzf_lua = require("nvim_utils").prequire("fzf-lua")
	fzf_lua.setup({
		"fzf-native",
		winopts = { fullscreen = true },
		grep = {
			rg_opts = "--column --line-number --hidden --color=always --no-ignore"
				.. " --iglob !.git/ --iglob !.ruff_cache/ --iglob !.mypy_cache/ --iglob !build/ --iglob !.pytest_cache/ ",
		},
		oldfiles = { cwd_only = true, include_current_session = true },
		marks = { marks = "%a", fzf_opts = { ["--multi"] = true } },
		keymap = {
			builtin = {
				-- neovim `:tmap` mappings for the fzf win
				["PgDn"] = "preview-page-down",
				["PgUp"] = "preview-page-up",
			},

			fzf = {
				-- fzf '--bind=' options
				["alt-a"] = "select-all+accept",
				["PgDn"] = "preview-page-down",
				["PgUp"] = "preview-page-up",
				["ctrl-d"] = "half-page-down",
				["ctrl-u"] = "half-page-up",
			},
		},
	})
end

---Diffview between selected commit and previous commit
---@param selected string
local function diffview_prev(selected)
	require("diffview") --Needed to lazy load diffview
	local commit_hash = string.match(selected[1], "^%S+")
	vim.cmd("DiffviewOpen " .. commit_hash .. "^!")
end

---Diffview between selected commit and HEAD
---@param selected string
local function diffview_head(selected)
	require("diffview") --Needed to lazy load diffview
	local commit_hash = string.match(selected[1], "^%S+")
	vim.cmd("DiffviewOpen " .. commit_hash)
end

---Interactive rebase relative to the selected commit
---@param selected string
local function rebase(selected)
	-- Interactive rebase
	local commit_hash = string.match(selected[1], "^%S+")
	vim.cmd("G rebase -i " .. commit_hash .. "^")
end

---Extract info from a line from :marks (capital marks only)
---@param mark string
---@return [string?, string?, string?, string?]
local function get_mark_name_line_col_text(mark)
	local mark_name, line, col, text = mark:match("(.)%s+(%d+)%s+(%d+)%s+(.*)")
	if mark_name == nil then
		return { nil, nil, nil, nil }
	end
	return { mark_name, line, col, text }
end

return {

	"ibhagwan/fzf-lua",
	config = config,
	keys = {
		-- Git related cmds
		{
			"<leader>ab",
			function()
				prequire("fzf-lua").git_branches()
			end,
		},
		{
			"<leader>af",
			function()
				prequire("fzf-lua").fzf_live(
					'git log -G <query> --color --pretty=format:"%C(yellow)%h%Creset %Cgreen(%><(12)%cr%><|(12))%Creset %s %C(blue)<%an>%Creset" | uniq',
					{
						prompt = "Git Code History Search> ",
						previewer = false,
						preview = {
							type = "cmd",
							fn = function(items)
								local commit_hash = string.match(items[1], "^%S+")
								return "git show " .. commit_hash .. " | delta --line-numbers"
							end,
						},
						actions = {
							["enter"] = prequire("fzf-lua.actions").git_checkout,
							["alt-c"] = diffview_prev,
							["alt-d"] = diffview_head,
							["alt-r"] = rebase,
						},
					}
				)
			end,
		},
		{
			"<leader>aF",
			function()
				prequire("fzf-lua").fzf_live(
					'git log --grep=<query> --color --pretty=format:"%C(yellow)%h%Creset %Cgreen(%><(12)%cr%><|(12))%Creset %s %C(blue)<%an>%Creset" | uniq',
					{
						prompt = "Git Commit Msg History Search> ",
						previewer = false,
						preview = {
							type = "cmd",
							fn = function(items)
								local commit_hash = string.match(items[1], "^%S+")
								return "git show " .. commit_hash .. " | delta --line-numbers"
							end,
						},
						actions = {
							["enter"] = prequire("fzf-lua.actions").git_checkout,
							["alt-d"] = diffview_prev,
							["alt-c"] = diffview_head,
							["alt-r"] = rebase,
						},
					}
				)
			end,
		},
		{
			"<leader>al",
			function()
				prequire("fzf-lua").git_commits({

					actions = {
						["alt-d"] = diffview_prev,
						["alt-c"] = diffview_head,
						["alt-r"] = rebase,
					},
				})
			end,
		},
		{
			"<leader>b",
			function()
				prequire("fzf-lua").buffers()
			end,
		},
		-- lsp
		{
			"<leader>ca",
			function()
				prequire("fzf-lua").lsp_code_actions()
			end,
		},
		{
			"<leader>cg",
			function()
				prequire("fzf-lua").lsp_document_diagnostics()
			end,
		},
		{
			"<leader>cw",
			function()
				prequire("fzf-lua").lsp_workspace_diagnostics()
			end,
		},
		-- Other cmds
		{
			"<leader>d",
			function()
				-- https://www.reddit.com/r/neovim/comments/1hgvt7c/comment/m2mofc2/?utm_source=share&utm_medium=mweb3x&utm_name=mweb3xcss&utm_term=1&utm_content=share_button
				prequire("fzf-lua").oldfiles({ winopts = { preview = { delay = 0 } } })
			end,
		},
		{
			"<leader>f",
			function()
				prequire("fzf-lua").live_grep_glob()
			end,
		},
		{
			"<leader>F",
			function()
				prequire("fzf-lua").resume()
			end,
		},
		{
			"<leader>g",
			function()
				prequire("fzf-lua").files({
					cmd = "fd -IH --exclude *.pyc --exclude *.ruff_cache/ --exclude *.mypy_cache/ --exclude *__pycache__/ --exclude *.git/",
					winopts = { preview = { delay = 0 } },
				})
			end,
		},
		{
			"<leader><leader>h",
			function()
				prequire("fzf-lua").command_history()
			end,
		},
		{
			"<leader>D",
			function()
				prequire("fzf-lua").quickfix()
			end,
		},
		{
			"<leader>h",
			function()
				prequire("fzf-lua").helptags()
			end,
		},
		{
			"<leader>m",
			function()
				prequire("fzf-lua").marks({
					actions = {
						["ctrl-r"] = function(selected)
							for _, mark in ipairs(selected) do
								local mark_name, _, _, _ = unpack(get_mark_name_line_col_text(mark))
								vim.cmd("delmarks " .. mark_name)
							end
						end,
					},
				})
			end,
		},
		{
			'<leader>"',
			function()
				prequire("fzf-lua").registers()
			end,
		},
	},
}
