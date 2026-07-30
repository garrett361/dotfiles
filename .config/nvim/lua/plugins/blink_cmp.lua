local function config()
	local blink = require("nvim_utils").prequire("blink.cmp")

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

	blink.setup({
		-- Top level, not under sources: this swaps both the expand/jump handlers and the source
		-- module away from the vim.snippet default.
		snippets = { preset = "luasnip" },
		appearance = { kind_icons = kind_icons },
		completion = {
			list = {
				selection = {
					-- Defaults to true, which auto-selects the first item and would make <CR>
					-- accept it rather than insert a newline.
					preselect = false,
					-- Defaults to true, which writes the highlighted item into the buffer on
					-- every <Tab>. Selection should only move the highlight.
					auto_insert = false,
				},
			},
			-- Defaults to true, appending () to accepted functions. mini.pairs already owns
			-- bracket insertion.
			accept = { auto_brackets = { enabled = false } },
			menu = {
				draw = {
					columns = {
						{ "kind_icon" },
						{ "label", "label_description", gap = 1 },
						{ "source_name" },
					},
				},
			},
		},
		-- Replaces cmp-nvim-lsp-signature-help. Off by default and still experimental upstream,
		-- so this is the first thing to disable if signatures misbehave.
		signature = { enabled = true },
		cmdline = {
			-- Blink only auto-shows the menu in cmdwin; nvim-cmp showed it while typing.
			completion = { menu = { auto_show = true } },
			-- The cmdline preset binds all three globally, clobbering the regex helpers in
			-- user/keymaps.lua: <C-e> is \> there (paired with <C-b> for \<), and the <C-s> and
			-- <C-g> maps are defined without noremap, so their trailing <Left>s would be
			-- remapped into menu navigation instead of moving the cursor.
			keymap = { ["<Left>"] = false, ["<Right>"] = false, ["<C-e>"] = false },
		},
		keymap = {
			-- Overrides win over the preset per key, so these five behave as they did under
			-- nvim-cmp while <C-e>, <C-b>/<C-f>, <C-k> and <C-space> come from the preset.
			-- <C-k> is a knowing trade: it toggles the signature window and shadows digraphs.
			preset = "default",
			-- The preset binds these with fallback_to_mappings, which falls back only to a user
			-- mapping. With none defined they would be inert whenever the menu is closed, so
			-- unbind them and leave native i_CTRL-N/i_CTRL-P alone.
			["<C-n>"] = false,
			["<C-p>"] = false,
			["<CR>"] = { "accept", "fallback" },
			["<Tab>"] = { "select_next", "snippet_forward", "fallback" },
			["<S-Tab>"] = { "select_prev", "snippet_backward", "fallback" },
			["<Down>"] = { "select_next", "fallback" },
			["<Up>"] = { "select_prev", "fallback" },
		},
		sources = {
			-- Replaces the default list in the REPL rather than extending it, matching what
			-- cmp-dap did. inherit_defaults = true would merge instead.
			per_filetype = { ["dap-repl"] = { "dap" } },
			providers = {
				-- Both default to fallbacks = { "buffer" }, which drops buffer words entirely
				-- whenever LSP or path returns any item at all, tested before scoring.
				lsp = { fallbacks = {} },
				path = { fallbacks = {} },
				-- Named because the id-derived default would render the acronym as "Dap".
				dap = { name = "DAP", module = "blink-cmp-dap" },
			},
		},
	})
end
return {
	"saghen/blink.cmp",
	-- main is an unstable v2, and the prebuilt Rust fuzzy matcher is only downloaded on release
	-- tags. Without the pin it silently falls back to the slower Lua matcher.
	version = "1.*",
	dependencies = { "L3MON4D3/LuaSnip", "mayromr/blink-cmp-dap" },
	config = config,
}
