-- No capabilities block here: blink.cmp's own plugin/ file registers its delta via
-- vim.lsp.config("*"), which nvim merges under every server (:h lsp-config-merge),
-- rust-analyzer included.

vim.lsp.config.lua_ls = {
	cmd = { "lua-language-server" },
	filetypes = { "lua" },
	root_markers = {
		".luarc.json",
		".luarc.jsonc",
		".stylua.toml",
		"stylua.toml",
		"selene.toml",
		"selene.yml",
		".git",
	},
	settings = {
		Lua = {
			-- LuaJIT and the runtime files are what make vim.* resolve when editing this config.
			runtime = { version = "LuaJIT" },
			workspace = { checkThirdParty = false, library = { vim.env.VIMRUNTIME } },
		},
	},
}

-- get_deps.sh pins clangd rather than taking whatever Xcode or brew ships, since those lag badly.
-- Upstream has no aarch64 Linux build, so those machines get no C/C++ LSP and, because conform
-- routes c/cpp/cuda through the LSP, no C/C++ formatting either.
vim.lsp.config.clangd = {
	cmd = { "clangd" },
	filetypes = { "c", "c.doxygen", "cpp", "cpp.doxygen", "objc", "objcpp", "cuda" },
	root_markers = {
		".clangd",
		".clang-tidy",
		".clang-format",
		"compile_commands.json",
		"compile_flags.txt",
		"configure.ac",
		".git",
	},
	-- Without this, .cu buffers reach clangd as languageId `cuda` and it ignores them silently.
	get_language_id = function(_, ftype)
		local t = { objc = "objective-c", objcpp = "objective-cpp", cuda = "cuda-cpp" }
		return t[ftype] or ftype
	end,
	capabilities = { textDocument = { completion = { editsNearCursor = true } } },
}

vim.lsp.config.ruff = {
	cmd = { "ruff", "server" },
	filetypes = { "python" },
	root_markers = { "pyproject.toml", "ruff.toml", ".ruff.toml", ".git" },
	init_options = {
		settings = {
			lint = {
				extendSelect = {
					"A",
					"ARG",
					"B",
					"C4",
					"C90",
					"FURB",
					"INT",
					"N",
					"NPY",
					"PD",
					"PERF",
					"PIE",
					"PT",
					"PYI",
					"Q",
					"RET",
					"RSE",
					"RUF",
					"SIM",
					"TRY",
					"UP",
				},
				ignore = { "RET504", "N803", "N806", "TRY003" },
			},
		},
	},
	-- ruff and ty both attach to python; without this both hovers merge into one float.
	on_attach = function(client)
		client.server_capabilities.hoverProvider = false
	end,
}

vim.lsp.config.ty = {
	cmd = { "ty", "server" },
	filetypes = { "python" },
	root_markers = { "pyproject.toml", "ty.toml", ".ty.toml", ".git" },
}

vim.lsp.config.tinymist = {
	cmd = { "tinymist" },
	filetypes = { "typst" },
	root_markers = { ".git" },
	settings = {
		projectResolution = "lockedDatabase",
		exportPdf = "onSave",
		semanticTokens = "disable",
	},
}

local servers = { "clangd", "lua_ls", "ruff", "tinymist", "ty" }
vim.lsp.enable(servers)

-- get_deps.sh does not install these here, so warning about them would only train us to ignore
-- it. clangd has no aarch64 Linux build upstream; tinymist is skipped on Linux by choice.
local uname = vim.uv.os_uname()
local unshipped = {
	clangd = uname.sysname == "Linux" and uname.machine == "aarch64",
	tinymist = uname.sysname == "Linux",
}

-- nvim skips a server whose cmd is not executable and only logs it, so a machine that pulled but
-- has not re-run get_deps.sh loses LSP silently. Say so once at startup instead.
vim.schedule(function()
	local missing = {}
	for _, name in ipairs(servers) do
		local cmd = vim.lsp.config[name].cmd
		if not unshipped[name] and type(cmd) == "table" and vim.fn.executable(cmd[1]) == 0 then
			missing[#missing + 1] = cmd[1]
		end
	end
	-- Not a server, but its absence breaks <leader>cf on lua with no other signal.
	if vim.fn.executable("stylua") == 0 then
		missing[#missing + 1] = "stylua"
	end
	if #missing > 0 then
		vim.notify(
			"Missing tools, run get_deps.sh: " .. table.concat(missing, ", "),
			vim.log.levels.WARN
		)
	end
end)

-- Configuring signs and other visuals

vim.diagnostic.config({
	virtual_text = true, -- virtual text
	-- nvim 0.12 ignores sign_define() for diagnostics; sign text comes from here now.
	signs = {
		text = {
			[vim.diagnostic.severity.ERROR] = "",
			[vim.diagnostic.severity.WARN] = "",
			[vim.diagnostic.severity.HINT] = "󰰂",
			[vim.diagnostic.severity.INFO] = "",
		},
	},
	update_in_insert = true,
	underline = false,
	severity_sort = true,
	float = {
		source = true,
		header = "",
		prefix = "",
	},
})
