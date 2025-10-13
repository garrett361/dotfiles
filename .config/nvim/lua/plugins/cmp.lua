local function config()
	local cmp = require("nvim_utils").prequire("cmp")

	local luasnip = require("nvim_utils").prequire("luasnip")

	-- GG: Not sure what this function does? Inherited from a previous config.
	local has_words_before = function()
		unpack = unpack or table.unpack
		local line, col = unpack(vim.api.nvim_win_get_cursor(0))
		return col ~= 0
			and vim.api.nvim_buf_get_lines(0, line - 1, line, true)[1]:sub(col, col):match("%s")
				== nil
	end

	-- some other good icons
	local kind_icons = {
		Text = "",
		Method = "m",
		Function = "󰡱",
		Constructor = "",
		Field = "",
		Variable = "󰫧",
		Class = "",
		Interface = "",
		Module = "",
		Property = "",
		Unit = "",
		Value = "󰰬",
		Enum = "",
		Keyword = "󰈭",
		Snippet = "",
		Color = "",
		File = "",
		Reference = "",
		Folder = "",
		EnumMember = "",
		Constant = "",
		Struct = "",
		Event = "",
		Operator = "",
		TypeParameter = "",
	}
	-- find more here: https://www.nerdfonts.com/cheat-sheet

	cmp.setup({
		snippet = {
			expand = function(args)
				luasnip.lsp_expand(args.body) -- For `luasnip` users.
			end,
		},
		mapping = {
			-- Accept currently selected item. If none selected, `select` first item.
			-- Set `select` to `false` to only confirm explicitly selected items.
			["<CR>"] = cmp.mapping.confirm({ select = false }),
			-- TODO: Clean up doubled functions.  Also understand diff between the Tab and S-Tab fns.
			["<Tab>"] = cmp.mapping(function(fallback)
				if cmp.visible() and has_words_before() then
					cmp.select_next_item({ behavior = cmp.SelectBehavior.Select })
				elseif luasnip.expand_or_jumpable() then
					luasnip.expand_or_jump()
				elseif cmp.visible() then
					cmp.select_next_item()
				else
					fallback()
				end
			end, {
				"i",
				"s",
			}),
			["<S-Tab>"] = cmp.mapping(function(fallback)
				if cmp.visible() and has_words_before() then
					cmp.select_prev_item({ behavior = cmp.SelectBehavior.Select })
				elseif luasnip.expand_or_jumpable(-1) then
					luasnip.expand_or_jump(-1)
				elseif cmp.visible() then
					cmp.select_prev_item()
				else
					fallback()
				end
			end, {
				"i",
				"s",
			}),
			["<Down>"] = cmp.mapping(function(fallback)
				if cmp.visible() and has_words_before() then
					cmp.select_next_item({ behavior = cmp.SelectBehavior.Select })
				elseif cmp.visible() then
					cmp.select_next_item()
				else
					fallback()
				end
			end, {
				"i",
				"s",
			}),
			["<Up>"] = cmp.mapping(function(fallback)
				if cmp.visible() and has_words_before() then
					cmp.select_prev_item({ behavior = cmp.SelectBehavior.Select })
				elseif cmp.visible() then
					cmp.select_prev_item()
				else
					fallback()
				end
			end, {
				"i",
				"s",
			}),
		},
		formatting = {
			fields = { "kind", "abbr", "menu" },
			format = function(entry, vim_item)
				-- Kind icons
				vim_item.kind = string.format("%s", kind_icons[vim_item.kind])
				vim_item.menu = ({
					nvim_lsp = "[LSP]",
					luasnip = "[Snippet]",
					buffer = "[Buffer]",
					path = "[Path]",
				})[entry.source.name]
				return vim_item
			end,
		},
		sources = {
			{ name = "buffer" },
			{ name = "luasnip" },
			{ name = "nvim_lsp" },
			{ name = "nvim_lsp_signature_help" },
			{ name = "path" },
		},
		-- https://www.reddit.com/r/neovim/comments/14k7pbc/what_is_the_nvimcmp_comparatorsorting_you_are/
		sorting = {
			comparators = {
				cmp.config.compare.offset,
				cmp.config.compare.exact,
				-- cmp.config.compare.scopes,
				cmp.config.compare.score,
				cmp.config.compare.recently_used,
				cmp.config.compare.locality,
				cmp.config.compare.kind,
				-- cmp.config.compare.sort_text,
				cmp.config.compare.length,
				cmp.config.compare.order,
			},
		},
		window = {
			documentation = {
				border = { "╭", "─", "╮", "│", "╯", "─", "╰", "│" },
			},
		},
		enabled = function()
			return vim.api.nvim_get_option_value("buftype", {}) ~= "prompt"
				or require("cmp_dap").is_dap_buffer()
		end,
	})

	cmp.setup.filetype({ "dap-repl", "dapui_watches", "dapui_hover" }, {
		sources = {
			{ name = "dap" },
		},
	})

	cmp.setup.cmdline({ "/", "?" }, {
		mapping = cmp.mapping.preset.cmdline(),
		sources = {
			{ name = "buffer" },
		},
	})

	cmp.setup.cmdline(":", {
		mapping = cmp.mapping.preset.cmdline(),
		sources = cmp.config.sources({
			{ name = "path" },
		}, {
			{
				name = "cmdline",
				option = {
					ignore_cmds = { "Man", "!" },
				},
			},
		}),
	})
end
return {
	"hrsh7th/nvim-cmp",
	dependencies = {
		"hrsh7th/cmp-buffer",
		"hrsh7th/cmp-cmdline",
		"hrsh7th/cmp-nvim-lsp",
		"hrsh7th/cmp-path",
	},
	config = config,
}
