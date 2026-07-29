local ls = require("nvim_utils").prequire("luasnip")
ls.filetype_extend("cpp", { "c" })

-- Helper objects, following the docs.
local s = ls.snippet
local i = ls.insert_node
local c = ls.choice_node
local extras = require("luasnip.extras")
local p = extras.partial
local fmta = require("luasnip.extras.fmt").fmta

local snippets, autosnippets = {}, {}

-- Dynamic nodes -----------------------------------------------------------------

local include = {
	-- More <'s needed to properly format.
	s(
		",p",
		fmta(
			[[
            std::cout <<<< <> <<<< std::endl;
        ]],
			{ i(1) }
		)
	),
}

local collection = { include }

for _, snip in pairs(collection) do
	autosnippets = vim.list_extend(autosnippets, snip)
end

return snippets, autosnippets
