local ls = require("nvim_utils").prequire("luasnip")
ls.filetype_extend("cuda", { "c", "cpp" })

-- Helper objects, following the docs.
local s = ls.snippet
local sn = ls.snippet_node
local i = ls.insert_node
local c = ls.choice_node
local fmt = require("luasnip.extras.fmt").fmt

local snippets, autosnippets = {}, {}

-- Dynamic nodes -----------------------------------------------------------------

-- local include = {
-- 	s(
-- 		"ii",
-- 		fmt(
-- 			[[#include {}]],
-- 			{ c(1, { sn(1, fmt([[<{}>]], { i(1) })), sn(1, fmt([["{}"]], { i(1) })) }) }
-- 		)
-- 	),
-- }
--
-- local collection = { include }
--
-- for _, snip in pairs(collection) do
-- 	autosnippets = vim.list_extend(autosnippets, snip)
-- end

return snippets, autosnippets
