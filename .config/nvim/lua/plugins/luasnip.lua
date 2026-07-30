local function config()
	local ls = require("nvim_utils").prequire("luasnip")
	local ls_types = require("nvim_utils").prequire("luasnip.util.types")

	-- General config
	vim.cmd("hi LuasnipChoiceNode guifg=#ff00c7")
	ls.setup({
		history = true,
		update_events = { "TextChanged", "TextChangedI" },
		delete_check_events = { "TextChanged", "InsertEnter" },
		enable_autosnippets = true,
		ext_opts = {
			[ls_types.choiceNode] = { active = { virt_text = { { "ﯟ", "LuasnipChoiceNode" } } } },
			[ls_types.insertNode] = {
				unvisited = {
					virt_text = { { "", "LuasnipChoiceNode" } },
					virt_text_pos = "overlay",
				},
			},
		},
	})

	-- Keymaps following (somewhat) teej: https://www.youtube.com/watch?v=Dn800rlPIho

	vim.keymap.set({ "i", "s", "n" }, "<C-l>", function()
		if ls.choice_active() then
			ls.change_choice(1)
		else
			local key = vim.api.nvim_replace_termcodes("<C-l>", true, false, true)
			vim.api.nvim_feedkeys(key, "isn", false)
		end
	end, { silent = true })

	require("nvim_utils")
		.prequire("luasnip.loaders.from_lua")
		.lazy_load({ paths = "~/.config/nvim/lua/user/snippets/" })
end
return {
	"L3MON4D3/LuaSnip",
	config = config,
	event = "VeryLazy",
	-- Keep these in sync with the blink_cmp mappings! The non-normal mode mappings are there.
	keys = {
		{
			"<Tab>",
			function()
				local ls = require("nvim_utils").prequire("luasnip")
				if ls.expand_or_jumpable() then
					ls.expand_or_jump()
				else
					-- Fallback
					local key = vim.api.nvim_replace_termcodes("<Tab>", true, false, true)
					vim.api.nvim_feedkeys(key, "isn", false)
				end
			end,
			mode = { "n" },
		},
		{
			"<S-Tab>",
			function()
				local ls = require("nvim_utils").prequire("luasnip")
				if ls.expand_or_jumpable(-1) then
					ls.expand_or_jump(-1)
				end
			end,
			mode = { "n" },
		},
	},
}
