local mason = require("nvim_utils").prequire("mason")
mason.setup()

local cmp_nvim_lsp = require("nvim_utils").prequire("cmp_nvim_lsp")
-- Only cmp's delta belongs here: nvim merges make_client_capabilities() underneath it. The "*"
-- config is merged under every server (:h lsp-config-merge), rust-analyzer included.
vim.lsp.config("*", { capabilities = cmp_nvim_lsp.default_capabilities() })

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

local mason_lspconfig = require("nvim_utils").prequire("mason-lspconfig")
mason_lspconfig.setup({
	-- clangd is the one server worth installing unprompted: it is a hard requirement for C and
	-- C++ LSP, and it also formats those buffers via conform. Mason owns it on macOS too, so the
	-- version stops tracking whatever Xcode ships. It has no aarch64 Linux build, so those
	-- machines log a Mason error each launch and get no C/C++ support either way.
	ensure_installed = { "clangd" },
	-- Off because nvim-lspconfig is gone: automatic_enable would enable Mason-installed servers
	-- with no `filetypes`, and such a config attaches to every buffer rather than none.
	automatic_enable = false,
})

-- Every server is listed explicitly rather than left to automatic_enable. A server whose binary is
-- missing only warns in :checkhealth vim.lsp and logs to :LspLog, so listing all five is safe.
vim.lsp.enable({ "clangd", "lua_ls", "ruff", "tinymist", "ty" })

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
